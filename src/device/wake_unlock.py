# ====================== 唤醒屏幕 + 自动拉起豆包 ======================
# 解决「手机灭屏/锁屏」时程序无法操作豆包的问题。
#
# 能力边界（adb 视角，受 Android 安全机制约束）：
#   ✅ 检测屏幕是否熄灭 / 是否处于锁屏(keyguard)
#   ✅ 点亮屏幕（KEYCODE_WAKEUP）
#   ✅ 无锁屏 / 滑动锁屏：直接拉起豆包到前台
#   ⚠️ PIN / 密码 / 图案锁屏：adb 无法自动解，只能亮屏并停在解锁界面，
#      需用户手动解锁后程序继续（这是 Android 安全机制，绕不过）
#
# 设计原则：
#   - 所有动作集中在「发送前置」与「启动自检」，不干扰用户正在进行的操作；
#   - 拉起豆包用 monkey/am start，不依赖任何坐标，跨机型稳定；
#   - 进入对话页：启动后尝试点第一个对话项；若识别不到就提示用户手动点一下。
from device import adb_utils
from core.doubao import DOUBAO_PKG
from device import ui_locator
from core.doubao import DOUBAO_INPUT_ID
import time


def is_screen_off():
    """屏幕是否熄灭（休眠）。返回 True/False/None(无法判断)。

    判定：`dumpsys power` 的 mWakefulness=Asleep/Dozing；
    兜底：`dumpsys window` 含 mDreamingLockscreen=true 或 keyguard 可见。
    """
    out, ok = adb_utils.adb_shell("dumpsys", "power")
    if ok and out:
        for line in out.splitlines():
            s = line.strip()
            if "mWakefulness=" in s:
                # 形如 mWkefulness=Asleep / Dozing / Awake
                val = s.split("=", 1)[1].strip()
                if val in ("Asleep", "Dozing"):
                    return True
                if val == "Awake":
                    return False
    # 兜底：window 维度
    wout, wok = adb_utils.adb_shell("dumpsys", "window")
    if wok and wout:
        if "mDreamingLockscreen=true" in wout:
            return True
        # 锁屏 keyguard 可见 + 无豆包前台 => 视作未亮屏可用
        if "Keyguard" in wout and DOUBAO_PKG not in wout:
            # 仅作参考，不作为强判定（避免误判），返回 None 让上层靠 keyguard 判断
            pass
    return None


def is_keyguard_locked():
    """是否处于锁屏(keyguard 尚未解锁)。返回 True/False/None。

    无锁屏的机器 keyguard 通常处于 STATE_UNLOCKED，不会误拦。
    """
    out, ok = adb_utils.adb_shell("dumpsys", "window", "policy")
    if not ok or not out:
        out, ok = adb_utils.adb_shell("dumpsys", "window")
    if not ok or not out:
        return None
    # 关键行示例：
    #   isStatusBarKeyguard=true / mInputRestricted=true（锁屏）
    #   keyguardState=STATE_UNLOCKED（已解锁）
    low = out.lower()
    if "state_unlocked" in low:
        return False
    if "isstatusbarkeyguard=true" in low or "mInputRestricted=true" in low:
        return True
    # 兜底：看 mShowingNotOccluded / keyguard 可见
    if "keyguard" in low and "showing=true" in low:
        return True
    return None


def wake_screen():
    """点亮屏幕（不解锁）。返回是否成功执行命令。"""
    try:
        adb_utils.adb_shell("input", "keyevent", "26")  # KEYCODE_WAKEUP
        time.sleep(0.8)
        return True
    except Exception:
        return False


def launch_doubao():
    """拉起豆包 App 到前台（不依赖坐标）。
    优先 monkey 启动器（等价于点桌面图标，进入上次停留页）；
    失败回退 am start 显式 LAUNCHER activity。"""
    try:
        adb_utils.adb_shell("monkey", "-p", DOUBAO_PKG,
                            "-c", "android.intent.category.LAUNCHER", "1")
        time.sleep(2.0)
        return True
    except Exception:
        pass
    try:
        adb_utils.adb_shell("am", "start", "-n",
                            DOUBAO_PKG + "/.MainActivity",
                            "-c", "android.intent.category.LAUNCHER",
                            "-a", "android.intent.action.MAIN")
        time.sleep(2.0)
        return True
    except Exception:
        return False


def enter_first_conversation():
    """尝试点进豆包的第一个对话项，让界面进入「对话页」（含输入框）。
    返回 True 表示已检测到输入框(对话页)；False/None 表示没识别到，需用户手动。
    说明：不同版本豆包首页布局不同，这里只做「有输入框就视为 OK」的轻量尝试，
    若首页本身就是对话页（输入框已存在）直接返回 True，不做任何点击，避免误操作。"""
    xml = ui_locator._dump_ui_xml()
    if not xml:
        return None
    # 已经在对话页（有输入框）就不用点了
    if ui_locator._find_id_bounds(xml, DOUBAO_INPUT_ID):
        return True
    # 否则尝试点列表第一个可点击项（对话/历史记录）。
    # 用通用「对话/历史」文案兜底：找包含「对话」或第一个 recyclerview 子项。
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        # 优先：desc 或 text 含「对话」「历史」「最近」的可点击节点
        candidates = []
        for n in root.iter("node"):
            txt = (n.get("text") or "") + (n.get("content-desc") or "")
            if any(k in txt for k in ("对话", "历史", "最近", "Chat", "chat")):
                cls = n.get("class", "")
                if "TextView" in cls or n.get("clickable") == "true":
                    candidates.append(n)
        if candidates:
            b = ui_locator._parse_bounds_str(candidates[0].get("bounds", ""))
            if b:
                cx, cy = ui_locator._bounds_center(b)
                adb_utils.adb_tap(cx, cy)
                time.sleep(1.5)
                xml2 = ui_locator._dump_ui_xml()
                if xml2 and ui_locator._find_id_bounds(xml2, DOUBAO_INPUT_ID):
                    return True
        # 兜底：点 recyclerview 的第一个子节点（多数 IM 首页首项是最近对话）
        for n in root.iter("node"):
            if "RecyclerView" in n.get("class", "") and n.get("clickable") == "true":
                b = ui_locator._parse_bounds_str(n.get("bounds", ""))
                if b:
                    cx, cy = ui_locator._bounds_center(b)
                    adb_utils.adb_tap(cx, cy)
                    time.sleep(1.5)
                    xml2 = ui_locator._dump_ui_xml()
                    if xml2 and ui_locator._find_id_bounds(xml2, DOUBAO_INPUT_ID):
                        return True
                break
    except Exception:
        return None
    return False


def ensure_doubao_awake_and_foreground(enter_conversation=True):
    """一键恢复：灭屏则点亮并拉起豆包；已亮但不在前台也拉起；可选进入对话页。

    返回 (ok, msg, need_manual_unlock)
      ok=True              已就绪（豆包前台 + 对话页可达）
      need_manual_unlock=True  遇到 PIN/密码/图案锁屏，需用户手动解锁后重试
    """
    # 1) 灭屏 -> 亮屏
    off = is_screen_off()
    if off:
        wake_screen()
        # 亮屏后重新判断锁屏
    # 2) 锁屏判定
    locked = is_keyguard_locked()
    if locked:
        # 点亮并停在解锁界面，等用户解锁
        wake_screen()
        return False, "⚠️ 手机处于锁屏状态（PIN/密码/图案）：已为你点亮屏幕，请手动解锁后程序会自动继续", True
    # 3) 拉起豆包（无论原本前台与否，确保最新状态）
    if not adb_utils.doubao_in_foreground():
        launch_doubao()
        # 拉起后再确认一次前台
        if not adb_utils.doubao_in_foreground():
            return False, "⚠️ 已尝试拉起豆包但未能进入前台（可能仍被锁屏/其它App遮挡）", False
    # 4) 进入对话页（可选）
    if enter_conversation:
        res = enter_first_conversation()
        if res is True:
            return True, "✅ 已亮屏并拉起豆包到对话页", False
        if res is False:
            return True, "✅ 已亮屏并拉起豆包（未自动识别到对话项，请手动点进一个对话）", False
        # None = 无法 dump（刚亮屏界面未稳），再试一次
        time.sleep(1.0)
        res = enter_first_conversation()
        if res is True:
            return True, "✅ 已亮屏并拉起豆包到对话页", False
        return True, "✅ 已亮屏并拉起豆包（界面读取不稳定，请确认已进入对话页）", False
    return True, "✅ 已亮屏并拉起豆包到前台", False
