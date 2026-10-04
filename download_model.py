"""
luggage-agent/download_model.py
直接用 requests 从 HF 镜像拉取 Qwen2.5-VL-3B-Instruct，绕过 huggingface_hub 的临时文件删除
（WorkBuddy 沙箱的 safe-delete 钩子会拦截 unlink 导致下载中断）。
支持 HTTP Range 断点续传，适合不稳定的镜像。

运行（在 luggage-agent 目录下）：
  python download_model.py
"""
import os
import sys
import time
import requests

REPO = "Qwen/Qwen2.5-VL-3B-Instruct"
BASE = "https://hf-mirror.com"
OUT = "vlm/qwen2.5-vl-3b-instruct"
TIMEOUT = 300
RETRIES = 15
CHUNK = 1 << 20  # 1MB


def list_files():
    r = requests.get(f"{BASE}/api/models/{REPO}/tree/main", timeout=TIMEOUT)
    r.raise_for_status()
    return [f["path"] for f in r.json()]


def download(path):
    url = f"{BASE}/{REPO}/resolve/main/{path}"
    local = os.path.join(OUT, *path.split("/"))
    os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
    start = os.path.getsize(local) if os.path.exists(local) else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    for attempt in range(RETRIES):
        try:
            with requests.get(url, headers=headers, stream=True,
                               timeout=TIMEOUT, allow_redirects=True) as r:
                if r.status_code in (403, 404):
                    print("  SKIP", path, r.status_code)
                    return
                if r.status_code not in (200, 206):
                    print("  HTTP", r.status_code, path)
                    raise IOError("bad status")
                # 200 = 从头全量（服务器忽略 Range）→ 覆盖写；206 = 续传 → 追加
                mode = "wb" if (r.status_code == 200 or start == 0) else "ab"
                with open(local, mode) as f:
                    if r.status_code == 206:
                        f.seek(start)
                    for chunk in r.iter_content(CHUNK):
                        if chunk:
                            f.write(chunk)
            print(f"  OK  {path}  ({os.path.getsize(local)/1e6:.1f} MB)")
            return
        except Exception as e:
            print(f"  retry {attempt+1}/{RETRIES} {path}: {e}")
            time.sleep(3)
            if os.path.exists(local):
                start = os.path.getsize(local)
                headers = {"Range": f"bytes={start}-"}
    print("  FAIL", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    files = list_files()
    print(f">> 仓库共 {len(files)} 个文件，开始下载到 {OUT}")
    for i, p in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {p}")
        download(p)
    total = sum(os.path.getsize(os.path.join(OUT, *f.split("/")))
               for f in files if os.path.exists(os.path.join(OUT, *f.split("/"))))
    print(f">> 完成。本地总大小 {total/1e9:.2f} GB")


if __name__ == "__main__":
    main()
