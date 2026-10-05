# -*- coding: utf-8 -*-
"""项目卫生工具：找出并清理冗余文件。

分两类：
  【可以随便清】再生成本为零 —— 日志、脚本备份、Python 缓存、回收站、临时工具脚本
  【要先确认】体积大或可能还想留着 —— 旧 LoRA 适配器备份、训练中间 checkpoint、
               GDINO 中间产物、demo/、旧过程文档

用法：
    python _scripts/clean_project.py                     # 只报告，不动文件
    python _scripts/clean_project.py --apply safe        # 清「可以随便清」那类
    python _scripts/clean_project.py --apply intermediate # 清指定类（需显式点名）
    python _scripts/clean_project.py --apply all         # 全清（含大文件，谨慎）
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 不在这两个目录里动任何东西
SKIP_TOP = {"网盘备份", "个人留存_继续用", ".git", ".workbuddy", "vlm"}

# 「可以随便清」—— 再生成本为零
SAFE = {
    "logs": [ROOT / "anno_tool.log", ROOT / "infer_val.log", ROOT / "train.log"],
    "bak": [ROOT / "infer.py.bak", ROOT / "train.py.bak"],
    "pycache": [
        ROOT / "__pycache__",
        ROOT / "anno-tool" / "backend" / "__pycache__",
        ROOT / "_旧版备用_anno-tool" / "__pycache__",
        ROOT / "_scripts" / "__pycache__",
    ],
    # 这两个是回收站：里面都是之前删掉的东西
    "trash": [ROOT / "_trash", ROOT / "data" / "labeled" / "_trash"],
    # 调试/一次性诊断脚本（功能已并入 clean_project.py 或已完成使命）
    "temp_tools": [
        ROOT / "_scripts" / "_check_bat.py",
        ROOT / "_scripts" / "_measure_startup.py",
        ROOT / "_scripts" / "_run_bat_test.py",
        ROOT / "_scripts" / "_scan_junk.py",
    ],
}

# 「要先确认」—— 大或可能有保存价值
REVIEW = {
    # 旧适配器备份（当前在用的 output/lora-adapter 不在此列！）
    "old_adapters": [
        ROOT / "output" / "_bk_lora-adapter_v1",
        ROOT / "output" / "_bk_lora-adapter_v2",
        ROOT / "output" / "_bk_checkpoint-5",
        ROOT / "output" / "_backup",
    ],
    # 训练中间 checkpoint（只用于「断点续训」，训练已完成则无用）
    "checkpoints": None,      # 运行时展开 output/lora-adapter/checkpoint-*
    # GroundingDINO 预标的中间产物（已被 manual_annotations.json 取代）
    "intermediate": [
        ROOT / "data" / "labeled" / "locations_review.csv",
        ROOT / "data" / "labeled" / "locations_corrected.csv",
        ROOT / "data" / "labeled" / "detections.json",
        ROOT / "data" / "labeled" / "_taxonomy_analysis.json",
    ],
    # 早期交互原型，已被 anno-tool 完全取代
    "demo": [ROOT / "demo"],
    # 早期过程/协作稿
    "process_docs": [ROOT / "个人留存_继续用" / "过程与协作文档"],
}


def size_of(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    tot = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                tot += f.stat().st_size
        except OSError:
            pass
    return tot


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def expand(name: str, items):
    if name == "checkpoints":
        ad = ROOT / "output" / "lora-adapter"
        return sorted(ad.glob("checkpoint-*")) if ad.is_dir() else []
    return [p for p in (items or []) if p.exists()]


def collect(group: dict):
    out = {}
    for k, v in group.items():
        got = expand(k, v)
        if got:
            out[k] = got
    return out


def remove(p: Path) -> str:
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return "已删"
    except OSError as e:
        return f"失败({e.__class__.__name__})"


def report(title: str, groups: dict, verbose: bool = True) -> int:
    print(f"\n{'=' * 64}")
    print(title)
    print("=" * 64)
    total = 0
    for k, items in groups.items():
        sub = sum(size_of(p) for p in items)
        total += sub
        print(f"\n### {k}   ({len(items)} 项 / {human(sub)})")
        if verbose:
            for p in items:
                try:
                    rel = p.relative_to(ROOT)
                except ValueError:
                    rel = p
                print(f"    {human(size_of(p)):>10s}  {rel}")
    print(f"\n小计：{human(total)}")
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", nargs="*", default=None,
                    help="要清理的类别名；'safe'= 安全那组，'all'=全部")
    ap.add_argument("-q", "--quiet", action="store_true", help="不逐条列文件")
    args = ap.parse_args()

    safe_groups = collect(SAFE)
    review_groups = collect(REVIEW)

    t1 = report("[可以随便清] 再生成本为零", safe_groups, not args.quiet)
    t2 = report("[要先确认] 体积大 / 可能还想留着", review_groups, not args.quiet)
    print(f"\n合计可回收：{human(t1 + t2)}")
    print(f"  其中安全部分：{human(t1)}")
    print(f"  其中需确认部分：{human(t2)}")

    if args.apply is None:
        print("\n（未加 --apply，什么都没删。加 --apply safe 清安全那组）")
        sys.exit(0)

    targets = args.apply
    if not targets:
        targets = ["safe"]

    picked = {}
    if "all" in targets:
        picked = {**safe_groups, **review_groups}
    else:
        if "safe" in targets:
            picked.update(safe_groups)
        for k in targets:
            if k == "safe":
                continue
            if k in safe_groups:
                picked[k] = safe_groups[k]
            elif k in review_groups:
                picked[k] = review_groups[k]
            else:
                print(f"⚠️ 未知类别：{k}")

    if not picked:
        print("没有要清理的内容。")
        sys.exit(0)

    print(f"\n{'=' * 64}")
    print("开始清理")
    print("=" * 64)
    freed = 0
    for k, items in picked.items():
        print(f"\n### {k}")
        for p in items:
            s = size_of(p)
            msg = remove(p)
            if msg == "已删":
                freed += s
            try:
                rel = p.relative_to(ROOT)
            except ValueError:
                rel = p
            print(f"    [{msg}] {rel}  ({human(s)})")

    print(f"\n✅ 清理完成，回收 {human(freed)}")
