# -*- coding: utf-8 -*-
"""从人工标注重新导出 train.jsonl（离线命令行版，与平台「导出」按钮等价）。

【什么时候用它】
平时导出走标注平台的「导出」按钮（后端 POST /api/export）就够了。
这个脚本用于**不开平台**的场景，例如：
  - 批量重导 / 修完 taxonomy.json 后想直接看结果
  - CI 或脚本化流程
  - 想先 dry-run 看一眼归类和丢弃情况，再决定要不要写文件

【与平台导出的差异】
- 平台导出：按 `data/labeled/manual_annotations.json` + `image_scenarios.json`，
  只导出「annotations 里有键」的图（人工确认过的），会写回 `data/labeled/train.jsonl`。
- 本脚本：逻辑完全对齐平台，额外提供 --out / --dry-run / --csv 便于检查和调试。

【输出格式（v3）】
    {"items": [{"name": "充电宝", "location": "画面右侧"}]}
只列画面里真实看到的物品；「未带」= 该场景清单 − 已列出，由程序算。

用法：
    python _scripts/_reexport.py                     # 导出到 data/labeled/train.jsonl
    python _scripts/_reexport.py --dry-run           # 只看统计，不写文件
    python _scripts/_reexport.py --out /tmp/x.jsonl  # 指定输出路径
    python _scripts/_reexport.py --csv               # 同时导出明细 CSV
"""
import argparse
import csv
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from normalize import normalize_name          # noqa: E402
import prompt as prompt_mod                   # noqa: E402
from PIL import Image                         # noqa: E402

DATA = ROOT / "data"
TAXONOMY_FILE = ROOT / "taxonomy.json"
ANNO_FILE = DATA / "labeled" / "manual_annotations.json"
SCEN_FILE = DATA / "labeled" / "image_scenarios.json"
DEFAULT_OUT = DATA / "labeled" / "train.jsonl"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# 与 _旧版备用_anno-tool/app.py 的 region_text 保持一致（平台用它算 location）
def region_text(box, W, H):
    x1, y1, x2, y2 = [float(v) for v in box]
    if (x2 - x1) * (y2 - y1) > 0.6 * W * H:
        return "整张画面"
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    hx = "左" if cx < W / 3 else ("右" if cx > 2 * W / 3 else "中")
    vy = "上" if cy < H / 3 else ("下" if cy > 2 * H / 3 else "中")
    if hx == "中" and vy == "中":
        return "画面中央"
    if hx == "中":
        return f"画面{vy}方"
    if vy == "中":
        return f"画面{hx}侧"
    return f"画面{vy}{hx}角"


def load_taxonomy(path: Path):
    tax = json.loads(path.read_text(encoding="utf-8"))
    items = tax["items"]
    canon = [it["name"] for it in items]
    item_scen = {it["name"]: list(it.get("scenarios") or ["travel", "school"])
                 for it in items}
    scen_names = tax.get("scenarios") or prompt_mod.SCENARIOS
    category = {it["name"]: it.get("category", "") for it in items}
    return canon, item_scen, scen_names, category


def item_dir(name: str) -> str:
    """图片在 data/ 下的相对路径前缀（与平台 _resolve / 导出规则一致）。"""
    if (DATA / "labeled" / "uploads" / name).exists():
        return "labeled/uploads"
    if (DATA / "raw" / "reference_wuzi" / name).exists():
        return "raw/reference_wuzi"
    return ""


def img_size(name: str):
    for sub in ("labeled/uploads", "raw/reference_wuzi"):
        p = DATA / sub / name
        if p.exists():
            return Image.open(p).convert("RGB").size
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--anno", default=str(ANNO_FILE))
    ap.add_argument("--taxonomy", default=str(TAXONOMY_FILE))
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    ap.add_argument("--csv", action="store_true", help="同时导出明细 CSV")
    args = ap.parse_args()

    canon, item_scen, scen_names, category = load_taxonomy(Path(args.taxonomy))
    anno_path = Path(args.anno)
    if not anno_path.exists():
        sys.exit(f"找不到标注文件：{anno_path}")
    annos = json.loads(anno_path.read_text(encoding="utf-8"))

    img_scen = {}
    if SCEN_FILE.exists():
        img_scen = json.loads(SCEN_FILE.read_text(encoding="utf-8")).get("map", {})

    def items_for(scen):
        picked = [c for c in canon if scen in item_scen.get(c, ["travel", "school"])]
        return picked or list(canon)

    instr = {s: prompt_mod.build_prompt(items_for(s), s) for s in scen_names}

    rows, detail = [], []
    n_present = 0
    dropped = Counter()          # 归不进清单的名字
    off_scenario = Counter()     # 在清单里，但不属于这张图的场景
    skipped_no_bbox = 0
    by_scenario = Counter()
    unmatched_img = []

    for name in sorted(annos.keys()):
        d = item_dir(name)
        if not d:
            unmatched_img.append(name)
            continue
        size = img_size(name)
        if size is None:
            unmatched_img.append(name)
            continue
        W, H = size

        scen = img_scen.get(name, "travel")
        if scen not in scen_names:
            scen = list(scen_names)[0]
        row_canon = items_for(scen)
        by_scenario[scen] += 1

        present = {}
        for i, b in enumerate(annos[name] or [], 1):
            raw = (b.get("name") or "").strip()
            bb = b.get("bbox") or []
            if len(bb) != 4:
                skipped_no_bbox += 1
                continue
            if not raw:
                dropped["(空名字)"] += 1
                continue
            nm = normalize_name(raw) or raw
            if nm not in canon:
                dropped[raw] += 1
                continue
            if nm not in row_canon:
                off_scenario[f"{raw}（{scen} 场景不含）"] += 1
                continue
            if nm in present:
                continue
            px = [bb[0] * W, bb[1] * H, bb[2] * W, bb[3] * H]
            loc = region_text(px, W, H)
            present[nm] = loc
            detail.append(OrderedDict([
                ("image", name), ("scenario", scen), ("box_id", i),
                ("raw_name", raw), ("canonical_name", nm),
                ("category", category.get(nm, "")),
                ("location", loc),
            ]))

        answer = {"items": [{"name": it, "location": present[it]}
                            for it in row_canon if it in present]}
        n_present += len(answer["items"])
        rows.append({
            "image": f"{d}/{name}",
            "scenario": scen,
            "instruction": instr[scen],
            "answer": json.dumps(answer, ensure_ascii=False),
        })

    # ---- 汇报 ----
    print("=" * 60)
    print("重新导出 train.jsonl（v3 格式）")
    print("=" * 60)
    print(f"标注文件      : {anno_path.relative_to(ROOT)}")
    print(f"清单          : {len(canon)} 项 / {len(scen_names)} 场景")
    for s in scen_names:
        print(f"   {s:<8s} {len(items_for(s)):>2d} 项 | {by_scenario.get(s, 0):>2d} 张图")
    print(f"导出图片      : {len(rows)} 张")
    print(f"正样本(present): {n_present} 个")
    print(f"跳过(无 bbox)  : {skipped_no_bbox}")
    if dropped:
        print(f"⚠️ 归不进清单（会被丢弃）: {dict(dropped)}")
    if off_scenario:
        print(f"⚠️ 不属于该图场景（不写入）: {dict(off_scenario)}")
    if unmatched_img:
        print(f"⚠️ 找不到图片文件，已跳过: {unmatched_img}")

    # 按图片列一下正样本数，便于肉眼核对
    print("\n每图正样本数：")
    for r in rows:
        ans = json.loads(r["answer"])["items"]
        names = "、".join(a["name"] for a in ans) or "（空）"
        print(f"   {r['image'].split('/')[-1]:<24s} [{r['scenario']:<6s}] "
              f"{len(ans):>2d} 项  {names}")

    if args.dry_run:
        print("\n（--dry-run，未写入任何文件）")
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    print(f"\n✅ 已写入 {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")

    if args.csv:
        csv_path = out.with_name("labels_detail.csv")
        if detail:
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(detail[0].keys()))
                w.writeheader()
                w.writerows(detail)
            print(f"✅ 明细 CSV 已写入 {csv_path.name}")


if __name__ == "__main__":
    main()
