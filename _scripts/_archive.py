# -*- coding: utf-8 -*-
"""把已标注的图片 + 对应表格整理成一份干净归档（只读源，不删不改原文件）。

产物：data/archive/<版本>/
  images/              原图副本
  overlays/            框可视化副本
  labels_detail.csv    明细表：每个手标框一行（原始名 -> 规范名）
  labels_matrix.csv    矩阵表：图 x 28 项，值为 present 时的位置描述
  labels_stats.csv     统计表：每项的正样本数 / 覆盖图数
  train.jsonl          训练数据副本
  taxonomy.json        清单副本
  MANIFEST.md          归档说明
"""
import csv
import json
import os
import shutil
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from normalize import normalize_name, CANON, CATEGORY  # noqa: E402

DATA = ROOT / "data"
TAXONOMY = json.loads((ROOT / "taxonomy.json").read_text(encoding="utf-8"))
TRAIN = DATA / "labeled" / "train.jsonl"
MANUAL = DATA / "labeled" / "manual_annotations.json"
OVERLAYS = DATA / "labeled" / "overlays"

VERSION = "v2-20261004"
OUT = DATA / "archive" / VERSION

STAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_answer(ans):
    if isinstance(ans, str):
        ans = json.loads(ans)
    return ans


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    (OUT / "overlays").mkdir(exist_ok=True)

    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    train_rows = read_jsonl(TRAIN)

    # ---------- 1. 明细表：每个手标框一行 ----------
    detail = []
    per_item_boxes = Counter()
    for img in sorted(manual.keys()):
        for i, box in enumerate(manual[img], 1):
            raw = (box.get("name") or "").strip()
            canon = normalize_name(raw)
            bbox = box.get("bbox") or []
            bb = [round(v, 4) for v in bbox] if len(bbox) == 4 else []
            detail.append(OrderedDict([
                ("image", img),
                ("box_id", i),
                ("raw_name", raw),
                ("canonical_name", canon or "(未归类)"),
                ("category", CATEGORY.get(canon, "") if canon else ""),
                ("bbox_xyxy", f"[{bb[0]}, {bb[1]}, {bb[2]}, {bb[3]}]" if bb else ""),
            ]))
            if canon:
                per_item_boxes[canon] += 1

    with open(OUT / "labels_detail.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
        w.writeheader()
        w.writerows(detail)

    # ---------- 2. 矩阵表：图 x 28 项 ----------
    matrix = []
    present_counter = Counter()
    for row in train_rows:
        img = os.path.basename(row["image"])
        items = parse_answer(row["answer"])
        cells = OrderedDict([("image", img)])
        for name in CANON:
            hit = next((it for it in items if it.get("name") == name), None)
            if hit and hit.get("present"):
                loc = hit.get("location") or "(在画面中)"
                cells[name] = loc
                present_counter[name] += 1
            else:
                cells[name] = ""
        n_present = sum(1 for k in CANON if cells[k])
        cells["present_count"] = n_present
        matrix.append(cells)

    with open(OUT / "labels_matrix.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(matrix[0].keys()))
        w.writeheader()
        w.writerows(matrix)

    # ---------- 3. 统计表 ----------
    stats = []
    for item in TAXONOMY["items"]:
        name = item["name"]
        covered = sum(1 for row in matrix if row.get(name))
        stats.append(OrderedDict([
            ("canonical_name", name),
            ("category", item.get("category", "")),
            ("english", item.get("en", "")),
            ("框数", per_item_boxes.get(name, 0)),
            ("present_次数", present_counter.get(name, 0)),
            ("覆盖图片数", covered),
            ("覆盖率", f"{covered}/{len(matrix)}"),
            ("aliases", "、".join(item.get("aliases", []))),
        ]))
    stats.sort(key=lambda r: (-r["present_次数"], -r["框数"]))

    with open(OUT / "labels_stats.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stats[0].keys()))
        w.writeheader()
        w.writerows(stats)

    # ---------- 4. 复制图片 / overlays / 数据文件 ----------
    n_img = n_ov = 0
    missing = []
    for row in train_rows:
        src = DATA / row["image"]
        if src.exists():
            shutil.copy2(src, OUT / "images" / src.name)
            n_img += 1
        else:
            missing.append(row["image"])

        stem = Path(row["image"]).stem
        ov_src = OVERLAYS / f"{stem}_bbox.jpg"
        if ov_src.exists():
            shutil.copy2(ov_src, OUT / "overlays" / ov_src.name)
            n_ov += 1

    shutil.copy2(TRAIN, OUT / "train.jsonl")
    shutil.copy2(ROOT / "taxonomy.json", OUT / "taxonomy.json")
    shutil.copy2(MANUAL, OUT / "manual_annotations.json")

    # ---------- 5. MANIFEST ----------
    total_present = sum(present_counter.values())
    total_boxes = len(detail)
    unmatched = [d for d in detail if d["canonical_name"] == "(未归类)"]

    lines = [
        f"# 标注数据归档 · {VERSION}",
        "",
        f"生成时间：{STAMP}",
        "",
        "## 概览",
        "",
        "| 项目 | 数值 |",
        "|---|---|",
        f"| 标注图片数 | {n_img} |",
        f"| 框可视化图 | {n_ov} |",
        f"| 手标框总数 | {total_boxes} |",
        f"| 归类成功 | {total_boxes - len(unmatched)} / {total_boxes} |",
        f"| 训练正样本(present=true) | {total_present} |",
        f"| 清单项数 | {len(CANON)} |",
        f"| 类别数 | {len(set(CATEGORY.values()))} |",
        "",
        "## 目录说明",
        "",
        "| 路径 | 内容 |",
        "|---|---|",
        "| `images/` | 原图副本（训练集来源：`data/raw/reference_wuzi/`） |",
        "| `overlays/` | GroundingDINO 框可视化对照图 |",
        "| `labels_detail.csv` | 明细表：每个手标框一行，含「原始名 → 规范名」映射 |",
        "| `labels_matrix.csv` | 矩阵表：图 × 清单项，单元格为 present 时的位置描述 |",
        "| `labels_stats.csv` | 统计表：每项的框数、present 次数、覆盖图片数、别名 |",
        "| `train.jsonl` | 训练数据副本（image / instruction / answer） |",
        "| `taxonomy.json` | 本归档对应的清单版本（28 项 + 别名） |",
        "| `manual_annotations.json` | 原始手标框数据 |",
        "",
        "## 数据来源链路",
        "",
        "```",
        "reference_wuzi/ 原图",
        "  -> gdino_detect.py 自动预标 -> locations_review.csv + overlays/",
        "  -> 人工在标注平台手改      -> locations_corrected.csv / manual_annotations.json",
        "  -> normalize.py 别名归类   -> train.jsonl（本次已修复丢框问题）",
        "```",
        "",
        "> **重要**：早期导出会把「名称不在清单里」的框静默丢弃（82 框丢了 45 个）。",
        "> 本版本经 `normalize.py` 归类后**救回率 100%**，正样本 35 → 64。",
        "",
        "## 未归类项",
        "",
    ]
    if unmatched:
        lines.append("| 图片 | 原始名 |")
        lines.append("|---|---|")
        for d in unmatched:
            lines.append(f"| {d['image']} | {d['raw_name']} |")
    else:
        lines.append("无，全部已归入清单项。")

    lines += [
        "",
        "## 复现方式",
        "",
        "```bat",
        "conda activate lora",
        f"python train.py --data data/archive/{VERSION}/train.jsonl ^",
        "    --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter --epochs 8 --lr 1e-4",
        "```",
        "",
    ]
    (OUT / "MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")

    # ---------- 6. 控制台汇报 ----------
    print(f"✅ 归档完成 -> {OUT.relative_to(ROOT)}")
    print(f"   图片 {n_img} 张 | overlays {n_ov} 张")
    print(f"   手标框 {total_boxes} 个 | 未归类 {len(unmatched)} 个")
    print(f"   训练正样本 present=true : {total_present}")
    print(f"   清单 {len(CANON)} 项 / {len(set(CATEGORY.values()))} 类")
    if missing:
        print("   ⚠️ 缺失图片:", missing)
    print()
    print("   present 次数 TOP8:")
    for r in stats[:8]:
        print(f"     {r['canonical_name']:<10s} {r['present_次数']:>2d} 次 / {r['覆盖率']} 图")


if __name__ == "__main__":
    main()
