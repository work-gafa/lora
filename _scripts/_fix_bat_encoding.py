# -*- coding: utf-8 -*-
"""把 .bat 文件统一转成 GBK + CRLF。

背景：用编辑器/工具写 .bat 很容易落成 UTF-8，Windows 命令行按 GBK 解读，
中文全变乱码（甚至命令都执行不了）。这个脚本做幂等转换，可反复跑。

用法：
    python _scripts/_fix_bat_encoding.py                # 转换项目内所有 .bat
    python _scripts/_fix_bat_encoding.py 启动标注平台.bat
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"

# 跳过这些目录
SKIP_DIRS = {"__pycache__", "_trash", ".git", "个人留存_继续用"}


def already_gbk(raw: bytes) -> bool:
    try:
        raw.decode("gbk")
    except UnicodeDecodeError:
        return False
    # 能按 GBK 解出来还不够：真有中文的 GBK 文件通常解不出合法 UTF-8
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return True          # 只能 GBK → 已是 GBK
    return False             # 两者都能解 → 纯 ASCII，无需处理


def convert(path: Path, force: bool = False) -> str:
    raw = path.read_bytes()
    if raw.startswith(BOM):
        raw = raw[len(BOM):]

    if not force:
        try:
            text = raw.decode("gbk")
            raw.decode("utf-8")
            if already_gbk(raw):
                return "已是 GBK，跳过"
        except UnicodeDecodeError:
            pass

    # 统一先按 utf-8 解（含 BOM 已去掉），失败则按 gbk 解
    try:
        text = raw.decode("utf-8")
        src = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("gbk")
        src = "gbk"

    if src == "gbk":
        out = raw
    else:
        out = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("gbk")

    if out == path.read_bytes():
        return "无需改动"
    path.write_bytes(out)
    return f"{src} → GBK + CRLF"


def main():
    if len(sys.argv) > 1:
        targets = [ROOT / a for a in sys.argv[1:]]
    else:
        targets = [p for p in ROOT.rglob("*.bat")
                   if not any(d in p.parts for d in SKIP_DIRS)]

    for p in sorted(targets):
        if not p.is_file():
            print(f"   跳过（不存在）：{p}")
            continue
        msg = convert(p)
        # 校验
        chk = "✅" if _is_ok(p) else "❌"
        print(f" {chk} {p.relative_to(ROOT)}  ::  {msg}")


def _is_ok(p: Path) -> bool:
    raw = p.read_bytes()
    if b"chcp" in raw:
        return False
    try:
        raw.decode("gbk")
    except UnicodeDecodeError:
        return False
    return b"\r\n" in raw


if __name__ == "__main__":
    main()
