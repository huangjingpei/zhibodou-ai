@echo off
chcp 65001 >nul
title 智播豆 - 一键编译生成 EXE

echo ========================================================
echo               智播豆 - EXE 编译打包程序
echo ========================================================
echo.

cd /d "%~dp0"

:: 优先检测虚拟环境 Python
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    set "PY=python"
)

echo [1/3] 检查 Python 环境...
"%PY%" --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到可用的 Python 环境！
    echo 请确认根目录下存在 .venv 虚拟环境或已安装系统 Python。
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('"%PY%" --version') do echo       检测到: %%i

echo.
echo [2/3] 检查 PyInstaller 打包工具...
"%PY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo       未安装 PyInstaller，正在安装...
    "%PY%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败，请检查网络连接。
        pause
        exit /b 1
    )
)
for /f "tokens=*" %%i in ('"%PY%" -m PyInstaller --version') do echo       PyInstaller 版本: %%i

echo.
echo 请选择编译模式：
echo   [1] 交付发布版 (Release - 推荐，无控制台黑窗口)
echo   [2] 调试分析版 (Debug - 带控制台黑窗口，适合观察排错日志)
echo.
set /p CHOICE="请输入选项 [1 或 2，默认为 1]: "

if "%CHOICE%"=="2" (
    echo.
    echo ========================================================
    echo   开始编译【调试分析版】(build\build_console_debug.py)...
    echo ========================================================
    "%PY%" build\build_console_debug.py
    if errorlevel 1 (
        echo.
        echo [错误] 打包失败，请检查上方错误输出！
        pause
        exit /b 1
    )
    echo.
    echo ========================================================
    echo   [成功] 调试版 EXE 构建完成！
    echo   产物位置: build\dist_debug\zhibodou_console.exe
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   开始编译【交付发布版】(build\build_onefile_release.py)...
    echo ========================================================
    "%PY%" build\build_onefile_release.py
    if errorlevel 1 (
        echo.
        echo [错误] 打包失败，请检查上方错误输出！
        pause
        exit /b 1
    )
    echo.
    echo ========================================================
    echo   [成功] 交付版 EXE 构建完成！
    echo   产物位置: build\dist\zhibodou.exe
    echo ========================================================
)

echo.
pause
