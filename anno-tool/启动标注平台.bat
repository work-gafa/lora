@echo off
cd /d "%~dp0.."
set ACC_PRODUCT_CONFIG_V3=
echo ============================================
echo   Luggage Annotator starting ...
echo   Browser will open: http://127.0.0.1:8003
echo   Close this window to STOP (frees GPU).
echo ============================================
start "" /min cmd /c "ping -n 6 127.0.0.1 >nul & start http://127.0.0.1:8003"
"D:\10604\ANACONDA\envs\lora\python.exe" -m uvicorn anno-tool.app:app --host 127.0.0.1 --port 8003
if errorlevel 1 (
  echo.
  echo [ERROR] Failed to start. Check if port 8003 is in use or the conda python path.
  pause
)
