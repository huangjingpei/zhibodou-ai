import os
import sys

# 基础目录计算
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# 配置文件与数据路径
CONFIG_JSON = os.path.join(SRC_DIR, "settings", "config.json")
if not os.path.exists(CONFIG_JSON):
    ROOT_CONFIG = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(ROOT_CONFIG):
        CONFIG_JSON = ROOT_CONFIG

# 授权与认证文件路径 (Auth & Security)
DATA_DIR = os.path.join(SRC_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

AUTH_FILE = os.path.join(DATA_DIR, "auth.key")
PWD_FILE = os.path.join(DATA_DIR, "pwd.key")
EXPIRE_FILE = os.path.join(DATA_DIR, "expire.key")

# 话术、音视频与日志目录
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# APK 目录
APK_DIR = os.path.join(BASE_DIR, "apk")
ADBKEYBOARD_APK = os.path.join(APK_DIR, "ADBKeyBoard.apk")
CLIPPER_APK = os.path.join(APK_DIR, "clipper.apk")

# Scrcpy 与 ADB 路径
SCRCPY_DIR = os.path.join(BASE_DIR, "scrcpy")
SCRCPY_EXE = os.path.join(SCRCPY_DIR, "scrcpy.exe")
LOCAL_ADB = os.path.join(SCRCPY_DIR, "adb.exe")

if os.path.exists(LOCAL_ADB):
    ADB_EXE = LOCAL_ADB
else:
    ADB_EXE = "adb"

# ====================== 打包(frozen)路径兼容 ======================
# 开发态(python src/main.py)：不进入下方分支，所有路径保持原行为，零影响。
# 单文件打包(PyInstaller --onefile)：全部资源解压到临时目录 sys._MEIPASS(只读)，
#   因此「只读资源(apk)」走 _MEIPASS；「可写数据(config/auth/log)」
#   必须落到 exe 同级目录，否则每次启动配置丢失、授权文件无法持久化。
# 多文件打包(--onedir)：frozen 为真但不存在 _MEIPASS，下方分支不进入，行为同开发态
#   （BASE_DIR 已是 dist 目录、可写），无需特殊处理。
def _extract_tree_if_needed(src, dst):
    """把 _MEIPASS 中的只读资源树解压到可写 runtime 目录(仅首次/缺失时)。
    关键：scrcpy/adb 这类【需要被执行的二进制】不能依赖 _MEIPASS 临时目录——
    从 %TEMP% 启动的可执行文件最常被 Defender 拦截、且 adb server 需要稳定路径。
    改为解压到 exe 同级目录运行，与开发态(项目目录/scrcpy)完全一致。"""
    import shutil
    try:
        if not os.path.isdir(src):
            return
        if os.path.exists(os.path.join(dst, "adb.exe")):
            return  # 已解压，跳过（如需更新请删除 exe 同级 scrcpy 目录）
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    except Exception as e:
        # 解压失败不致命：退回用 _MEIPASS 原路径尝试
        print("[paths] ⚠ 解压 scrcpy 到 %s 失败：%s" % (dst, e))


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    RESOURCE_DIR = sys._MEIPASS                       # 只读资源：apk
    RUNTIME_DIR = os.path.dirname(os.path.abspath(sys.executable))  # 可写数据

    # ⚠ scrcpy(含 adb.exe/依赖 DLL)从临时目录解压到 exe 同级稳定目录运行
    RUNTIME_SCRCPY_DIR = os.path.join(RUNTIME_DIR, "scrcpy")
    _extract_tree_if_needed(os.path.join(RESOURCE_DIR, "scrcpy"), RUNTIME_SCRCPY_DIR)
    SCRCPY_DIR = RUNTIME_SCRCPY_DIR
    SCRCPY_EXE = os.path.join(SCRCPY_DIR, "scrcpy.exe")
    LOCAL_ADB = os.path.join(SCRCPY_DIR, "adb.exe")
    ADB_EXE = LOCAL_ADB if os.path.exists(LOCAL_ADB) else "adb"

    APK_DIR = os.path.join(RESOURCE_DIR, "apk")
    ADBKEYBOARD_APK = os.path.join(APK_DIR, "ADBKeyBoard.apk")
    CLIPPER_APK = os.path.join(APK_DIR, "clipper.apk")

    CONFIG_JSON = os.path.join(RUNTIME_DIR, "config.json")
    DATA_DIR = os.path.join(RUNTIME_DIR, "data")
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    AUTH_FILE = os.path.join(DATA_DIR, "auth.key")
    PWD_FILE = os.path.join(DATA_DIR, "pwd.key")
    EXPIRE_FILE = os.path.join(DATA_DIR, "expire.key")
    SCRIPTS_DIR = os.path.join(RUNTIME_DIR, "scripts")
    LOGS_DIR = os.path.join(RUNTIME_DIR, "logs")


# ====================== 隐藏外部二进制子进程黑窗口 ======================
# 打包为无控制台 GUI 后，每次调用 adb.exe / scrcpy.exe 这类控制台程序都会
# 弹出一个一闪而过的黑窗口，体验极差。这里在导入早期统一给这些外部二进制
# 的子进程注入 CREATE_NO_WINDOW，彻底消除闪烁。
# 仅匹配可执行文件名含 adb / scrcpy 的子进程，不影响其它进程；非 Windows
# 平台 CREATE_NO_WINDOW 不存在时自动跳过。
import subprocess as _sp
try:
    _HIDE_WIN_FLAGS = _sp.CREATE_NO_WINDOW
except AttributeError:
    _HIDE_WIN_FLAGS = 0

if _HIDE_WIN_FLAGS:
    _orig_run = _sp.run
    _orig_popen = _sp.Popen

    def _exe_is_external(args, executable):
        target = executable or (args[0] if isinstance(args, (list, tuple)) and args else "")
        s = str(target).lower().replace("\\", "/")
        return "/adb" in s or s.endswith("adb") or "scrcpy" in s

    def _patched_run(*a, **k):
        if (a or "args" in k) and "creationflags" not in k:
            args = k.get("args", a[0] if a else None)
            if _exe_is_external(args, k.get("executable")):
                k["creationflags"] = _HIDE_WIN_FLAGS
        return _orig_run(*a, **k)

    def _patched_popen(*a, **k):
        if (a or "args" in k) and "creationflags" not in k:
            args = k.get("args", a[0] if a else None)
            if _exe_is_external(args, k.get("executable")):
                k["creationflags"] = _HIDE_WIN_FLAGS
        return _orig_popen(*a, **k)

    _sp.run = _patched_run
    _sp.Popen = _patched_popen
