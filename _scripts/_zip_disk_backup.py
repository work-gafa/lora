#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 网盘备份/ 打包成一个 zip，方便直接上传网盘 / 发给组员。"""
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "网盘备份"
OUT = ROOT / f"luggage-agent_网盘备份_{datetime.now():%Y%m%d}.zip"

if not SRC.is_dir():
    sys.exit("找不到 网盘备份/，先跑 _scripts/_make_disk_backup.py")

n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(SRC.rglob("*")):
        if p.is_file():
            arc = Path("luggage-agent") / p.relative_to(SRC)
            z.write(p, str(arc))
            n += 1

size = OUT.stat().st_size / 1024 / 1024
print(f"✅ 已打包：{OUT.name}")
print(f"   文件 {n} 个，压缩后 {size:.1f} MB")
