# -*- coding: utf-8 -*-
"""重写两个启动 bat（必须存 GBK，cmd 默认按 GBK 读）。

改进：
  1. 先探测 8004 是否已在服务 —— 已在跑就直接开浏览器，不再报"端口被占用"然后闪退
     （之前用户双击没反应/报错，多半是这个原因）。
  2. 不写 chcp（会让 cmd 把后面几行解析坏）。
  3. python 路径用 %~dp0 绝对路径。
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

PY = r'"D:\10604\ANACONDA\envs\lora\python.exe"'
CHECK = 'netstat -ano | findstr ":8004" | findstr "LISTENING" >nul'
OPEN_BROWSER = 'start "" /min cmd /c "ping -n 3 127.0.0.1 >nul ^& start http://127.0.0.1:8004"'


def build(app_rel: str) -> str:
    return (
        "@echo off\n"
        'cd /d "%~dp0"\n'
        "echo.\n"
        "echo   ============================================\n"
        "echo     行李物品标注与识别平台\n"
        "echo   ============================================\n"
        "echo.\n"
        "\n"
        "rem --- 1) 8004 已经在服务？那就别再起一个，直接开浏览器 ---\n"
        f"{CHECK}\n"
        "if %errorlevel%==0 (\n"
        "  echo   检测到服务已在运行，直接打开浏览器...\n"
        f"  {OPEN_BROWSER}\n"
        "  echo.\n"
        "  echo   如果想重启服务：先关掉正在运行的那个黑窗口，再双击本文件。\n"
        "  timeout /t 4 >nul\n"
        "  exit /b 0\n"
        ")\n"
        "\n"
        "rem --- 2) 没在跑，正常启动 ---\n"
        "echo   正在启动服务，请稍候...\n"
        f"{OPEN_BROWSER}\n"
        f'{PY} "%~dp0{app_rel}"\n'
        "\n"
        "if errorlevel 1 (\n"
        "  echo.\n"
        "  echo   [启动失败] 请检查 8004 端口是否被其他程序占用。\n"
        "  pause\n"
        ")\n"
    )


(BASE / "启动标注平台.bat").write_text(build("anno-tool\\backend\\app.py"), encoding="gbk")
(BASE / "anno-tool" / "启动平台.bat").write_text(build("backend\\app.py"), encoding="gbk")

for f in (BASE / "启动标注平台.bat", BASE / "anno-tool" / "启动平台.bat"):
    b = f.read_bytes()
    print("--- %s (%d bytes) ---" % (f.name, len(b)))
    print(b.decode("gbk"))
