"""
luggage-agent/validate.py
==========================
用训练好的 LoRA 适配器在「训练集（或任意 jsonl）」上做验证：
把模型输出的「带齐情况 JSON」与 train.jsonl 里的 ground truth 逐物品比对，
报告整体准确率、每类精确率/召回率/F1，以及最常被漏带(FN)/误报(FP) 的物品。

实现上**复用 infer.py** 的 load_model / infer_one / try_parse_json，保证与推理完全一致。

运行：
  python validate.py --adapter output/lora-adapter
  python validate.py --data data/labeled/train.jsonl --adapter output/lora-adapter
  python validate.py --data data/labeled/train.jsonl --adapter output/lora-adapter --report validate_report.json
"""
import argparse
import json
import os
from collections import Counter

from infer import load_model, infer_one, try_parse_json

BASE = os.path.dirname(os.path.abspath(__file__))


def load_ground_truth(jsonl_path):
    """读 train.jsonl，每行 answer 是 JSON 字符串 → 解析成 {name: present}。"""
    rows = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            gt_map = {}
            for it in json.loads(r["answer"]):
                gt_map[it["name"]] = bool(it["present"])
            rows.append({"image": r["image"], "gt": gt_map})
    return rows


def f1_of(s):
    p = s["tp"] / max(1, s["tp"] + s["fp"])
    r = s["tp"] / max(1, s["tp"] + s["fn"])
    return 2 * p * r / max(1e-9, p + r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/labeled/train.jsonl")
    ap.add_argument("--model", default="vlm/qwen2.5-vl-3b-instruct")
    ap.add_argument("--adapter", default="output/lora-adapter")
    ap.add_argument("--data_root", default="data")
    # 清单默认取项目根 taxonomy.json（与训练/推理/平台同一来源 22 项）
    ap.add_argument("--taxonomy", default="taxonomy.json")
    ap.add_argument("--scenario", default="")
    ap.add_argument("--report", default="validate_report.json")
    args = ap.parse_args()

    with open(args.taxonomy, encoding="utf-8") as f:
        tax = json.load(f)
    # 兼容两种结构：根 taxonomy.json 用 items；旧 demo/taxonomy.json 用 scenarios
    if "items" in tax:
        canon = [it["name"] if isinstance(it, dict) else it for it in tax["items"]]
    else:
        canon = tax["scenarios"][args.scenario]["items"]

    gt_rows = load_ground_truth(args.data)
    print(f">> 待验证 {len(gt_rows)} 张，物品 {len(canon)} 类")

    model, processor = load_model(
        args.model, args.adapter if os.path.exists(args.adapter) else None
    )

    # 每类累计 TP/FP/FN/TN
    stat = {c: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for c in canon}
    noise = []          # 模型输出但不在 canon 里的名字（噪声）
    per_image = []

    for r in gt_rows:
        ipath = os.path.join(args.data_root, r["image"])
        if not os.path.exists(ipath):
            print("  缺图跳过：", r["image"])
            continue
        raw = infer_one(ipath, canon, model, processor)
        pred = try_parse_json(raw, canon=canon)
        pred_map = {}
        if pred:
            for it in pred:
                nm = it.get("name")
                pv = bool(it.get("present"))
                if nm in canon:
                    pred_map[nm] = pv
                else:
                    noise.append(nm)
        img_stat = {}
        for c in canon:
            g = r["gt"].get(c, False)
            p = pred_map.get(c, False)
            if p and g:
                stat[c]["tp"] += 1; img_stat[c] = "TP"
            elif p and not g:
                stat[c]["fp"] += 1; img_stat[c] = "FP"
            elif (not p) and g:
                stat[c]["fn"] += 1; img_stat[c] = "FN"
            else:
                stat[c]["tn"] += 1; img_stat[c] = "TN"
        per_image.append({"image": r["image"], "stat": img_stat})

    # ---- 汇总 ----
    tot = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for c in canon:
        for k in tot:
            tot[k] += stat[c][k]
    n = sum(tot.values())
    acc = (tot["tp"] + tot["tn"]) / max(1, n)
    prec = tot["tp"] / max(1, tot["tp"] + tot["fp"])
    rec = tot["tp"] / max(1, tot["tp"] + tot["fn"])
    f1 = 2 * prec * rec / max(1e-9, prec + rec)

    print("\n================ 验证结果 ================")
    print(f"整体(逐物)准确率   : {acc * 100:.1f}%   ({n} 个判定)")
    print(f"present 类 精确率 P : {prec * 100:.1f}%")
    print(f"present 类 召回率 R : {rec * 100:.1f}%")
    print(f"present 类 F1      : {f1 * 100:.1f}%")

    print("\n-- 每类（按 F1 升序，问题最大的在前）--")
    rows_out = []
    for c in sorted(canon, key=lambda x: f1_of(stat[x])):
        s = stat[c]
        p = s["tp"] / max(1, s["tp"] + s["fp"])
        r = s["tp"] / max(1, s["tp"] + s["fn"])
        f = f1_of(s)
        flag = "  ⚠" if f < 0.5 else ""
        print(f"  {c:<10} P={p * 100:5.1f}% R={r * 100:5.1f}% F1={f * 100:5.1f}%"
              f"  (TP{s['tp']} FP{s['fp']} FN{s['fn']} TN{s['tn']}){flag}")
        rows_out.append({"item": c, "P": round(p, 3), "R": round(r, 3),
                         "F1": round(f, 3),
                         "tp": s["tp"], "fp": s["fp"], "fn": s["fn"], "tn": s["tn"]})

    top_fn = [c for c in sorted(canon, key=lambda x: -stat[x]["fn"]) if stat[c]["fn"] > 0][:5]
    top_fp = [c for c in sorted(canon, key=lambda x: -stat[x]["fp"]) if stat[c]["fp"] > 0][:5]
    print("\n最常漏带(FN 最多)：", ", ".join(f"{c}({stat[c]['fn']})" for c in top_fn) or "无")
    print("最常误报(FP 最多)：", ", ".join(f"{c}({stat[c]['fp']})" for c in top_fp) or "无")
    if noise:
        print("模型输出但非规范项(噪声)：", dict(Counter(noise)))

    report = {
        "overall": {"accuracy": round(acc, 3), "precision": round(prec, 3),
                    "recall": round(rec, 3), "f1": round(f1, 3), "totals": tot},
        "per_item": rows_out,
        "per_image": per_image,
        "noise": dict(Counter(noise)) if noise else {},
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n✅ 报告已写：", args.report)


if __name__ == "__main__":
    main()
