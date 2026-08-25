"""
豆包状态自检模块 —— 纯 Agent / 前台快检架构，已彻底剔除 uiautomator dump
"""
from device import adb_utils
from core.doubao import DOUBAO_PKG

def in_conversation_screen():
    """检测是否在豆包主界面：直接通过 dumpsys 秒判（< 20ms）"""
    return adb_utils.doubao_in_foreground()


def in_voice_call():
    """是否在语音通话中"""
    return False


def is_doubao_black_screen():
    """是否黑屏"""
    return False


def can_send():
    """是否具备发送能力：前台处于活跃状态即具备发送能力"""
    return adb_utils.doubao_in_foreground()


def is_phone_at_desktop():
    """判断是否在手机桌面"""
    out, _ = adb_utils.adb_shell("dumpsys", "window")
    return "launcher" in out.lower()


def check_doubao_ready():
    """
    【开机自检入口】
    完全基于轻量级设备状态探测，不执行任何 dump
    返回: (ok: bool, problems: list[str], mode: str)
    """
    online = adb_utils.adb_devices_online(verbose=True)
    if not online:
        return False, ["ℹ️ 未检测到 adb 设备，进入手动模式"], "offline"

    # 1. 检查豆包安装状态
    installed = adb_utils.is_app_installed(DOUBAO_PKG)
    if installed is False:
        return False, ["❌ 手机未安装豆包 APP"], "auto"

    # 2. 检查前台状态
    if not adb_utils.doubao_in_foreground():
        return False, ["⚠️ 豆包未在前台运行，请在手机上打开豆包"], "auto"

    return True, [], "auto"