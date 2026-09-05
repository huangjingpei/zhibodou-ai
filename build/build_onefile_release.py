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
RTH = os.path.join(ROOT, "build", "rth_asyncio.py")
# 交付版专属：注入生产 PDK 后端（https://pdk.graddu.com）。
# debug/测试构建（build_onefile.py / build_console_debug.py）不挂此钩子，
# 默认仍为 http://127.0.0.1:8080；环境变量 PDK_BASE_URL 优先级更高。
RTH_PDK_RELEASE = os.path.join(ROOT, "build", "rth_pdk_release.py")

# asyncio 子模块（playwright 依赖）。PyInstaller 冻结后 asyncio.__init__ 里
# `from .base_events import *` 不会把子模块名绑定回包命名空间，导致
# `NameError: name 'base_events' is not defined`，弹幕/浏览器采集启动即崩。
ASYNCIO_HIDDEN = [
    "asyncio", "asyncio.base_events", "asyncio.constants", "asyncio.coroutines",
    "asyncio.events", "asyncio.exceptions", "asyncio.futures", "asyncio.locks",
    "asyncio.log", "asyncio.proactor_events", "asyncio.protocols", "asyncio.queues",
    "asyncio.runners", "asyncio.selector_events", "asyncio.sslproto",
    "asyncio.staggered", "asyncio.streams", "asyncio.subprocess", "asyncio.tasks",
    "asyncio.taskgroups", "asyncio.timeouts", "asyncio.transports", "asyncio.trsock",
    "asyncio.unix_events", "asyncio.windows_events", "asyncio.windows_selector_events",
    "asyncio.windows_utils",
]

PyInstaller.__main__.run([
    "--onefile",
    "--noconsole",               # 交付版：无黑窗口
    "--name", "zhibodou",
    "--paths", SRC,
    "--runtime-hook", RTH,
    "--runtime-hook", RTH_PDK_RELEASE,
    "--add-data", os.path.join(ROOT, "scrcpy") + ";" + "scrcpy",
    "--add-data", os.path.join(ROOT, "apk") + ";" + "apk",
    "--hidden-import", "playwright",
    "--hidden-import", "playwright.sync_api",
    "--hidden-import", "playwright._impl",
    "--hidden-import", "greenlet",
] + [item for m in ASYNCIO_HIDDEN for item in ("--hidden-import", m)] + [
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
