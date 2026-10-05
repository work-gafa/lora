# -*- coding: utf-8 -*-
"""把归档里的图片还原到训练脚本期望的位置。

背景
----
`train.jsonl` 里 image 字段写的是相对 `data/` 的路径，例如：
  - `raw/reference_wuzi/小红书参考5.jpg`   （预设图集）
  - `labeled/uploads/小红书补充7.jpg`      （平台上上传的图）

但 `data/raw/` 和 `data/labeled/uploads/` 都被 .gitignore 排除了，
队友 clone 仓库后这两个目录不存在，直接跑训练会报「图片找不到」。

用法
----
    python _scripts/restore_data.py              # 用最新归档
    python _scripts/restore_data.py v3-20261005  # 指定版本

效果：把 `data/archive/<版本>/images/**` 原样覆盖回 `data/**`
（归档里保留了相对结构，所以一个循环就够）。
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARCHIVE = DATA / "archive"

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


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

    n_new = n_skip = 0
    per_dir = {}
    for f in sorted(src.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in IMG_EXT:
            continue
        rel = f.relative_to(src)          # 例：raw/reference_wuzi/x.jpg
        dst = DATA / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_size == f.stat().st_size:
            n_skip += 1
        else:
            shutil.copy2(f, dst)
            n_new += 1
        key = str(rel.parent).replace("\\", "/")
        per_dir[key] = per_dir.get(key, 0) + 1

    print(f"✅ 已从 {ver.name} 还原图片")
    print(f"   新复制 {n_new} 张，已存在跳过 {n_skip} 张")
    for k, v in sorted(per_dir.items()):
        print(f"   data/{k}/  {v} 张")
    print()
    print("   现在可以训练了：")
    print(f"   python train.py --data data/archive/{ver.name}/train.jsonl ^")
    print("       --model vlm/qwen2.5-vl-3b-instruct --out output/lora-adapter ^")
    print("       --epochs 16 --lr 1e-4")


if __name__ == "__main__":
    main()
