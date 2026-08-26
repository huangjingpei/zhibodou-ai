"""
生成带黑色命令行窗口的调试版 zhibodou_console.exe，方便查看 ADB / VAD / scrcpy 启动日志。
产物：build/dist_debug/zhibodou_console.exe
"""
import os
import sys
import subprocess
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_DIR = os.path.join(ROOT, "build", "specs_debug")
WORK_DIR = os.path.join(ROOT, "build", "work_debug")
DIST_DIR = os.path.join(ROOT, "build", "dist_debug")

os.makedirs(SPEC_DIR, exist_ok=True)
os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(DIST_DIR, exist_ok=True)

PY = sys.executable
ENTRY = os.path.join(ROOT, "src", "main.py")

# 收集 scrcpy 目录下的所有文件（递归）
datas = []
SCRCPY_DIR = os.path.join(ROOT, "scrcpy")
if os.path.isdir(SCRCPY_DIR):
    for dirpath, dirnames, filenames in os.walk(SCRCPY_DIR):
        for fname in filenames:
            src = os.path.join(dirpath, fname)
            rel_dir = os.path.relpath(os.path.dirname(src), ROOT)
            datas.append(f"{src};{rel_dir}")
else:
    print(f"[WARN] scrcpy 目录不存在: {SCRCPY_DIR}")

# apk 目录
APK_DIR = os.path.join(ROOT, "apk")
if os.path.isdir(APK_DIR):
    for fname in os.listdir(APK_DIR):
        src = os.path.join(APK_DIR, fname)
        if os.path.isfile(src):
            datas.append(f"{src};apk")

# 隐藏导入（与交付版 build_onefile_release.py 保持一致，确保能真正运行出日志）
hidden = [
    "pywintypes", "pythoncom", "win32api", "win32gui", "win32con",
    "win32process", "win32event", "wmi",
    "pyautogui", "pyscreeze", "pygetwindow", "pyperclip",
    "mouseinfo", "pytweening", "pyrect", "PIL", "PIL.Image",
    "pyaudio", "pyttsx3", "comtypes",
    "websocket", "websocket_client",
    "playwright", "playwright.sync_api", "playwright._impl", "greenlet",
]

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

cmd = [
    PY, "-m", "PyInstaller",
    "--onefile",
    "--console",                 # <-- 关键：带黑窗口
    "--name", "zhibodou_console",
    "--runtime-hook", os.path.join(ROOT, "build", "rth_asyncio.py"),
    "--distpath", DIST_DIR,
    "--workpath", WORK_DIR,
    "--specpath", SPEC_DIR,
    "--noconfirm",
    # 注意：不要加 --clean。本构建环境的"安全删除"钩子会拦截 PyInstaller 的
    # 清理步骤（批量删 50+ 临时文件需人工确认），导致构建以非零码中止。
    # 去掉 --clean 后可正常构建，PyInstaller 会直接覆盖 work 目录。
    "--paths", os.path.join(ROOT, "src"),
]
for d in datas:
    cmd += ["--add-data", d]
for h in hidden:
    cmd += ["--hidden-import", h]
for m in ASYNCIO_HIDDEN:
    cmd += ["--hidden-import", m]

cmd.append(ENTRY)

print("[BUILD] console debug build command:")
print(" ".join(cmd))
subprocess.run(cmd, check=True)
print(f"[OK] 调试版 exe 已生成: {os.path.join(DIST_DIR, 'zhibodou_console.exe')}")
