# -*- coding: utf-8 -*-
"""把归档里的图片还原到训练脚本期望的位置。

背景
----
`train.jsonl` 里 image 字段写的是 `raw/reference_wuzi/xxx.jpg`（相对 data/ 目录），
但 `data/raw/` 被 .gitignore 排除了，队友 clone 仓库后这个目录不存在，
直接跑训练会报「图片找不到」。

用法
----
    python _scripts/restore_data.py              # 用最新归档
    python _scripts/restore_data.py v2-20261004  # 指定版本

效果：data/archive/<版本>/images/*.jpg  ->  data/raw/reference_wuzi/
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "data" / "archive"
TARGET = ROOT / "data" / "raw" / "reference_wuzi"


def pick_version(arg=None):
    if arg:
        d = ARCHIVE / arg
        if not d.is_dir():
            sys.exit(f"找不到归档版本：{d}")
        return d
    dirs = sorted([d for d in ARCHIVE.iterdir() if d.is_dir()]) if ARCHIVE.exists() else []
    if not dirs:
        sys.exit("data/archive/ 下没有任何归档")
    return dirs[-1]


def main():
    ver = pick_version(sys.argv[1] if len(sys.argv) > 1 else None)
    src = ver / "images"
    if not src.is_dir():
        sys.exit(f"归档里没有 images/：{src}")

    TARGET.mkdir(parents=True, exist_ok=True)
    n_new = n_skip = 0
    for f in sorted(src.iterdir()):
        if f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        dst = TARGET / f.name
        if dst.exists() and dst.stat().st_size == f.stat().st_size:
            n_skip += 1
            continue
        shutil.copy2(f, dst)
        n_new += 1

    total = len([p for p in TARGET.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}])
    print(f"✅ 已从 {ver.name} 还原图片")
    print(f"   新复制 {n_new} 张，已存在跳过 {n_skip} 张")
    print(f"   {TARGET.relative_to(ROOT)} 现有 {total} 张")
    print()
    print("   现在可以训练了：")
    print(f"   python train.py --data data/archive/{ver.name}/train.jsonl ^")
    print("       --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter --epochs 8 --lr 1e-4")


if __name__ == "__main__":
    main()
