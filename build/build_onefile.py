"""智播豆 单文件 exe 构建脚本（PyInstaller）。
用法：
    .venv\\Scripts\\python.exe build\\build_onefile.py
产物：build\\dist\\zhibodou.exe

说明：
- 首轮使用 --console，便于在控制台观察缺失依赖 / 启动错误；
  确认能启动后，将下方 "--console" 改为 "--noconsole" 重新构建即为无黑窗交付版。
- scrcpy / apk 等只读资源通过 --add-data 打进 _MEIPASS；
  运行时路径由 src/core/paths.py 的 frozen 兼容分支重定向（scrcpy 走 _MEIPASS，配置/授权/log 落到 exe 同级目录）。
- 仅支持 Windows（依赖 pywin32 / pyaudio / scrcpy 的 Windows 二进制）。
"""
import os
import PyInstaller.__main__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根 E:\zhibodou-ai\zhibodou
SRC = os.path.join(ROOT, "src")

PyInstaller.__main__.run([
    "--onefile",
    "--console",                 # 调试用；交付版改 --noconsole
    "--name", "zhibodou",
    "--paths", SRC,
    # 只读资源：scrcpy 完整目录(含 scrcpy.exe / scrcpy-server / SDL3.dll / adb.exe 等)
    "--add-data", os.path.join(ROOT, "scrcpy") + ";" + "scrcpy",
    "--add-data", os.path.join(ROOT, "apk") + ";" + "apk",
    # 隐藏导入（静态分析可能漏掉的动态依赖）
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
    "--workpath", os.path.join(ROOT, "build", "build"),
    "--specpath", os.path.join(ROOT, "build"),
    os.path.join(SRC, "main.py"),
])
