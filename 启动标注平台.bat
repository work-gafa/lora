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
  start "" /min cmd /c "ping -n 3 127.0.0.1 >nul ^& start http://127.0.0.1:8004"
  echo.
  echo   如果想重启服务：先关掉正在运行的那个黑窗口，再双击本文件。
  timeout /t 4 >nul
  exit /b 0
)

rem --- 2) 没在跑，正常启动 ---
echo   正在启动服务，请稍候...
start "" /min cmd /c "ping -n 3 127.0.0.1 >nul ^& start http://127.0.0.1:8004"
"D:\10604\ANACONDA\envs\lora\python.exe" "%~dp0anno-tool\backend\app.py"

if errorlevel 1 (
  echo.
  echo   [启动失败] 请检查 8004 端口是否被其他程序占用。
  pause
)
