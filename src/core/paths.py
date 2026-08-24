# ====================== 路径配置 ======================
# 基于本文件位置自动推导各资源目录，兼容目录重组（scrcpy/、apk/ 子目录）。
# 无论双击 .bat / 命令行 / 打包后，路径都不会错位。
import os


def _find_project_root(start_file):
    """向上查找「同时包含 scrcpy/ 与 src/ 子目录」的那一层，即为项目根。
    这样即使本文件被移到更深的包目录（如 src/core/），也能正确定位根目录，
    避免 BASE_DIR 算错一级导致 adb/scrcpy/apk 全部找不到。"""
    cur = os.path.abspath(os.path.dirname(start_file))
    while True:
        if os.path.isdir(os.path.join(cur, "scrcpy")) and os.path.isdir(os.path.join(cur, "src")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:  # 已到盘根仍未找到，退化为「上两级」(兼容 src/core 布局)
            return os.path.dirname(os.path.dirname(os.path.abspath(start_file)))
        cur = parent


# 项目根：含 scrcpy/、apk/、src/ 的那一层
BASE_DIR = _find_project_root(__file__)
SRC_DIR  = os.path.join(BASE_DIR, "src")
# 本文件运行时目录锚点：运行时文件(授权/配置)落在 src/，避免生成位置漂移
THIS_DIR = SRC_DIR

SCRCPY_DIR = os.path.join(BASE_DIR, "scrcpy")
APK_DIR    = os.path.join(BASE_DIR, "apk")

SCRCPY_EXE = os.path.join(SCRCPY_DIR, "scrcpy.exe")
ADB_EXE    = os.path.join(SCRCPY_DIR, "adb.exe")
ADBKEYBOARD_APK = os.path.join(APK_DIR, "ADBKeyBoard.apk")
CLIPPER_APK    = os.path.join(APK_DIR, "clipper.apk")

# 授权 / 配置等运行时文件：锚定 src/ 目录，避免生成位置漂移
AUTH_FILE   = os.path.join(THIS_DIR, "auth_key.dat")
PWD_FILE    = os.path.join(THIS_DIR, "admin_pwd.dat")
EXPIRE_FILE = os.path.join(THIS_DIR, "expire.dat")
CONFIG_JSON = os.path.join(THIS_DIR, "zhibodou_config.json")
