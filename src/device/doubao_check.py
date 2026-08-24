# ====================== 豆包就绪检测（发送前置体检） ======================
# 在开机自检 / 正式发送前，确认豆包：已安装、已运行、在前台、处于对话界面、无遮挡、可发送。
# 设计原则：全部为「只读检测」（dump 控件树 / 读 window 信息），不点击、不输入、
# 不切输入法，避免干扰用户真实对话。需要主动切换/输入的动作留给 input_text 发送流程。
#
# 两种运行模式：
#   - 在线模式（adb 设备在线）：做完整自动体检。
#   - 离线模式（无 adb 设备）：无法自动检测，降级为「手动模式」——
#     提示用户用肉眼确认豆包状态并手动操作，不阻塞程序本身。
from core.doubao import (DOUBAO_PKG, DOUBAO_INPUT_ID, DOUBAO_VOICE_TOGGLE_ID)
from device import adb_utils
from device import ui_locator
from device import wake_unlock


def doubao_installed():
    """手机是否安装了豆包 App（adb 可用时）。
    返回 True / False / None(adb 不可用或命令失败，无法判断)。"""
    return adb_utils.is_app_installed(DOUBAO_PKG)


def doubao_running():
    """豆包是否处于「运行/驻留」状态（窗口列表中存在豆包窗口）。
    区别于前台：后台 App 也常保留窗口，故仅用于给出更精准的提示文案。"""
    out, _ = adb_utils.adb_shell("dumpsys", "window")
    return DOUBAO_PKG in out


def in_conversation_screen():
    """是否处于对话界面（只读）：控件树中存在输入框(文字模式)。
    返回 True / False / None(无法获取控件树)。"""
    xml = ui_locator._dump_ui_xml()
    if not xml:
        return None
    if ui_locator._find_id_bounds(xml, DOUBAO_INPUT_ID):
        return True
    return False


def conversation_hint():
    """对话界面检测失败时的辅助提示：是否停在语音模式 / 在其它页。"""
    xml = ui_locator._dump_ui_xml()
    if not xml:
        return "无法获取界面控件树（确认手机未锁屏/未卡顿）"
    if ui_locator._find_id_bounds(xml, DOUBAO_VOICE_TOGGLE_ID):
        return "可能在语音输入模式（需点「文本输入」切回文字模式）"
    return "未找到输入框/发送按钮，请确认进入了豆包聊天对话页"


def is_occluded():
    """当前豆包界面是否被遮挡（权限框 / 系统弹窗 / 悬浮窗 / 其它 App 覆盖）。
    返回 (occluded: bool|None, detail: str)。None=无法判断。

    判定依据（只读 dumpsys window）：
      1) mCurrentFocus 焦点窗口不属于豆包 -> 被其它窗口抢焦点（权限框/系统UI/其它App）
      2) 存在覆盖型窗口(type SYSTEM_ALERT / APPLICATION_OVERLAY)且不属于豆包
    """
    out, _ = adb_utils.adb_shell("dumpsys", "window")
    if not out:
        return None, "无法读取窗口信息"
    # 1) 焦点窗口不是豆包 -> 被其它窗口抢焦点
    focus_line = ""
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("mCurrentFocus"):
            focus_line = s
            break
    if focus_line and DOUBAO_PKG not in focus_line:
        return True, "焦点窗口不是豆包(mCurrentFocus 指向其它窗口，可能为权限框/弹窗): " + focus_line
    # 2) 存在覆盖型窗口且不属于豆包
    for line in out.splitlines():
        s = line.strip()
        if "type" in s and ("TYPE_SYSTEM_ALERT" in s or "TYPE_APPLICATION_OVERLAY" in s):
            if DOUBAO_PKG not in s:
                return True, "存在非豆包的覆盖层窗口(悬浮窗/系统警报)"
    return False, ""


def can_send():
    """能否向豆包发送聊天信息（只读结构检测）：
    豆包在前台、界面无遮挡、且输入框存在且可编辑/可点击。
    返回 True / False / None(无法判断)。

    说明：发送按钮仅在有文字时才出现，故「可发送」以输入框可用性为判定；
    真正的发送动作由 input_text 发送流程执行并验证。
    """
    if not adb_utils.doubao_in_foreground():
        return False
    occ, _ = is_occluded()
    if occ:
        return False
    xml = ui_locator._dump_ui_xml()
    if not xml:
        return None
    node = ui_locator._find_node(xml, DOUBAO_INPUT_ID)
    if node is None:
        return False
    if node.get("enabled") == "false":
        return False
    return True


def check_doubao_ready():
    """综合体检：返回 (ok, problems, mode)。
    ok=True 表示：豆包已安装、已运行、在前台、处于对话界面、无遮挡、可发送。
    problems 是人话中文提示（含 ℹ️ 级别提示，不一定阻断发送）。
    mode='online' 表示做了完整自动检测；mode='offline' 表示无 adb、
        降级为手动模式（程序仍可运行，但发送需用户肉眼确认并手动操作）。

    注意：离线模式不返回 ok=True（因为无法自动确认状态），但也不把
    「无设备」当作阻断性错误，而是给出手动操作指引。
    """
    online = adb_utils.adb_devices_online()
    if not online:
        return (False,
                ["ℹ️ 未检测到 adb 设备（豆包自动检测不可用）",
                 "   程序进入【手动模式】：请人工确认豆包已打开、处于对话界面、未被遮挡，"
                 "并手动完成发送/操作；或在手机上开启USB调试后重连后重试自动检测。"],
                "offline")

    problems = []
    # 0'. 灭屏 / 锁屏：先自动亮屏并拉起豆包（无锁屏或滑动锁屏可全自动完成）
    #     有 PIN/密码/图案锁屏则停在解锁界面，提示用户手动解锁后程序继续。
    off = wake_unlock.is_screen_off()
    if off or wake_unlock.is_keyguard_locked():
        ok_w, msg_w, need_unlock = wake_unlock.ensure_doubao_awake_and_foreground(
            enter_conversation=True)
        if need_unlock:
            # 锁屏需手动解，不阻断程序，但本次自检视为「未就绪」并给出指引
            return (False,
                    ["🔒 " + msg_w,
                     "   解锁后程序会自动重试就绪检测；或直接手动进入豆包对话页。"],
                    "online")
        # 已自动亮屏拉起（无锁屏场景）：把这条成功信息作为 ℹ️ 记录，并继续后续检测
        if ok_w:
            problems.append("ℹ️ " + msg_w)
    # 0. 豆包是否已安装
    inst = doubao_installed()
    if inst is False:
        return False, ["❌ 手机未安装豆包 APP（包名 " + DOUBAO_PKG + "）"
                       "：请先在手机上安装豆包后再使用"], "online"
    elif inst is None:
        problems.append("ℹ️ 无法确认豆包是否已安装（adb 命令异常），请人工确认")

    # 1. 运行 + 前台
    if not adb_utils.doubao_in_foreground():
        if doubao_running():
            problems.append("⚠️ 豆包在后台运行，未处于前台：请切到豆包并进入对话页")
        else:
            problems.append("⚠️ 豆包未运行：请先在手机上打开豆包 APP")
        return False, problems, "online"
    # 2. 对话界面
    conv = in_conversation_screen()
    if conv is False:
        problems.append("⚠️ 豆包不在对话界面：" + conversation_hint())
    elif conv is None:
        problems.append("ℹ️ 无法获取界面控件树，确认手机未锁屏/未卡顿")
    # 3. 遮挡
    occ, detail = is_occluded()
    if occ:
        problems.append("⚠️ 豆包界面被遮挡（" + detail + "）：请关闭弹窗/权限框/悬浮窗")
    elif occ is None:
        problems.append("ℹ️ 无法判定遮挡状态")
    # 4. 可发送
    sendable = can_send()
    if sendable is False:
        problems.append("⚠️ 当前无法向豆包输入：请确认输入框可点击、输入法已就绪")
    elif sendable is None:
        problems.append("ℹ️ 无法判定输入框可输入状态")
    ok = len(problems) == 0
    return ok, problems, "online"
