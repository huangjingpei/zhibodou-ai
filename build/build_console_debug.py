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
]

cmd = [
    PY, "-m", "PyInstaller",
    "--onefile",
    "--console",                 # <-- 关键：带黑窗口
    "--name", "zhibodou_console",
    "--distpath", DIST_DIR,
    "--workpath", WORK_DIR,
    "--specpath", SPEC_DIR,
    "--noconfirm",
    "--clean",
    "--paths", os.path.join(ROOT, "src"),
]
for d in datas:
    cmd += ["--add-data", d]
for h in hidden:
    cmd += ["--hidden-import", h]

cmd.append(ENTRY)

print("[BUILD] console debug build command:")
print(" ".join(cmd))
subprocess.run(cmd, check=True)
print(f"[OK] 调试版 exe 已生成: {os.path.join(DIST_DIR, 'zhibodou_console.exe')}")
