@echo off
cd /d "%~dp0"
echo.
echo   ============================================
echo     推送更新到 GitHub
echo   ============================================
echo.

git remote -v
echo.
echo   即将推送当前提交：
git --no-pager log --oneline -1
echo.
echo   按任意键开始推送（会弹窗让你登录 GitHub，选 Browser 即可）...
pause >nul

git push origin main

echo.
if errorlevel 1 (
  echo   [推送失败]
  echo   常见原因：
  echo     1. 远端有新提交 -^> 先执行: git pull --rebase origin main
  echo     2. 凭据过期     -^> 删除 Windows 凭据管理器里的 github 条目后重试
  echo     3. 没有权限     -^> 确认账号已被加为 Collaborator
  echo.
  pause
  exit /b 1
)

echo   [推送成功] 仓库地址：
echo   https://github.com/work-gafa/lora
echo.
echo   组员拉取更新：git pull
pause
