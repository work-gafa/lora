# -*- coding: utf-8 -*-
"""按「白名单」把当前版本同步到 网盘备份/（纯工程 + 最新归档，不含个人文档/大文件）。

为什么要用脚本而不是手动拖：
  手拖很容易漏掉新增文件、或误带 148MB 适配器 / 7.7GB 基座 / 原始照片。
  这里的白名单与 .gitignore 保持同一套口径，改完一键重跑即可。

用法：
    python _scripts/_make_disk_backup.py            # 全量重建（会先挪走旧备份）
    python _scripts/_make_disk_backup.py --check    # 只列出会同步什么，不动文件
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "网盘备份"
ARCHIVE = ROOT / "data" / "archive"

# ---------- 白名单：根目录放哪些文件 ----------
ROOT_FILES = [
    "README.md", ".gitignore", "requirements.txt",
    "taxonomy.json", "normalize.py", "prompt.py",
    "train.py", "infer.py", "validate.py",
    "gdino_detect.py", "gdino_to_train.py",
    "download_model.py", "download_gdino.py",
    "validate_report.json",
    "启动标注平台.bat",
]

# ---------- 白名单：整目录复制 ----------
ROOT_DIRS = [
    "anno-tool",           # 新标注平台（backend + web，含本地 vendor）
    "_旧版备用_anno-tool",  # 新版 AI 预标依赖它（必须保持直接子目录）
    "_scripts",            # 工具脚本
]

# ---------- 明确排除（哪怕在目录里也不复制）----------
EXCLUDE_DIRS = {"__pycache__", ".ipynb_checkpoints", "_trash", "_backup", "vendor"}
# 注意 vendor 要单独处理：anno-tool/web/vendor 是前端库，必须保留；
# 上面的 EXCLUDE_DIRS 只用在对 _scripts 之类做过滤，anno-tool 单独走完整复制。
GLOBAL_EXCLUDE_FILES = {".DS_Store", "Thumbs.db"}
GLOBAL_EXCLUDE_PATTERNS = (".bak", ".log", ".pyc")


def newest_archive():
    dirs = sorted([d for d in ARCHIVE.iterdir() if d.is_dir()]) if ARCHIVE.exists() else []
    return dirs[-1] if dirs else None


def iter_skip(path: Path) -> bool:
    if path.is_dir():
        return path.name in {"__pycache__", ".ipynb_checkpoints", "_trash", "_backup"}
    if path.name in GLOBAL_EXCLUDE_FILES:
        return True
    return path.name.endswith(GLOBAL_EXCLUDE_PATTERNS)


def copy_tree(src: Path, dst: Path, skip_vendor: bool = False) -> int:
    n = 0
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if any(part == "__pycache__" or part == ".ipynb_checkpoints"
               for part in rel.parts):
            continue
        if p.name in GLOBAL_EXCLUDE_FILES or p.name.endswith(GLOBAL_EXCLUDE_PATTERNS):
            continue
        if skip_vendor and "vendor" in rel.parts:
            continue
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif p.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            n += 1
    return n


def main():
    check_only = "--check" in sys.argv
    ver = newest_archive()
    if ver is None:
        sys.exit("data/archive/ 下没有归档，先跑 _scripts/_archive.py")

    plan = []
    for f in ROOT_FILES:
        if (ROOT / f).is_file():
            plan.append((ROOT / f, DST / f))
        else:
            print(f"   ⚠️ 白名单里的文件不存在，跳过：{f}")

    print(f"== 将同步到 {DST.name}/ ==")
    print(f"   工程文件 {len(plan)} 个")
    for d in ROOT_DIRS:
        print(f"   目录 {d}/")
    print(f"   归档 data/archive/{ver.name}/ （仅最新一版）")

    if check_only:
        print("\n（--check 模式，未改动任何文件）")
        return

    # 1) 旧备份挪走（不真删，避免 safe-delete 拦截；确认无误后可自行删）
    if DST.exists():
        old = ROOT / f"网盘备份_旧_{datetime.now():%Y%m%d-%H%M%S}"
        shutil.move(str(DST), str(old))
        print(f"\n   旧备份已挪到：{old.name}/（确认无误后可删除）")
    DST.mkdir(parents=True, exist_ok=True)

    # 2) 根文件
    for src, dst in plan:
        shutil.copy2(src, dst)
    n_files = len(plan)

    # 3) 整目录
    for d in ROOT_DIRS:
        src = ROOT / d
        if not src.is_dir():
            print(f"   ⚠️ 目录不存在，跳过：{d}")
            continue
        n_files += copy_tree(src, DST / d)

    # 4) 最新归档（原样整目录复制）
    n_files += copy_tree(ver, DST / "data" / "archive" / ver.name)

    # 5) 给备份单独塞一份「这是哪一版」的说明
    (DST / "_版本说明.md").write_text(
        f"# 网盘备份 · {ver.name}\n\n"
        f"同步时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
        f"这是 luggage-agent 当前版本的**纯工程快照**（代码 + 最新标注归档）。\n\n"
        f"- 归档版本：`data/archive/{ver.name}/`\n"
        f"- 清单：`taxonomy.json`（32 项 / 2 场景）\n"
        f"- 标注平台：`anno-tool/`（双击 `启动标注平台.bat` 启动，端口 8004）\n\n"
        "## 用之前先做三件事\n\n"
        "```bat\n"
        ":: 1. 建环境\n"
        "conda create -n lora python=3.10 -y\n"
        "conda activate lora\n"
        "pip install torch==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128\n"
        "pip install -r requirements.txt\n\n"
        ":: 2. 下基座模型（约 7.7GB，本备份不含）\n"
        "pip install -U \"huggingface_hub[cli]\"\n"
        "set HF_ENDPOINT=https://hf-mirror.com\n"
        "set HF_HUB_DISABLE_XET=1\n"
        "hf download Qwen/Qwen2.5-VL-3B-Instruct --local-dir vlm/qwen2.5-vl-3b-instruct\n\n"
        ":: 3. 还原训练图片（必做）\n"
        "python _scripts/restore_data.py\n"
        "```\n\n"
        "**不含**：基座权重（7.7GB）、LoRA 适配器（148MB）、原始照片、本地日志。\n"
        "适配器请单独找作者要（或走 GitHub Releases）。\n",
        encoding="utf-8")

    size = sum(p.stat().st_size for p in DST.rglob("*") if p.is_file())
    print(f"\n✅ 网盘备份已重建：{DST.relative_to(ROOT)}")
    print(f"   文件 {n_files + 1} 个，合计 {size / 1024 / 1024:.1f} MB")
    print(f"   归档：data/archive/{ver.name}/")
    print("\n   下一步：把 网盘备份/ 整个压缩上传网盘即可。")


if __name__ == "__main__":
    main()
