@echo off
cd /d "%~dp0"
echo.
echo   ============================================
echo     行李物品标注与识别平台
echo   ============================================
echo.

rem --- 1) 8004 已经在服务？那就别再起一个，直接开浏览器 ---
netstat -ano | findstr ":8004" | findstr "LISTENING" >nul
if %errorlevel%==0 (
  echo   检测到服务已在运行，直接打开浏览器...
  start "" http://127.0.0.1:8004
  echo.
  echo   如果想重启服务：先关掉正在运行的那个黑窗口，再双击本文件。
  timeout /t 4 >nul
  exit /b 0
)

rem --- 2) 没在跑，启动服务 ---
rem     浏览器由 app.py 自己探活后打开（端口通了才开），
rem     所以这里不需要猜等待时间，也不会出现"浏览器先开、页面打不开"。
echo   正在启动服务，浏览器会自动打开（约 3~5 秒，请稍候）...
echo.
echo   ---- 关闭本窗口 = 停止服务 + 释放显存 ----
echo.

set ANNO_OPEN_BROWSER=1
"D:\10604\ANACONDA\envs\lora\python.exe" "%~dp0..\anno-tool\backend\app.py"

rem --- 3) 走到这里说明服务已停止（正常 Ctrl+C，或异常退出）---
echo.
echo   [服务已停止]
echo   若刚才看到端口占用等报错，请检查 8004 是否被其他程序占用。
pause
