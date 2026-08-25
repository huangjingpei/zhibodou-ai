"""智播豆 单文件 exe 交付版构建脚本（PyInstaller，--noconsole 无黑窗口）。
用法：
    .venv\\Scripts\\python.exe build\\build_onefile_release.py
产物：build\\dist\\zhibodou.exe （GUI 程序标准形态，无控制台黑窗口）

与 build_onefile.py（--console 调试版）的区别仅在于 --noconsole：
调试版会保留控制台窗口，便于在排错时观察 [Client-VAD] / 【投屏】等日志；
交付版不弹控制台，运行日志统一显示在软件内置的日志框内。
资源/路径处理两者一致（均依赖 src/core/paths.py 的 frozen 兼容分支）。
"""
import os
import PyInstaller.__main__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根 E:\zhibodou-ai\zhibodou
SRC = os.path.join(ROOT, "src")

PyInstaller.__main__.run([
    "--onefile",
    "--noconsole",               # 交付版：无黑窗口
    "--name", "zhibodou",
    "--paths", SRC,
    "--add-data", os.path.join(ROOT, "scrcpy") + ";" + "scrcpy",
    "--add-data", os.path.join(ROOT, "apk") + ";" + "apk",
    "--hidden-import", "pyautogui",
    "--hidden-import", "pyscreeze",
    "--hidden-import", "pygetwindow",
    "--hidden-import", "pyperclip",
    "--hidden-import", "mouseinfo",
    "--hidden-import", "pytweening",
    "--hidden-import", "pyrect",
    "--hidden-import", "PIL",
    "--hidden-import", "PIL.Image",
    "--hidden-import", "pyaudio",
    "--hidden-import", "pyttsx3",
    "--hidden-import", "comtypes",
    "--hidden-import", "websocket",
    "--hidden-import", "websocket_client",
    "--hidden-import", "win32api",
    "--hidden-import", "win32gui",
    "--hidden-import", "win32con",
    "--hidden-import", "win32com",
    "--hidden-import", "pythoncom",
    "--hidden-import", "pywintypes",
    "--distpath", os.path.join(ROOT, "build", "dist"),
    "--workpath", os.path.join(ROOT, "build", "work"),
    "--specpath", os.path.join(ROOT, "build", "specs"),
    os.path.join(SRC, "main.py"),
])
