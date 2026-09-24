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

# 自动同步最新的 android_agent APK 到 apk 资源目录（确保打包进 exe 的是最新版本）
agent_apk = os.path.join(ROOT, "android_agent", "app", "release", "app-release.apk")
target_apk = os.path.join(ROOT, "apk", "app-release.apk")
if os.path.exists(agent_apk):
    import shutil
    os.makedirs(os.path.dirname(target_apk), exist_ok=True)
    if not os.path.exists(target_apk) or os.path.getmtime(agent_apk) >= os.path.getmtime(target_apk):
        shutil.copy2(agent_apk, target_apk)

# 冻结态修复运行时钩子（与测试/交付构建保持一致）：
# - rth_asyncio.py     ：修复 asyncio 子模块名未绑定（NameError: base_events）
# - rth_isolated_shim.py：中和 PyInstaller.isolated（code must be code 崩溃）
# - rth_liveplate.py   ：把 _MEIPASS 内的 live_plate 加入 sys.path 兜底
RTH_ASYNCIO = os.path.join(ROOT, "build", "rth_asyncio.py")
RTH_SHIM = os.path.join(ROOT, "build", "rth_isolated_shim.py")
RTH_LIVEPLATE = os.path.join(ROOT, "build", "rth_liveplate.py")

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
    "--console",                 # 调试用；交付版改 --noconsole
    "--name", "zhibodou",
    "--paths", SRC,
    "--paths", os.path.join(SRC, "danma"),   # 让 live_plate 作为顶层包被 PyInstaller 分析发现（danma/main.py 用绝对导入 `from live_plate`，运行期靠 sys.path 注入可达，但静态分析需此路径）
    "--paths", os.path.join(SRC, "streamget"), # 让 streamget 作为顶层包被 PyInstaller 分析发现
    "--collect-submodules", "danma",   # 递归收集 danma 包（含 live_plate 及全部子模块，避免 No module named 'live_plate'）
    "--collect-submodules", "streamget", # 递归收集 streamget 包及所有平台子模块
    "--noconfirm",               # 非交互重建：已有 dist/work 时直接覆盖
    "--runtime-hook", RTH_ASYNCIO,
    "--runtime-hook", RTH_SHIM,
    "--runtime-hook", RTH_LIVEPLATE,
    # 只读资源：scrcpy 完整目录(含 scrcpy.exe / scrcpy-server / SDL3.dll / adb.exe 等)
    "--add-data", os.path.join(ROOT, "scrcpy") + ";" + "scrcpy",
    "--add-data", os.path.join(ROOT, "apk") + ";" + "apk",
    "--add-data", os.path.join(SRC, "streamget", "streamget", "js") + ";" + "streamget/js",
    # 隐藏导入（静态分析可能漏掉的动态依赖）
    "--hidden-import", "streamget",
    "--hidden-import", "execjs",
    "--hidden-import", "loguru",
    "--hidden-import", "Crypto",
    "--hidden-import", "httpx",
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
] + [item for m in ASYNCIO_HIDDEN for item in ("--hidden-import", m)] + [
    "--distpath", os.path.join(ROOT, "build", "dist_debug"),
    "--workpath", os.path.join(ROOT, "build", "build_debug"),
    "--specpath", os.path.join(ROOT, "build"),
    os.path.join(SRC, "main.py"),
])
