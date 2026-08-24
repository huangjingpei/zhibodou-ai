@echo off
setlocal
cd /d "%~dp0"

echo ======================================
echo   智播豆直播系统 一键启动
echo ======================================
echo.

set "PY="
where python >nul 2>nul
if %errorlevel%==0 (
  set "PY=python"
  goto :run
)
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py"
  goto :run
)
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" (
  set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
  goto :run
)

echo [错误] 未找到 Python 解释器。
echo   请先安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
echo   或确认此路径存在：
echo   C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
pause
exit /b 1

:run
echo 正在使用 %PY% 启动主程序...
echo.
"%PY%" main.py
echo.
echo 程序已退出，按任意键关闭窗口。
pause >nul
