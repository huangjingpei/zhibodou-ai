# ====================== 文本输入（豆包对话框） ======================
# 统一发送入口：清空输入框 → ADBKeyboard 直输(绕开剪贴板) → 控件定位点击发送(带验证)。
# ADBKeyboard 未安装时降级为 clipper 剪贴板方案（仅老系统可用）。
import base64
import time
from device import adb_utils
from device import ui_locator
from core.doubao import DOUBAO_INPUT_ID
from gui.ui import set_status

ADB_IME_ID = "com.android.adbkeyboard/.AdbIME"


def check_adbkeyboard_installed():
    """检测手机是否装了 ADBKeyboard 输入法"""
    out, _ = adb_utils.adb_shell("pm", "list", "packages")
    return "adbkeyboard" in out.lower()


def get_adbkeyboard_ime_id():
    """动态解析手机上 ADBKeyboard 的真实 IME ID（不同 ROM/版本 ID 可能不同）。
    优先从 `ime list` 解析，找不到则用标准 ID 兜底；后续发送时会先用 `ime enable` 启用。"""
    def _parse(out):
        for line in (out or "").splitlines():
            low = line.lower()
            if "adbkeyboard" in low:
                line = line.strip()
                if line.startswith("mId="):
                    return line[4:].split()[0]
                if ":" in line:
                    return line.split(":")[0].strip()
                return line
        return None
    try:
        out, _ = adb_utils.adb_shell("ime", "list", "-s")
        idv = _parse(out)
        if idv:
            return idv
        out, _ = adb_utils.adb_shell("ime", "list")
        idv = _parse(out)
        if idv:
            return idv
    except Exception:
        pass
    return "com.android.adbkeyboard/.AdbIME"  # 标准兜底


def _ime_current():
    """获取当前默认输入法 id"""
    out, _ = adb_utils.adb_shell("settings", "get", "secure", "default_input_method")
    return out.strip()


def adb_input_text_via_ime(text):
    """通过 ADBKeyboard 广播把文字直接输入聚焦的输入框（base64 传输，无编码问题）"""
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    out, _ = adb_utils.adb_shell("am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64)
    return ("result=0" in out), ("" if "result=0" in out else out.strip()[-80:])


def _clear_input_box():
    """控件定位聚焦输入框并清空旧草稿（Ctrl+A 全选删除 + 退格兜底）。
    ⚠️ 旧草稿不清掉，后面的"输入验证"会出现假阳性（把草稿当成新输入的内容）！"""
    xml = ui_locator._dump_ui_xml()
    if not xml:
        return False
    # 语音模式下先切回文字模式
    if ui_locator._find_id_bounds(xml, DOUBAO_INPUT_ID) is None:
        if not ui_locator._switch_to_text_mode():
            return False
        xml = ui_locator._dump_ui_xml()
    b = ui_locator._find_id_bounds(xml, DOUBAO_INPUT_ID)
    if not b:
        return False
    adb_utils.adb_tap((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)   # 聚焦输入框
    time.sleep(0.5)
    try:
        adb_utils.adb_shell("input", "keycombination", "113", "29")   # Ctrl+A 全选
        time.sleep(0.2)
        adb_utils.adb_shell("input", "keyevent", "67")                # 删除选中
        time.sleep(0.35)
    except Exception:
        pass
    t = ui_locator._find_node_text(ui_locator._dump_ui_xml(), DOUBAO_INPUT_ID)
    if t and t != "" and "发消息" not in t:
        # 全选失败 → 退格连发兜底
        for _ in range(60):
            adb_utils.adb_shell("input", "keyevent", "67")
        time.sleep(0.3)
        t = ui_locator._find_node_text(ui_locator._dump_ui_xml(), "com.larus.nova:id/input_text")
    return t is None or t == "" or "发消息" in t


def send_text_to_doubao(text):
    """统一发送入口（开播预演/直播话术共用）。
    返回 (ok, err_msg)。"""
    text = text.strip()
    if not text:
        return False, "发送内容为空"

    # 0) 发送前置：若灭屏/锁屏，先自动亮屏拉起豆包（无锁屏全自动；
    #    有锁屏则提示手动解锁后由调用方重试）。避免「黑屏假阴性」误报。
    from device import wake_unlock
    off = wake_unlock.is_screen_off()
    locked = wake_unlock.is_keyguard_locked()
    if off or locked:
        ok_w, msg_w, need_unlock = wake_unlock.ensure_doubao_awake_and_foreground(
            enter_conversation=True)
        if need_unlock:
            return False, "手机处于锁屏状态：" + msg_w
        if not ok_w:
            return False, "灭屏恢复失败：" + msg_w

    # 1) 确保文字模式 + 聚焦并清空输入框（清掉旧草稿，杜绝假阳性）
    if not _clear_input_box():
        return False, "无法定位/清空豆包输入框(豆包不在前台对话页?)"

    # 2) 输入文字
    if check_adbkeyboard_installed():
        adb_ime = get_adbkeyboard_ime_id()
        prev_ime = _ime_current()
        # 关键：未启用的输入法 `ime set` 会报 Unknown，先 enable 再 set
        try:
            adb_utils.adb_shell("ime", "enable", adb_ime)
        except Exception:
            pass
        time.sleep(0.3)
        adb_utils.adb_shell("ime", "set", adb_ime)
        time.sleep(0.6)
        # 切换输入法可能使豆包输入框失焦，重新聚焦后再发广播
        ui_locator.tap_input_box()
        time.sleep(0.4)
        ok, err = adb_input_text_via_ime(text)
        # 输完恢复原输入法，避免影响手机正常打字
        if prev_ime and prev_ime != adb_ime:
            try:
                adb_utils.adb_shell("ime", "set", prev_ime)
            except Exception:
                pass
        if not ok:
            return False, "ADBKeyboard 输入失败: " + err
        time.sleep(0.9)
        # 输入验证：连续 dump 2 次，避免 AI 流式回复导致 dump 偶发返回空状态
        # 严苛的"开头片段匹配"在 AI 动画期间容易假阴性，故改为"非空且非占位符"
        # 最终的"是否真的发送出去"由 tap_send_button 内的发送后验证把关
        input_ok = False
        for _ in range(2):
            t = ui_locator._find_node_text(ui_locator._dump_ui_xml(), "com.larus.nova:id/input_text")
            if t is not None and t != "" and "发消息" not in t:
                input_ok = True
                break
            time.sleep(1.2)
        if not input_ok:
            return False, "文字未出现在输入框(ADBKeyboard输入未生效)"
    else:
        # 降级路径：clipper 剪贴板 + keyevent 279 粘贴
        # ⚠️ Android 10+ 上 clipper 后台写剪贴板会被系统拒绝，仅老系统可用
        adb_utils.adb_set_phone_clipboard(text)
        time.sleep(0.4)
        adb_utils.adb_phone_paste()
        time.sleep(1.0)
        t = ui_locator._find_node_text(ui_locator._dump_ui_xml(), DOUBAO_INPUT_ID)
        if t is None or t == "" or "发消息" in t:
            return False, "粘贴失败：剪贴板没写进去(Android10+限制)。请安装 ADBKeyboard.apk"

    # 3) 控件定位点击发送（内含发送后验证 + 自动重试）
    if not ui_locator.tap_send_button():
        return False, "发送按钮点击未生效(多次重试后放弃)"
    return True, ""
