# -*- coding: utf-8 -*-
"""把已标注的图片 + 对应表格整理成一份干净归档（只读源，不删不改原文件）。

产物：data/archive/<版本>/
  images/              原图副本（**保持 data/ 下的相对结构**，便于一键还原）
  overlays/            框可视化副本（仅预设图有）
  labels_detail.csv    明细表：每个手标框一行（原始名 -> 规范名）
  labels_matrix.csv    矩阵表：图 x 清单项，值为 present 时的位置描述
  labels_stats.csv     统计表：每项的正样本数 / 覆盖图数 / 别名 / 归属场景
  labels_by_scenario.csv 场景分布表
  train.jsonl          训练数据副本
  taxonomy.json        清单副本
  image_scenarios.json 每张图的场景副本
  manual_annotations.json 原始手标框
  MANIFEST.md          归档说明

用法：
  python _scripts/_archive.py v3-20261005
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
ITEMS = TAXONOMY["items"]
SCEN_NAMES = TAXONOMY.get("scenarios") or {"travel": "出门旅行 / 旅游",
                                          "school": "上学 / 回家"}
SCEN_OF_ITEM = {it["name"]: list(it.get("scenarios") or ["travel", "school"]) for it in ITEMS}

TRAIN = DATA / "labeled" / "train.jsonl"
MANUAL = DATA / "labeled" / "manual_annotations.json"
IMG_SCEN = DATA / "labeled" / "image_scenarios.json"
OVERLAYS = DATA / "labeled" / "overlays"

VERSION = sys.argv[1] if len(sys.argv) > 1 else "v3-20261005"
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
    """兼容新格式 {"items":[{name,location}]} 与旧格式 [{name,present,location}]。

    返回 (present_location_map, format_tag)
    """
    if isinstance(ans, str):
        ans = json.loads(ans)
    if isinstance(ans, dict):
        return {it["name"]: (it.get("location") or "(在画面中)")
                for it in ans.get("items", [])}, "items"
    return {it["name"]: (it.get("location") or "(在画面中)")
            for it in ans if it.get("present")}, "legacy"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    (OUT / "overlays").mkdir(exist_ok=True)

    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    train_rows = read_jsonl(TRAIN)
    img_scen = {}
    if IMG_SCEN.exists():
        img_scen = json.loads(IMG_SCEN.read_text(encoding="utf-8")).get("map", {})

    # ---------- 1. 明细表：每个手标框一行 ----------
    detail = []
    per_item_boxes = Counter()
    for img in sorted(manual.keys()):
        for i, box in enumerate(manual[img] or [], 1):
            raw = (box.get("name") or "").strip()
            canon = normalize_name(raw)
            bbox = box.get("bbox") or []
            bb = [round(v, 4) for v in bbox] if len(bbox) == 4 else []
            detail.append(OrderedDict([
                ("image", img),
                ("scenario", img_scen.get(img, "")),
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

    # ---------- 2. 矩阵表：图 x 清单项 ----------
    matrix = []
    present_counter = Counter()
    scen_counter = Counter()
    scen_present = Counter()      # 按「图片所属场景」统计正样本，不重复计共享项
    for row in train_rows:
        img = os.path.basename(row["image"])
        scen = row.get("scenario") or img_scen.get(img, "travel")
        scen_counter[scen] += 1
        present_map, _fmt = parse_answer(row["answer"])
        scen_present[scen] += len(present_map)
        cells = OrderedDict([("image", img), ("scenario", scen)])
        for name in CANON:
            if name in present_map:
                cells[name] = present_map[name]
                present_counter[name] += 1
            else:
                cells[name] = ""
        cells["present_count"] = sum(1 for k in CANON if cells[k])
        matrix.append(cells)

    with open(OUT / "labels_matrix.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(matrix[0].keys()))
        w.writeheader()
        w.writerows(matrix)

    # ---------- 3. 统计表 ----------
    stats = []
    for item in ITEMS:
        name = item["name"]
        covered = sum(1 for row in matrix if row.get(name))
        stats.append(OrderedDict([
            ("canonical_name", name),
            ("category", item.get("category", "")),
            ("english", item.get("en", "")),
            ("scenarios", "/".join(SCEN_OF_ITEM.get(name, []))),
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

    # ---------- 3b. 场景分布表 ----------
    scen_rows = []
    for s, sname in SCEN_NAMES.items():
        s_items = [n for n in CANON if s in SCEN_OF_ITEM.get(n, [])]
        scen_rows.append(OrderedDict([
            ("scenario", s),
            ("中文名", sname),
            ("清单项数", len(s_items)),
            ("图片数", scen_counter.get(s, 0)),
            ("present_次数", scen_present.get(s, 0)),
            ("清单项", "、".join(s_items)),
        ]))
    with open(OUT / "labels_by_scenario.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(scen_rows[0].keys()))
        w.writeheader()
        w.writerows(scen_rows)

    # ---------- 4. 复制图片 / overlays / 数据文件 ----------
    # ★ images/ 内保持 data/ 下的相对结构（raw/reference_wuzi/…、labeled/uploads/…），
    #   这样 restore_data.py 只要把 images/** 覆盖回 data/** 就能一键还原。
    n_img = n_ov = 0
    missing = []
    for row in train_rows:
        rel = row["image"]                       # 例：raw/reference_wuzi/x.jpg
        src = DATA / rel
        if src.exists():
            dst = OUT / "images" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n_img += 1
        else:
            missing.append(rel)

        stem = Path(rel).stem
        ov_src = OVERLAYS / f"{stem}_bbox.jpg"
        if ov_src.exists():
            shutil.copy2(ov_src, OUT / "overlays" / ov_src.name)
            n_ov += 1

    shutil.copy2(TRAIN, OUT / "train.jsonl")
    shutil.copy2(ROOT / "taxonomy.json", OUT / "taxonomy.json")
    shutil.copy2(MANUAL, OUT / "manual_annotations.json")
    if IMG_SCEN.exists():
        shutil.copy2(IMG_SCEN, OUT / "image_scenarios.json")

    # ---------- 5. MANIFEST ----------
    total_present = sum(present_counter.values())
    total_boxes = len(detail)
    unmatched = [d for d in detail if d["canonical_name"] == "(未归类)"]
    n_cat = len(set(CATEGORY.values()))

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
        f"| 训练正样本(present) | {total_present} |",
        f"| 清单项数 | {len(CANON)} |",
        f"| 类别数 | {n_cat} |",
        f"| 场景数 | {len(SCEN_NAMES)} |",
        "",
        "## 分场景",
        "",
        "| 场景 | 清单项 | 图片数 | 正样本 |",
        "|---|---|---|---|",
    ]
    for r in scen_rows:
        lines.append(f"| {r['中文名']}（`{r['scenario']}`） | {r['清单项数']} | "
                     f"{r['图片数']} | {r['present_次数']} |")

    lines += [
        "",
        "## 目录说明",
        "",
        "| 路径 | 内容 |",
        "|---|---|",
        "| `images/` | 原图副本，**保留 `data/` 下的相对结构**（`raw/reference_wuzi/`、`labeled/uploads/`） |",
        "| `overlays/` | GroundingDINO 框可视化对照图（仅预设图有） |",
        "| `labels_detail.csv` | 明细表：每个手标框一行，含「原始名 → 规范名」与场景 |",
        "| `labels_matrix.csv` | 矩阵表：图 × 清单项，单元格为 present 时的位置描述 |",
        "| `labels_stats.csv` | 统计表：每项的框数、present 次数、覆盖图片数、归属场景、别名 |",
        "| `labels_by_scenario.csv` | 场景分布表：每个场景的清单项、图片数、正样本 |",
        "| `train.jsonl` | 训练数据副本（image / scenario / instruction / answer） |",
        "| `taxonomy.json` | 本归档对应的清单版本 |",
        "| `image_scenarios.json` | 每张图属于哪个场景 |",
        "| `manual_annotations.json` | 原始手标框数据 |",
        "",
        "## 答案格式（本版本）",
        "",
        "```json",
        '{"items": [{"name": "充电宝", "location": "画面右侧"}]}',
        "```",
        "",
        "**只列画面里真实看到的物品**，不要 `present` 字段；",
        "「未带」= 该场景清单 − 已列出的，由程序计算，不占模型输出长度。",
        "一样都没看到时返回 `{\"items\": []}`。",
        "",
        "> 旧格式（`[{name,present,location}]` 全量）在 `validate.py` 里仍兼容。",
        "",
        "## 数据来源链路",
        "",
        "```",
        "reference_wuzi/ 预设图 + labeled/uploads/ 上传图",
        "  -> gdino_detect.py 自动预标 -> locations_review.csv + overlays/",
        "  -> 标注平台手改              -> manual_annotations.json + image_scenarios.json",
        "  -> normalize.py 别名归类     -> train.jsonl（按图所属场景取清单）",
        "```",
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
        "python _scripts/restore_data.py " + VERSION + "   :: 还原图片到 data/",
        "conda activate lora",
        f"python train.py --data data/archive/{VERSION}/train.jsonl ^",
        "    --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter ^",
        "    --epochs 16 --lr 1e-4",
        "python validate.py --adapter output/lora-adapter --taxonomy taxonomy.json ^",
        f"    --data data/archive/{VERSION}/train.jsonl",
        "```",
        "",
    ]
    (OUT / "MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")

    # ---------- 6. 控制台汇报 ----------
    print(f"✅ 归档完成 -> {OUT.relative_to(ROOT)}")
    print(f"   图片 {n_img} 张 | overlays {n_ov} 张")
    print(f"   手标框 {total_boxes} 个 | 未归类 {len(unmatched)} 个")
    print(f"   训练正样本 present : {total_present}")
    print(f"   清单 {len(CANON)} 项 / {n_cat} 类 / {len(SCEN_NAMES)} 场景")
    for r in scen_rows:
        print(f"     {r['中文名']:<12s} {r['清单项数']:>2d} 项 | "
              f"{r['图片数']:>2d} 张图 | {r['present_次数']:>3d} 正样本")
    if missing:
        print("   ⚠️ 缺失图片:", missing)
    print()
    print("   present 次数 TOP10:")
    for r in stats[:10]:
        print(f"     {r['canonical_name']:<10s} {r['present_次数']:>2d} 次 / {r['覆盖率']} 图")


if __name__ == "__main__":
    main()
