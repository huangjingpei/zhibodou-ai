@echo off
chcp 65001
echo 智播豆直播系统启动程序
echo ======================================
cd /d "%~dp0"
echo 正在加载Python运行环境，启动主程序...
"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" zhibodou_full.py
echo.
echo 程序已退出，按任意键关闭窗口
pause >nul