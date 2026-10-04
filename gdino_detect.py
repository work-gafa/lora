"""
luggage-agent/gdino_detect.py
==================================================
用 GroundingDINO（开集目标检测）对 11 张参考图自动标注 23 个出行物品的像素边界框。
相比 Qwen2.5-VL 零样本 grounding，GroundingDINO 是专门做「文字→准框」的检测器，
框的位置和区分度明显更好，适合作为"模型预标注 + 人工检查"的草稿。

产出：
  data/labeled/detections.json          （覆盖为 GroundingDINO 结果；VLM 草稿另存）
  data/labeled/locations_review.csv
  data/labeled/overlays/<图名>_bbox.jpg

用法：python gdino_detect.py [--box_th 0.30] [--text_th 0.25]
"""
import argparse
import csv
import json
import os
import shutil

from PIL import Image, ImageDraw, ImageFont
import torch
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# 必备物品清单（单一来源：taxonomy.json，与 anno-tool/app.py 共用，改一处全链路生效）
import json as _json
from pathlib import Path as _Path
_TAX_FILE = _Path(__file__).resolve().parent / "taxonomy.json"
_data = _json.loads(_TAX_FILE.read_text(encoding="utf-8"))
CANON = [it["name"] for it in _data["items"]]
EN = {it["name"]: it["en"] for it in _data["items"]}

IMG_DIR = "data/raw/reference_wuzi"
OUT_DIR = "data/labeled"
MODEL_DIR = "vlm/grounding-dino-tiny"
IMAGES = sorted(f for f in os.listdir(IMG_DIR)
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")))

COLORS = [
    (220, 50, 50), (50, 120, 220), (40, 160, 80), (230, 150, 20),
    (150, 60, 200), (20, 180, 180), (230, 90, 140), (120, 120, 40),
    (70, 160, 200), (200, 70, 40), (90, 170, 60), (180, 120, 30),
    (130, 70, 180), (30, 150, 150), (210, 110, 60), (100, 140, 210),
    (170, 90, 170), (60, 170, 110), (220, 60, 90), (140, 110, 50),
    (80, 130, 160), (190, 80, 120), (110, 150, 70),
]
COLOR_MAP = {n: COLORS[i % len(COLORS)] for i, n in enumerate(CANON)}


def get_font(size):
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf",
              "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_overlay(image_path, det, out_path):
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)
    font = get_font(max(22, int(H * 0.030)))
    for name, rec in det.items():
        x1, y1, x2, y2 = [int(v) for v in rec["bbox_px"]]
        color = COLOR_MAP.get(name, (220, 50, 50))
        draw.rectangle([x1, y1, x2, y2], outline=color, width=max(3, int(W * 0.005)))
        label = f"{name} {rec.get('score', 0):.2f}"
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ly = y1 - th - 10
        if ly < 0:
            ly = y1 + 4
        draw.rectangle([x1, ly, x1 + tw + 14, ly + th + 10], fill=color)
        draw.text((x1 + 7, ly + 4), label, fill=(255, 255, 255), font=font)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, quality=90)


def region_text(box, W, H):
    """把像素框中心换算成「画面X区域」文字，供训练的位置字段使用。"""
    x1, y1, x2, y2 = [float(v) for v in box]
    if (x2 - x1) * (y2 - y1) > 0.6 * W * H:
        return "整张画面"
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    hx = "左" if cx < W / 3 else ("右" if cx > 2 * W / 3 else "中")
    vy = "上" if cy < H / 3 else ("下" if cy > 2 * H / 3 else "中")
    if hx == "中" and vy == "中":
        return "画面中央"
    if hx == "中":
        return f"画面{vy}方"
    if vy == "中":
        return f"画面{hx}侧"
    return f"画面{vy}{hx}角"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--box_th", type=float, default=0.30)
    ap.add_argument("--text_th", type=float, default=0.25)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(MODEL_DIR)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(MODEL_DIR).to(device).eval()

    # 英文提示 -> 规范名 反查
    en2canon = {v.lower(): k for k, v in EN.items()}
    text_prompt = " . ".join(EN[c] for c in CANON) + " ."

    detections = {}
    for fname in IMAGES:
        img = Image.open(os.path.join(IMG_DIR, fname)).convert("RGB")
        inputs = processor(images=img, text=text_prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        try:
            res = processor.post_process_grounded_object_detection(
                outputs, inputs.input_ids, threshold=args.box_th,
                text_threshold=args.text_th, target_sizes=[img.size[::-1]])[0]
        except TypeError:
            res = processor.post_process_grounded_object_detection(
                outputs, inputs.input_ids, box_threshold=args.box_th,
                text_threshold=args.text_th, target_sizes=[img.size[::-1]])[0]
        boxes = res["boxes"].cpu().tolist()
        scores = res["scores"].cpu().tolist()
        labels = res.get("text_labels", res.get("labels"))
        per = {}
        for box, score, lab in zip(boxes, scores, labels):
            key = str(lab).strip().lower().strip(".")
            canon = en2canon.get(key)
            if canon is None:  # 模糊匹配
                for e, c in en2canon.items():
                    if e in key or key in e:
                        canon = c
                        break
            if canon is None:
                continue
            if canon in per and per[canon]["score"] >= score:
                continue
            x1, y1, x2, y2 = [int(v) for v in box]
            per[canon] = {"present": True, "score": round(float(score), 3),
                          "bbox_px": [x1, y1, x2, y2]}
        detections[fname] = per
        print(f"  {fname}: {len(per)} 项 -> {sorted(per)}")

    # 写出当前检测结果
    old = os.path.join(OUT_DIR, "detections.json")

    with open(old, "w", encoding="utf-8") as f:
        json.dump(detections, f, ensure_ascii=False, indent=2)

    rows = []
    for fname in IMAGES:
        path = os.path.join(IMG_DIR, fname)
        w, h = Image.open(path).convert("RGB").size
        draw_overlay(path, detections[fname],
                     os.path.join(OUT_DIR, "overlays", fname.rsplit(".", 1)[0] + "_bbox.jpg"))
        for name in CANON:
            rec = detections[fname].get(name)
            if rec:
                x1, y1, x2, y2 = rec["bbox_px"]
                loc = region_text([x1, y1, x2, y2], w, h)
                rows.append([fname, name, "TRUE", x1, y1, x2, y2,
                             abs(x2 - x1), abs(y2 - y1), rec["score"], loc])
            else:
                rows.append([fname, name, "FALSE", "", "", "", "", "", "", "", ""])
    with open(os.path.join(OUT_DIR, "locations_review.csv"), "w", newline="", encoding="utf-8-sig") as f:
        wc = csv.writer(f)
        wc.writerow(["image", "item", "present", "x1", "y1", "x2", "y2",
                     "box_w", "box_h", "score", "location"])
        wc.writerows(rows)
    print("✅ 已写 detections.json / locations_review.csv / overlays")


if __name__ == "__main__":
    main()
