"""
luggage-agent/gdino_to_train.py
================================
把「人工核对后的定位标注」转成 train.py 能吃的训练数据 (data/labeled/train.jsonl)。

为什么要它：
  gdino_detect.py 产出的是「像素框 + 物品名」(locations_review.csv / detections.json)，
  而训练目标 (train.py) 需要的是「物品 present + 位置文字」。
  本脚本把人改好的 CSV 读进来：
    - present  = (CSV 里 present 列为 TRUE 且该行有合法坐标)
    - location = 直接用 CSV 的 location 列（你可在 Excel 里改得更准）；若为空则按框中心自动推「画面X区域」
  生成 data/labeled/train.jsonl。

优先读取 locations_corrected.csv（你另存并改好的版本）；
若不存在则退回 locations_review.csv（机器草稿，仅供先跑通）。

用法：
  python gdino_to_train.py                         # 自动选 corrected / review
  python gdino_to_train.py --src data/labeled/locations_corrected.csv
"""
import argparse
import csv
import json
import os

CANON = [
    "身份证", "手机", "充电器", "充电宝", "耳机", "相机", "钱包/现金", "银行卡",
    "钥匙", "衣物", "内衣袜", "洗漱用品", "护肤品", "防晒", "常用药品", "口罩",
    "湿巾", "雨伞", "水杯", "转换插头", "护照(出境)", "门票/订单", "零食",
]
INSTRUCTION = "请检查照片中的出行必备物品，逐项判断是否在照片内并给出位置"
IMG_DIR = "data/raw/reference_wuzi"
REVIEW = "data/labeled/locations_review.csv"
CORRECTED = "data/labeled/locations_corrected.csv"
OUT_JSONL = "data/labeled/train.jsonl"


def region_text(box, W, H):
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


def read_anno_csv(path):
    """尝试多种编码读取标注 CSV；若文件是 xlsx/乱码则返回 None。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            with open(path, encoding=enc, newline="") as f:
                rows = list(csv.DictReader(f))
            if rows and "image" in rows[0]:
                return rows, enc
        except Exception:
            continue
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    args = ap.parse_args()
    src = args.src or (CORRECTED if os.path.exists(CORRECTED) else REVIEW)
    if args.src and not os.path.exists(src):
        print("❌ 找不到", src)
        return

    rows, enc = read_anno_csv(src)
    if rows is None and src == CORRECTED and os.path.exists(REVIEW):
        print("⚠️ locations_corrected.csv 无法解析（大概率是 Excel 存成了 xlsx 但扩展名仍是 .csv，"
              "或编码异常），自动改用 locations_review.csv")
        src = REVIEW
        rows, enc = read_anno_csv(REVIEW)
    if rows is None:
        print("❌ 找不到可解析的标注 CSV，请先跑 gdino_detect.py")
        return
    print(f"   读取来源：{src}（编码 {enc}）")

    rows_by_img = {}
    for row in rows:
            img = (row.get("image") or "").strip()
            item = (row.get("item") or "").strip()
            if not img or not item:
                continue
            present = str(row.get("present", "")).strip().upper() == "TRUE"
            coords = [row.get(c, "") for c in ("x1", "y1", "x2", "y2")]
            valid = all(c.strip() != "" for c in coords)
            box = [int(float(c)) for c in coords] if valid else None
            loc = (row.get("location") or "").strip()
            rows_by_img.setdefault(img, {})[item] = {
                "present": present and valid, "box": box, "loc": loc}

    out = []
    for img in sorted(rows_by_img):
        from PIL import Image
        W, H = Image.open(os.path.join(IMG_DIR, img)).convert("RGB").size
        answer = []
        for it in CANON:
            rec = rows_by_img[img].get(it)
            if rec and rec["present"] and rec["box"]:
                location = rec["loc"] or region_text(rec["box"], W, H)
                answer.append({"name": it, "present": True, "location": location})
            else:
                answer.append({"name": it, "present": False, "location": None})
        out.append({"image": f"raw/reference_wuzi/{img}",
                    "instruction": INSTRUCTION,
                    "answer": json.dumps(answer, ensure_ascii=False)})

    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_true = sum(1 for r in out for a in json.loads(r["answer"]) if a["present"])
    print(f"✅ 已生成 {OUT_JSONL}：{len(out)} 张图，共 {n_true} 个 present=TRUE 标注")
    print(f"   来源：{src}")
    print("   下一步：python train.py --data data/labeled/train.jsonl "
          "--model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter")


if __name__ == "__main__":
    main()
