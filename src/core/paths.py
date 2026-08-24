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