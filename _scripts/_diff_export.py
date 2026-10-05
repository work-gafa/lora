# -*- coding: utf-8 -*-
"""对比「当前手标数据重新导出」与「现有 train.jsonl」的差异。

为什么需要：如果手标改过但没重新导出，训练用的就是旧标签。
这个脚本把差异逐图列出来，避免"以为改了其实没生效"。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = r"D:\10604\ANACONDA\envs\lora\python.exe"
CUR = ROOT / "data" / "labeled" / "train.jsonl"
TMP = ROOT / "data" / "labeled" / "_reexport_check.jsonl"


def load(p: Path):
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        ans = json.loads(r["answer"])
        items = ans.get("items", []) if isinstance(ans, dict) else ans
        out[r["image"]] = {
            "scenario": r.get("scenario"),
            "present": {it["name"] for it in items},
        }
    return out


if __name__ == "__main__":
    print("生成一份新的导出到临时文件...")
    subprocess.run([PY, str(ROOT / "_scripts" / "_reexport.py"), "--out", str(TMP)],
                   cwd=str(ROOT), capture_output=True, text=True)

    old = load(CUR)
    new = load(TMP)

    print(f"\n{'=' * 62}")
    print("对比：现有 train.jsonl  vs  当前标注重新导出")
    print("=" * 62)

    only_old = set(old) - set(new)
    only_new = set(new) - set(old)
    if only_old:
        print(f"\n只在旧文件里的图（{len(only_old)}）：")
        for k in sorted(only_old):
            print("   - " + k)
    if only_new:
        print(f"\n只在新导出里的图（{len(only_new)}）：")
        for k in sorted(only_new):
            print("   + " + k)

    n_diff = 0
    tot_old = sum(len(v["present"]) for v in old.values())
    tot_new = sum(len(v["present"]) for v in new.values())

    for img in sorted(set(old) & set(new)):
        o, n = old[img], new[img]
        added = n["present"] - o["present"]
        removed = o["present"] - n["present"]
        scen_chg = (o["scenario"] != n["scenario"])
        if added or removed or scen_chg:
            n_diff += 1
            print(f"\n[{img}]")
            if scen_chg:
                print(f"   场景: {o['scenario']} → {n['scenario']}")
            if added:
                print(f"   + 新增: {'、'.join(sorted(added))}")
            if removed:
                print(f"   - 移出: {'、'.join(sorted(removed))}")

    print(f"\n{'=' * 62}")
    print(f"正样本总数：旧 {tot_old}  →  新 {tot_new}   （差 {tot_new - tot_old:+d}）")
    print(f"有差异的图：{n_diff} / {len(set(old) & set(new))}")
    if n_diff == 0 and not only_old and not only_new:
        print("✅ 完全一致，train.jsonl 是最新的")
    else:
        print("⚠️ 存在差异 —— 需要重新导出（并把归档重做一版）")

    if TMP.exists():
        TMP.unlink()
        print("\n（临时文件已清理）")
