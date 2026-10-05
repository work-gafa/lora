"""
luggage-agent/anno-tool/app.py
================================
实时标注工具（后端）。镜像 lora 平台的「后端 API + 前端 HTML」模块划分，
但本工具聚焦"人工画框 + AI 预标注"——不需要写坐标。

核心能力：
  1) 预设图集：data/raw/reference_wuzi（点击切换，等同「数据集管理」Tab）
  2) 自主上传：POST /api/upload 直接上传任意行李图片到 data/labeled/uploads
  3) AI 自动标注：上传后 / 点「AI自动标注当前图」会调用 GroundingDINO 生成候选框，
     前端填充为可手改的框（移动 / 缩放 / 改名 / 删除 / 补画）
  4) 标注读写：/api/annotations（等同「WD14 打标」Tab 的标注存储）
  5) 一键导出：/api/export 生成 train.jsonl（等同「训练任务」Tab 的数据装配）

启动（用户本机，lora 环境）：
  cd luggage-agent/anno-tool
  D:\10604\ANACONDA\envs\lora\python.exe app.py
  浏览器开 http://127.0.0.1:8003

坐标约定：前端传【归一化坐标 [0,1]】（与显示尺寸无关），后端导出时再乘原图宽高转像素。
"""
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image
import torch

BASE = Path(__file__).resolve().parent.parent            # luggage-agent/
IMG_DIR = BASE / "data" / "raw" / "reference_wuzi"        # 预设图集
UPLOAD_DIR = BASE / "data" / "labeled" / "uploads"        # 自主上传的行李图
OUT_DIR = BASE / "data" / "labeled"
ANNO_FILE = OUT_DIR / "manual_annotations.json"
TRAIN_JSONL = OUT_DIR / "train.jsonl"
STATIC_DIR = Path(__file__).resolve().parent / "static"

IMG_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== 必备物品清单（单一来源：项目根 taxonomy.json，改这一处全链路生效）=====
import json as _json
from pathlib import Path as _Path
import sys as _sys
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # 让 anno-tool 能 import 项目根模块
from normalize import CANON, EN as _EN, CATEGORY, normalize_name
from prompt import build_prompt

EN = _EN
# 导出训练数据用的提示词：与 train.py / infer.py 完全一致（统一来自 prompt.py）
INSTRUCTION = build_prompt(CANON)

# 同义/别名归并：统一由项目根 normalize.py 处理（读 taxonomy.json 的 aliases）
# 兼容旧用法：MERGE 保留为空 dict，导出时走 normalize_name()
MERGE = {}

# ---- GroundingDINO 自动标注（懒加载，首次调用时才载入模型） ----
_DETECTOR = None
# 规范名 -> GroundingDINO 英文提示词（已加载自 taxonomy.json）
en2canon = {v.lower(): k for k, v in EN.items()}
TEXT_PROMPT = " . ".join(EN[c] for c in CANON) + " ."


def get_detector():
    global _DETECTOR
    if _DETECTOR is None:
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        device = "cuda" if torch.cuda.is_available() else "cpu"
        mdir = str(BASE / "vlm" / "grounding-dino-tiny")
        proc = AutoProcessor.from_pretrained(mdir)
        mdl = AutoModelForZeroShotObjectDetection.from_pretrained(mdir).to(device).eval()
        _DETECTOR = (proc, mdl, device)
    return _DETECTOR


def detect_image(path, box_th=0.30, text_th=0.25):
    """对单张图跑 GroundingDINO，返回 (boxes, [W,H])。
    boxes: [{"name":规范名, "bbox_px":[x1,y1,x2,y2], "score":float}]"""
    proc, mdl, device = get_detector()
    img = Image.open(path).convert("RGB")
    W, H = img.size
    inputs = proc(images=img, text=TEXT_PROMPT, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = mdl(**inputs)
    try:
        res = proc.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=box_th,
            text_threshold=text_th, target_sizes=[img.size[::-1]])[0]
    except TypeError:
        res = proc.post_process_grounded_object_detection(
            outputs, inputs.input_ids, box_threshold=box_th,
            text_threshold=text_th, target_sizes=[img.size[::-1]])[0]
    out = []
    for box, score, lab in zip(res["boxes"].cpu().tolist(),
                               res["scores"].cpu().tolist(),
                               res.get("text_labels", res.get("labels"))):
        key = str(lab).strip().lower().strip(".")
        canon = en2canon.get(key)
        if canon is None:
            for e, c in en2canon.items():
                if e in key or key in e:
                    canon = c
                    break
        if canon is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in box]
        out.append({"name": canon, "bbox_px": [x1, y1, x2, y2],
                    "score": round(float(score), 3)})
    # 同类 NMS：抑制高度重叠的同名框（草稿更干净，少人工清理）
    out = nms_by_class(out, iou_th=0.6)
    return out, [W, H]


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


def nms_by_class(boxes, iou_th=0.6):
    groups = {}
    for b in boxes:
        groups.setdefault(b["name"], []).append(b)
    kept = []
    for name, items in groups.items():
        items.sort(key=lambda x: -x["score"])
        for b in items:
            bb = b["bbox_px"]
            if all(_iou(bb, k["bbox_px"]) < iou_th for k in kept if k["name"] == name):
                kept.append(b)
    kept.sort(key=lambda x: x["name"])
    return kept


app = FastAPI(title="行李标注 · 手动画框工具")

# ---------- 工具函数 ----------

def preset_images():
    if not IMG_DIR.exists():
        return []
    return [f for f in os.listdir(IMG_DIR)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))]

def upload_images():
    if not UPLOAD_DIR.exists():
        return []
    return [f for f in os.listdir(UPLOAD_DIR)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))]

def all_images():
    return [{"name": n, "source": "preset"} for n in preset_images()] + \
           [{"name": n, "source": "upload"} for n in upload_images()]

def known_names():
    return set(preset_images()) | set(upload_images())

def resolve_image_path(name):
    p = UPLOAD_DIR / name
    if p.exists():
        return str(p)
    p = IMG_DIR / name
    if p.exists():
        return str(p)
    return None

def region_text(box, W, H):
    x1, y1, x2, y2 = [float(v) for v in box]
    if (x2 - x1) * (y2 - y1) > 0.6 * W * H:
        return "整张画面"
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    hx = "左" if cx < W / 3 else ("右" if cx > 2 * W / 3 else "中")
    # 注意：纵向分界必须用 H，早先误写成 W，导致非正方形图片的上下判断全错
    vy = "上" if cy < H / 3 else ("下" if cy > 2 * H / 3 else "中")
    if hx == "中" and vy == "中":
        return "画面中央"
    if hx == "中":
        return f"画面{vy}方"
    if vy == "中":
        return f"画面{hx}侧"
    return f"画面{vy}{hx}角"

# ---- 训练后 LoRA 识别（懒加载，复用 infer.py）----
import threading as _threading
_LORA = None
_LORA_LOCK = _threading.Lock()
def get_lora():
    global _LORA
    if _LORA is None:
        with _LORA_LOCK:
            if _LORA is None:
                import importlib
                _infer = importlib.import_module("infer")
                mdir = str(BASE / "vlm" / "qwen2.5-vl-3b-instruct")
                adir = str(BASE / "output" / "lora-adapter")
                adir = adir if (BASE / "output" / "lora-adapter").exists() else None
                _LORA = _infer.load_model(mdir, adir)
    return _LORA

def lora_items():
    """LoRA 识别用的清单项：优先取 train.jsonl 训练项（与当前 adapter 严格一致），否则回退 taxonomy。"""
    if TRAIN_JSONL.exists():
        try:
            line = TRAIN_JSONL.read_text(encoding="utf-8").splitlines()[0]
            rec = json.loads(line)
            ans = rec["answer"]
            if isinstance(ans, str):
                ans = json.loads(ans)
            items = [a["name"] for a in ans if "name" in a]
            if items:
                return items
        except Exception:
            pass
    return CANON

# ---------- 数据模型 ----------

class AnnosPayload(BaseModel):
    # { "图片名": [ {"name":..,"bbox":[x1,y1,x2,y2](归一化0-1),"color":..}, ... ], ... }
    annotations: dict

# ---------- 路由 ----------

@app.get("/api/images")
def api_images():
    return {"images": all_images()}

@app.get("/api/canon")
def api_canon():
    return {"canon": CANON}

@app.get("/api/image/{name}")
def api_image(name: str):
    p = resolve_image_path(name)
    if not p:
        raise HTTPException(404, "图片不存在")
    return FileResponse(p)

@app.get("/api/annotations")
def api_get_annotations():
    if ANNO_FILE.exists():
        return {"annotations": json.loads(ANNO_FILE.read_text(encoding="utf-8"))}
    return {"annotations": {}}

@app.post("/api/annotations")
def api_post_annotations(payload: AnnosPayload):
    # 仅保留已知图片名对应的条目（预设 + 上传），过滤非法输入
    valid = known_names()
    clean = {k: v for k, v in payload.annotations.items() if k in valid}
    ANNO_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "saved": len(clean)}

@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """上传一张行李图片 → 存到 uploads → 立即用 GroundingDINO 自动标注 → 返回框。"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        raise HTTPException(400, "仅支持图片文件")
    base = re.sub(r"[^\w一-鿿.\-]", "_", os.path.splitext(file.filename)[0])[:60] or "upload"
    name = base + ext
    i = 1
    while (UPLOAD_DIR / name).exists():
        name = f"{base}_{i}{ext}"
        i += 1
    data = await file.read()
    (UPLOAD_DIR / name).write_bytes(data)
    boxes, size = detect_image(str(UPLOAD_DIR / name))
    return {"name": name, "boxes": boxes, "size": size, "source": "upload"}

@app.get("/api/autodetect/{name}")
def api_autodetect(name: str):
    """对任意已加载的图片（预设或上传）重新跑 GroundingDINO 自动标注。"""
    p = resolve_image_path(name)
    if not p:
        raise HTTPException(404, "图片不存在")
    boxes, size = detect_image(p)
    return {"name": name, "boxes": boxes, "size": size}

@app.post("/api/lora_recognize/{name}")
def api_lora_recognize(name: str):
    """用训练后的 LoRA 识别当前图：返回每项「带没带 + 文字位置」。
    精确框仍由 GroundingDINO 提供；本接口只做语义识别（混合模式）。"""
    p = resolve_image_path(name)
    if not p:
        raise HTTPException(404, "图片不存在")
    model, proc = get_lora()
    import importlib
    _infer = importlib.import_module("infer")
    items = lora_items()
    raw = _infer.infer_one(p, items, model, proc)
    parsed = _infer.try_parse_json(raw)
    return {"name": name, "items": parsed or [],
            "raw": raw,
            "note": "当前 LoRA 为旧 23 项训练版，过度预测明显（精确率约24%），结果仅供参考；建议按 22 项清单重训后使用"}

@app.get("/api/autodraft")
def api_autodraft():
    """把 GroundingDINO 的 detections.json 转成前端可用的框（兼容旧预设草稿）。"""
    dpath = OUT_DIR / "detections.json"
    if not dpath.exists():
        raise HTTPException(404, "没有自动标注草稿（detections.json）")
    raw = json.loads(dpath.read_text(encoding="utf-8"))
    draft, sizes = {}, {}
    for img, per in raw.items():
        p = resolve_image_path(img)
        if not p:
            continue
        W, H = Image.open(p).convert("RGB").size
        sizes[img] = [W, H]
        boxes = []
        for nm, rec in per.items():
            if rec.get("present") and rec.get("bbox_px"):
                boxes.append({"name": nm, "bbox_px": rec["bbox_px"]})
        draft[img] = boxes
    return {"draft": draft, "sizes": sizes}

@app.post("/api/export")
def api_export():
    """把人工画框标注转成 train.py 能吃的 train.jsonl（与 gdino_to_train.py 同 schema）。
    导出遍历【全部已标注图片】（预设 + 上传）；上传图的 image 字段记 labeled/uploads/..。"""
    if not ANNO_FILE.exists():
        raise HTTPException(400, "还没有标注，先画框保存")
    anno = json.loads(ANNO_FILE.read_text(encoding="utf-8"))
    out = []
    n_true = 0
    for meta in all_images():
        img = meta["name"]
        src = meta["source"]
        p = resolve_image_path(img)
        if not p:
            continue
        W, H = Image.open(p).convert("RGB").size
        boxes = anno.get(img, [])
        present_map = {}
        for b in boxes:
            nm = (b.get("name") or "").strip()
            # 统一归类：细名/自由命名 -> 规范大类（读 taxonomy.json 的 aliases）
            nm = normalize_name(nm) or MERGE.get(nm, nm)
            bb = b.get("bbox") or [0, 0, 0, 0]
            if nm not in CANON or len(bb) != 4:
                continue
            if nm in present_map:
                continue
            px = [bb[0] * W, bb[1] * H, bb[2] * W, bb[3] * H]
            present_map[nm] = region_text(px, W, H)
        answer = []
        for it in CANON:
            if it in present_map:
                answer.append({"name": it, "present": True, "location": present_map[it]})
                n_true += 1
            else:
                answer.append({"name": it, "present": False, "location": None})
        rel = ("labeled/uploads/" + img) if src == "upload" else ("raw/reference_wuzi/" + img)
        out.append({"image": rel, "instruction": INSTRUCTION,
                    "answer": json.dumps(answer, ensure_ascii=False)})
    TRAIN_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
        encoding="utf-8")
    return {"ok": True, "train_jsonl": str(TRAIN_JSONL),
            "images": len(out), "present": n_true}

# ---------- 前端 ----------

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
