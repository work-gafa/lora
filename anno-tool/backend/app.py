"""
行李物品标注与识别平台（独立 Web，UI 参考 lora-webui，业务完全独立）
=====================================================================
与教材的 lora-webui（SD1.5）**没有任何依赖**，只是界面风格参考。

复用 luggage-agent 已有能力，不重复造轮子：
  - 清单 / 别名归类   -> 项目根 taxonomy.json + normalize.py
  - GroundingDINO 预标 -> anno-tool/app.py 的 detect_image（惰性加载）
  - 标注读写         -> data/labeled/manual_annotations.json
  - 语义识别         -> 子进程调用 infer.py（隔离显存，不占 Web 进程）

启动：
  cd luggage-agent/luggage-webui/backend
  D:\\10604\\ANACONDA\\envs\\lora\\python.exe app.py
  浏览器开 http://127.0.0.1:8004
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

# ---------------- 路径 ----------------
BACKEND_DIR = Path(__file__).resolve().parent
WEB_DIR = BACKEND_DIR.parent / "web"
BASE = BACKEND_DIR.parent.parent                      # luggage-agent/
# 依赖：GroundingDINO 预标 / 图片枚举 / 位置文案，复用旧标注平台的实现。
# 旧平台已归档为 _旧版备用_anno-tool。⚠️ 它必须保持为 luggage-agent 的「直接子目录」——
# 它内部用 parent.parent 反推项目根，再往下套一层就会失效。
ANNO_TOOL = BASE / "_旧版备用_anno-tool"

UPLOAD_DIR = BASE / "data" / "labeled" / "uploads"
ANNO_FILE = BASE / "data" / "labeled" / "manual_annotations.json"
TRAIN_JSONL = BASE / "data" / "labeled" / "train.jsonl"
TAXONOMY = BASE / "taxonomy.json"
# 每张图属于哪个场景（travel / school）—— 决定导出时用哪套清单与指令
IMAGE_SCENARIOS = BASE / "data" / "labeled" / "image_scenarios.json"
# 删图时把文件挪到这里（不真删，方便找回）
TRASH_DIR = BASE / "data" / "labeled" / "_trash"
INFER_SCRIPT = BASE / "infer.py"
MODEL_DIR = BASE / "vlm" / "qwen2.5-vl-3b-instruct"
ADAPTER_DIR = BASE / "output" / "lora-adapter"
PYTHON_EXE = Path(r"D:\10604\ANACONDA\envs\lora\python.exe")

for _d in (UPLOAD_DIR, ANNO_FILE.parent):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------- 复用 anno-tool 的已有实现 ----------------
sys.path.insert(0, str(BASE))
_spec = importlib.util.spec_from_file_location("_anno_tool_app", ANNO_TOOL / "app.py")
anno = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(anno)          # 惰性加载，此处不会载入任何模型

CANON = anno.CANON
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# 清单是「单一数据源」，允许在平台上直接改。
# 改完必须让 normalize 与 GroundingDINO 的提示词同步刷新，否则改了不生效。
STATE: dict = {
    "canon": [], "category": {}, "en": {}, "instruction": "", "aliases": {},
    "scenarios": {},            # 场景代号 -> 中文名
    "item_scenarios": {},       # 规范名 -> ["travel"/"school", ...]
    "image_scenarios": {},      # 图片名 -> 场景代号
    "instructions": {},         # 场景代号 -> 该场景的指令
}


def _scenario_items(scenario: str) -> list[str]:
    """某场景对应的清单项。"""
    return [n for n, ss in STATE["item_scenarios"].items() if scenario in ss] or list(STATE["canon"])


def _load_image_scenarios() -> dict:
    if IMAGE_SCENARIOS.exists():
        try:
            return json.loads(IMAGE_SCENARIOS.read_text(encoding="utf-8")).get("map", {})
        except json.JSONDecodeError:
            return {}
    return {}


def _save_image_scenarios(mapping: dict) -> None:
    IMAGE_SCENARIOS.write_text(json.dumps({
        "_comment": "每张图属于哪个场景（travel=旅行 / school=上学回家）。可在平台上修改。",
        "scenarios": STATE["scenarios"],
        "map": mapping,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _reload_taxonomy() -> None:
    """重新读 taxonomy.json，并刷新 normalize / anno-tool / prompt 三处的缓存。"""
    import normalize as norm
    import prompt as prompt_mod

    canon, alias, en, category = norm._load()
    norm.CANON, norm._ALIAS, norm.EN, norm.CATEGORY = canon, alias, en, category
    norm.EN2CANON = {v.lower(): k for k, v in en.items()}

    anno.CANON, anno.EN, anno.CATEGORY = canon, en, category
    anno.en2canon = {v.lower(): k for k, v in en.items()}
    anno.TEXT_PROMPT = " . ".join(en[c] for c in canon) + " ."

    # 场景：来自 taxonomy.json 的 scenarios 字段；缺字段的项视为两场景通用
    # 注意：这里必须内联读文件——_reload_taxonomy() 在模块里先于 _read_taxonomy 定义被调用
    raw = json.loads(TAXONOMY.read_text(encoding="utf-8")) if TAXONOMY.exists() else {"items": []}
    scen_names = raw.get("scenarios") or prompt_mod.SCENARIOS
    item_scen = {}
    for it in raw.get("items", []):
        item_scen[it["name"]] = list(it.get("scenarios") or ["travel", "school"])

    instructions = {}
    for s in scen_names:
        instructions[s] = prompt_mod.build_prompt(_items_for(s, canon, item_scen), s)
    anno.INSTRUCTION = instructions.get("travel", prompt_mod.build_prompt(canon, "travel"))

    STATE.update(
        canon=canon, aliases=alias, category=category, en=en,
        instruction=anno.INSTRUCTION,
        scenarios=scen_names,
        item_scenarios=item_scen,
        image_scenarios=_load_image_scenarios(),
        instructions=instructions,
    )


def _items_for(scenario: str, canon: list, item_scen: dict) -> list[str]:
    picked = [n for n in canon if scenario in (item_scen.get(n) or ["travel", "school"])]
    return picked or list(canon)


_reload_taxonomy()
CANON = STATE["canon"]
CATEGORY = STATE["category"]
normalize_name = anno.normalize_name


def _read_taxonomy() -> dict:
    return json.loads(TAXONOMY.read_text(encoding="utf-8"))


def _write_taxonomy(data: dict) -> None:
    TAXONOMY.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _reload_taxonomy()


# ---------------- 通用 ----------------

def _load_annotations() -> dict:
    if ANNO_FILE.exists():
        return json.loads(ANNO_FILE.read_text(encoding="utf-8"))
    return {}


def _save_annotations(data: dict, merge: bool = True) -> None:
    """保存标注。

    ⚠️ `merge=True` 是**必须**的：前端每次只提交「当前这张图」的框，
    如果直接整体覆盖，保存 A 图就会把 B..K 图的标注全部清空。

    merge=False 仅供「恢复 / 批量导入」等确实要整体替换的场景使用。
    """
    valid = set(anno.known_names())
    incoming = {k: v for k, v in data.items() if k in valid}

    if merge:
        current = _load_annotations()
        current.update(incoming)          # 只覆盖本次提交的图，其余原样保留
        result = current
    else:
        result = incoming

    # 覆盖前留一份滚动备份，防止误写无法回溯
    if ANNO_FILE.exists():
        try:
            shutil.copy2(ANNO_FILE, ANNO_FILE.with_name("manual_annotations.prev.json"))
        except OSError:
            pass

    ANNO_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve(name: str):
    return anno.resolve_image_path(name)


app = FastAPI(title="行李物品标注与识别平台", version="1.0.0")


# ---------------- 健康与清单 ----------------

@app.get("/api/health")
def health() -> dict:
    return {
        "model": MODEL_DIR.is_dir(),
        "adapter": ADAPTER_DIR.is_dir(),
        "taxonomy": TAXONOMY.is_file(),
        "infer_script": INFER_SCRIPT.is_file(),
        "python": PYTHON_EXE.is_file(),
        "annotated_images": len(_load_annotations()),
        "items": len(STATE["canon"]),
    }


@app.get("/api/canon")
def canon() -> dict:
    return {"canon": STATE["canon"], "category": STATE["category"]}


@app.get("/api/taxonomy")
def taxonomy() -> dict:
    return _read_taxonomy()


# ---------------- 场景 ----------------

@app.get("/api/scenarios")
def scenarios() -> dict:
    """场景列表 + 每个场景的清单项 + 每张图所属场景。"""
    return {
        "scenarios": STATE["scenarios"],
        "items": {s: _scenario_items(s) for s in STATE["scenarios"]},
        "image_scenarios": STATE["image_scenarios"],
    }


class ImageScenarioPayload(BaseModel):
    image_scenarios: dict


@app.put("/api/image-scenarios")
def put_image_scenarios(payload: ImageScenarioPayload) -> dict:
    """设置每张图属于哪个场景（不存在的图名会被忽略）。"""
    known = set(anno.known_names())
    clean = {k: v for k, v in payload.image_scenarios.items()
             if k in known and v in STATE["scenarios"]}
    mapping = dict(STATE["image_scenarios"])
    mapping.update(clean)
    _save_image_scenarios(mapping)
    STATE["image_scenarios"] = mapping
    return {"ok": True, "updated": len(clean), "map": mapping}


def _scenario_of(image_name: str) -> str:
    return STATE["image_scenarios"].get(image_name, "travel")


# ---------------- 清单的增 / 改 / 删（平台上直接改，改完即时生效） ----------------

class ItemPayload(BaseModel):
    name: str
    en: str = ""
    category: str = "其他"
    aliases: list[str] = []
    # 归属场景；留空 = 两个场景通用
    scenarios: list[str] = []


class ClassifyPayload(BaseModel):
    names: list[str]


def _clean_scenarios(value) -> list[str]:
    """只保留已知场景；留空表示两场景通用。"""
    if not value:
        return ["travel", "school"]
    known = set(STATE["scenarios"]) or {"travel", "school"}
    picked = [s for s in value if s in known]
    return picked or ["travel", "school"]


def _check_name(name: str, exclude: str | None = None) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "名称不能为空")
    if len(name) > 20:
        raise HTTPException(400, "名称请控制在 20 字以内")
    exist = {it["name"] for it in _read_taxonomy()["items"]}
    if exclude:
        exist.discard(exclude)
    if name in exist:
        raise HTTPException(400, f"「{name}」已存在")
    return name


@app.post("/api/taxonomy/items")
def add_item(payload: ItemPayload) -> dict:
    name = _check_name(payload.name)
    data = _read_taxonomy()
    data["items"].append({
        "name": name,
        "en": (payload.en or name).strip(),
        "category": (payload.category or "其他").strip(),
        "aliases": [a.strip() for a in payload.aliases if a.strip()],
        "scenarios": _clean_scenarios(payload.scenarios),
    })
    _write_taxonomy(data)
    return {"ok": True, "taxonomy": data}


@app.put("/api/taxonomy/items/{old_name}")
def update_item(old_name: str, payload: ItemPayload) -> dict:
    data = _read_taxonomy()
    target = next((it for it in data["items"] if it["name"] == old_name), None)
    if target is None:
        raise HTTPException(404, f"清单里没有「{old_name}」")
    new_name = _check_name(payload.name, exclude=old_name)
    target["name"] = new_name
    target["en"] = (payload.en or new_name).strip()
    target["category"] = (payload.category or "其他").strip()
    target["aliases"] = [a.strip() for a in payload.aliases if a.strip()]
    target["scenarios"] = _clean_scenarios(payload.scenarios)

    # 改名时，同步把已有标注里用到的旧名改成新名
    renamed = 0
    if new_name != old_name:
        annos = _load_annotations()
        for boxes in annos.values():
            for b in boxes or []:
                if (b.get("name") or "").strip() == old_name:
                    b["name"] = new_name
                    renamed += 1
        if renamed:
            _save_annotations(annos)
    _write_taxonomy(data)
    return {"ok": True, "renamed_boxes": renamed, "taxonomy": data}


@app.delete("/api/taxonomy/items/{name}")
def delete_item(name: str) -> dict:
    data = _read_taxonomy()
    before = len(data["items"])
    data["items"] = [it for it in data["items"] if it["name"] != name]
    if len(data["items"]) == before:
        raise HTTPException(404, f"清单里没有「{name}」")

    annos = _load_annotations()
    used = sum(1 for boxes in annos.values() for b in (boxes or [])
               if (b.get("name") or "").strip() == name)
    _write_taxonomy(data)
    return {"ok": True, "used_boxes": used, "taxonomy": data}


@app.post("/api/classify")
def classify(payload: ClassifyPayload) -> dict:
    """给一批名字，返回各自会归到哪个规范名（null = 归不进去，导出时会被丢弃）。"""
    out = {}
    for raw in payload.names:
        raw = (raw or "").strip()
        if raw in out:
            continue
        canon = normalize_name(raw)
        out[raw] = canon
    return {"results": out, "canon": STATE["canon"]}


# ---------------- 图片与标注 ----------------

@app.get("/api/images")
def images() -> dict:
    """列出全部图片（预设图集 + 自主上传），并标注每张图的框数。"""
    annos = _load_annotations()
    items = []
    for meta in anno.all_images():
        name = meta["name"]
        items.append({
            "name": name,
            "source": meta.get("source", "preset"),
            "boxes": len(annos.get(name, []) or []),
            "scenario": _scenario_of(name),
        })
    return {"images": items, "annotations": annos,
            "scenarios": STATE["scenarios"], "image_scenarios": STATE["image_scenarios"]}


@app.get("/api/image/{name}")
def get_image(name: str):
    p = _resolve(name)
    if not p:
        raise HTTPException(404, "图片不存在")
    return FileResponse(p)


@app.delete("/api/images/{name}")
def delete_image(name: str, hard: bool = False) -> dict:
    """删掉一张图（连同它的标注与场景设置）。

    ⚠️ 默认**不真删**：文件移到 data/labeled/_trash/，可以在资源管理器里找回来。
    传 ?hard=true 才彻底删除（谨慎使用）。
    """
    p = _resolve(name)
    if not p:
        raise HTTPException(404, f"找不到图片「{name}」")
    src = Path(p)

    # 1) 标注：必须 merge=False 整体改写，否则被删的键会因为 merge 又留下
    annos = _load_annotations()
    removed_boxes = len(annos.pop(name, []) or [])
    _save_annotations(annos, merge=False)

    # 2) 场景映射
    if name in STATE["image_scenarios"]:
        mapping = dict(STATE["image_scenarios"])
        mapping.pop(name)
        _save_image_scenarios(mapping)
        STATE["image_scenarios"] = mapping

    # 3) 文件：移到回收站（留在原地/子目录，便于用户找回）
    if hard:
        src.unlink()
        where = "(已彻底删除)"
    else:
        TRASH_DIR.mkdir(parents=True, exist_ok=True)
        dest = TRASH_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}_{name}"
        shutil.move(str(src), str(dest))
        where = str(dest)

    return {"ok": True, "image": name, "removed_boxes": removed_boxes, "moved_to": where}


class AnnoPayload(BaseModel):
    annotations: dict


@app.put("/api/annotations")
def put_annotations(payload: AnnoPayload) -> dict:
    _save_annotations(payload.annotations, merge=True)
    stored = _load_annotations()
    return {
        "ok": True,
        "saved": len(payload.annotations),      # 本次提交的图数
        "total": len(stored),                   # 文件里现有的图数（应 ≥ 提交数）
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in IMAGE_EXTS:
        raise HTTPException(400, f"仅支持 {'/'.join(sorted(IMAGE_EXTS))}")
    base = re.sub(r"[^\w一-鿿.\-]", "_", os.path.splitext(file.filename)[0])[:60] or "upload"
    name, i = base + ext, 1
    while (UPLOAD_DIR / name).exists():
        name = f"{base}_{i}{ext}"
        i += 1
    (UPLOAD_DIR / name).write_bytes(await file.read())
    return {"name": name, "source": "upload"}


# ---------------- AI 能力 ----------------

@app.post("/api/autodetect/{name}")
def autodetect(name: str) -> dict:
    """GroundingDINO 自动预标（首次调用会加载检测模型）。"""
    p = _resolve(name)
    if not p:
        raise HTTPException(404, "图片不存在")
    try:
        boxes, size = anno.detect_image(str(p))
    except Exception as exc:
        raise HTTPException(500, f"自动标注失败：{exc}") from exc
    return {"name": name, "boxes": boxes, "size": size}


def _run_infer(path: Path, scenario: str = "travel") -> dict:
    cmd = [
        str(PYTHON_EXE), str(INFER_SCRIPT),
        "--image", str(path),
        "--model", str(MODEL_DIR),
        "--adapter", str(ADAPTER_DIR),
        "--taxonomy", str(TAXONOMY),
        "--scenario", scenario,
        "--json",
    ]
    env = os.environ.copy()
    env.pop("ACC_PRODUCT_CONFIG_V3", None)
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    env["PYTHONIOENCODING"] = "utf-8"

    start = time.time()
    proc = subprocess.run(
        cmd, cwd=str(BASE), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=900,
    )
    if proc.returncode != 0:
        raise HTTPException(500, f"识别失败：{(proc.stderr or proc.stdout or '')[-400:]}")
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            r = (payload.get("results") or [{}])[0]
            return {
                "image": r.get("image") or path.name,
                "scenario": scenario,
                "items": payload.get("items", []),
                "present": r.get("present", []),
                "missing": r.get("missing", []),
                "error": r.get("error"),
                "elapsed": round(time.time() - start, 1),
            }
    raise HTTPException(500, "未能解析模型输出")


@app.post("/api/recognize/{name}")
async def recognize(name: str, scenario: str = "travel") -> dict:
    """用训练好的 LoRA 识别这张图：返回「带了没 + 文字位置」。

    scenario 决定用哪套清单（travel=旅行 / school=上学），
    场景专属项不会出现在另一场景的结果里。
    """
    p = _resolve(name)
    if not p:
        raise HTTPException(404, "图片不存在")
    if scenario not in STATE["scenarios"]:
        scenario = "travel"
    # 图上标注过场景的话，以图片的标注为准（未指定时才用传入的）
    effective = STATE["image_scenarios"].get(name, scenario)
    return await asyncio.to_thread(_run_infer, Path(p), effective)


# ---------------- 导出训练数据 ----------------

@app.post("/api/export")
def export() -> dict:
    """把人工画框标注导出成 train.jsonl（经 normalize 归类，不再丢框）。"""
    annos = _load_annotations()
    if not annos:
        raise HTTPException(400, "还没有标注，先画框保存")

    out, n_true = [], 0
    dropped: dict[str, int] = {}          # 归不进清单的名字 -> 出现次数（会被丢弃）
    skipped_no_bbox = 0
    scenario_count: dict[str, int] = {}   # 每个场景导出了几条
    off_scenario: dict[str, int] = {}     # 框的物品不属于该图场景 -> 出现次数（不写入答案）

    for meta in anno.all_images():
        name, src = meta["name"], meta["source"]
        # 只导出「动过标注的图」：annotations 里有这个键（哪怕是空列表，代表人工确认过）
        # 没有键 = 从没标注过，不能当成「全部未带」的负样本塞进去，会污染训练数据
        if name not in annos:
            continue
        p = _resolve(name)
        if not p:
            continue

        # ★ 按这张图的场景取清单与指令：旅行图只问旅行项，上学图只问上学项
        scen = _scenario_of(name)
        canon = _scenario_items(scen)
        instruction = STATE["instructions"].get(scen, STATE["instruction"])
        scenario_count[scen] = scenario_count.get(scen, 0) + 1

        W, H = Image.open(p).convert("RGB").size
        present_map = {}
        for b in annos.get(name, []) or []:
            raw = (b.get("name") or "").strip()
            bb = b.get("bbox") or []
            if len(bb) != 4:
                skipped_no_bbox += 1
                continue
            if not raw:
                dropped["(空名字)"] = dropped.get("(空名字)", 0) + 1
                continue
            nm = normalize_name(raw) or raw
            if nm not in STATE["canon"]:
                dropped[raw] = dropped.get(raw, 0) + 1
                continue
            if nm not in canon:
                # 物品本身在清单里，但不属于这张图的场景（如上学图标了「相机」）
                key = f"{raw}（{scen}场景不含）"
                off_scenario[key] = off_scenario.get(key, 0) + 1
                continue
            if nm in present_map:
                continue
            px = [bb[0] * W, bb[1] * H, bb[2] * W, bb[3] * H]
            present_map[nm] = anno.region_text(px, W, H)

        # ★ 只写「看到的」物品：{"items":[{name,location}]}
        # 「未带」= 清单 - 已带，由程序算，不占模型输出长度
        answer = {
            "items": [
                {"name": it, "location": present_map[it]}
                for it in canon if it in present_map
            ]
        }
        n_true += len(present_map)
        rel = f"labeled/uploads/{name}" if src == "upload" else f"raw/reference_wuzi/{name}"
        out.append({
            "image": rel,
            "scenario": scen,
            "instruction": instruction,
            "answer": json.dumps(answer, ensure_ascii=False),
        })

    TRAIN_JSONL.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n", encoding="utf-8")
    return {
        "ok": True, "images": len(out), "present": n_true,
        "path": str(TRAIN_JSONL), "items": len(STATE["canon"]),
        "by_scenario": scenario_count,
        "dropped": dropped, "off_scenario": off_scenario,
        "skipped_no_bbox": skipped_no_bbox,
    }


@app.get("/api/stats")
def stats() -> dict:
    annos = _load_annotations()
    total_boxes = sum(len(v or []) for v in annos.values())
    return {
        "images": len(anno.all_images()),
        "annotated": len([k for k, v in annos.items() if v]),
        "boxes": total_boxes,
        "items": len(STATE["canon"]),
    }


# ---------------- 前端 ----------------

@app.middleware("http")
async def _no_cache_frontend(request, call_next):
    """前端是本机直接改文件、免构建的，必须禁用缓存。

    否则改完 app.js 刷新页面还是旧代码（"改了没生效"基本都是这个原因）。
    """
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        # 注意：Starlette 的 MutableHeaders 没有 .pop()，只能用 del（且要判存在）
        if "etag" in resp.headers:
            del resp.headers["etag"]
    return resp


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8004, log_level="info")
