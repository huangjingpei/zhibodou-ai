"""
手机唤醒与豆包拉起模块 —— 纯 ADB Shell Intent 模式，彻底剔除 slow dump
"""
import time
import subprocess
from core.paths import ADB_EXE
from core.doubao import DOUBAO_PKG, DOUBAO_MAIN_ACTIVITY
from device import adb_utils


def is_screen_on(device_id: str = None) -> bool:
    """判断屏幕是否点亮"""
    out, _ = adb_utils.adb_shell("dumpsys", "power")
    return "mHoldingDisplaySuspendBlocker=true" in out or "Display Power: state=ON" in out


def wake_up_phone(device_id: str = None):
    """点亮屏幕"""
    if not is_screen_on(device_id):
        base_cmd = [ADB_EXE]
        if device_id:
            base_cmd.extend(["-s", device_id])
        subprocess.run(base_cmd + ["shell", "input", "keyevent", "26"], capture_output=True, timeout=2)
        time.sleep(0.3)


def unlock_screen(device_id: str = None):
    """上滑解锁"""
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    # 模拟向上轻扫解锁
    subprocess.run(base_cmd + ["shell", "input", "swipe", "500", "1500", "500", "500", "200"], capture_output=True,
                   timeout=2)
    time.sleep(0.3)


def launch_doubao_app(device_id: str = None) -> bool:
    """通过 Android 原生 Intent 毫秒级拉起豆包主 Activity"""
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])

    cmd = base_cmd + [
        "shell", "am", "start",
        "-n", f"{DOUBAO_PKG}/{DOUBAO_MAIN_ACTIVITY}",
        "-a", "android.intent.action.MAIN",
        "-c", "android.intent.category.LAUNCHER"
    ]
    subprocess.run(cmd, capture_output=True, timeout=3)
    time.sleep(1.0)
    return adb_utils.doubao_in_foreground()


def ensure_doubao_ready(device_id: str = None) -> bool:
    """唤醒 -> 解锁 -> 拉起豆包"""
    wake_up_phone(device_id)
    unlock_screen(device_id)
    if not adb_utils.doubao_in_foreground():
        return launch_doubao_app(device_id)
    return True