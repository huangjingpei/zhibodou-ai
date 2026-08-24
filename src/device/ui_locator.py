# ====================== uiautomator 动态坐标定位（替换硬编码 P0 方案） ======================
# 通过 dump 控件树 + ElementTree 解析，精确取得豆包输入框/发送按钮坐标，
# 杜绝「点错坐标误入全屏输入页」的问题。全部基于控件树，绝不猜坐标。
import time
import re
import xml.etree.ElementTree as ET
import io
from device import adb_utils
from core.doubao import (DOUBAO_INPUT_ID, DOUBAO_SEND_ID, DOUBAO_FULLSCREEN_ID,
                   DOUBAO_VOICE_TOGGLE_ID)
from gui.ui import set_status

_BOUNDS_CACHE = {"input": None, "send": None, "time": 0.0}
_CACHE_TTL = 15  # 秒；正常发话术间隔 10-30s，15s 命中率近 100%，又能在 APP 改版时及时失效


def _dump_ui_xml(retries=2):
    """拉控件树 XML。注意：AI 流式回复时 dump 会卡住，超时后自动重试。"""
    for _ in range(retries + 1):
        adb_utils.adb_shell("uiautomator", "dump", "/sdcard/_zbd_uidump.xml", timeout=10)
        out, _ = adb_utils.adb_shell("cat", "/sdcard/_zbd_uidump.xml", timeout=10)
        if "<node" in out:
            return out
        time.sleep(1.5)
    return None


def _parse_bounds_str(s):
    """[x1,y1][x2,y2] -> (x1,y1,x2,y2) or None"""
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", s or "")
    return tuple(map(int, m.groups())) if m else None


def _find_node(xml_str, target_id, clickable_only=False):
    """ElementTree 精确解析：找 resource-id==target_id 的节点（可要求 clickable）。
    返回 Element 节点本身（可同时取 bounds/text），找不到返回 None。"""
    if not xml_str:
        return None
    try:
        root = ET.parse(io.StringIO(xml_str)).getroot()
    except Exception:
        return None
    for n in root.iter('node'):
        if n.get('resource-id') == target_id:
            if clickable_only and n.get('clickable') != 'true':
                continue
            return n
    return None


def _find_id_bounds(xml_str, target_id):
    """取 resource-id 节点的自身 bounds（ElementTree 精确解析，不会抓到邻节点）"""
    n = _find_node(xml_str, target_id)
    if n is None:
        return None
    return _parse_bounds_str(n.get('bounds', ''))


def _find_node_text(xml_str, target_id):
    """取 resource-id 节点的 text 属性（用于验证粘贴结果）"""
    n = _find_node(xml_str, target_id)
    return n.get('text', '') if n is not None else None


def _bounds_center(b):
    if not b:
        return None
    x1, y1, x2, y2 = b
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def get_input_center(force=False):
    """获取输入框中心点坐标 (x, y)；优先用缓存，过期或强制时重新 dump"""
    now = time.time()
    if not force and _BOUNDS_CACHE["input"] and (now - _BOUNDS_CACHE["time"]) < _CACHE_TTL:
        return _bounds_center(_BOUNDS_CACHE["input"])
    b = _find_id_bounds(_dump_ui_xml(), DOUBAO_INPUT_ID)
    if b:
        _BOUNDS_CACHE["input"] = b
        _BOUNDS_CACHE["time"] = now
    return _bounds_center(b)


def get_send_center(force=True):
    """获取发送按钮中心点。发送按钮仅在输入框有文字时存在，必须 force 刷新。
    多行文本会把输入框撑高，action_send 正上方会出现 action_full_screen(全屏输入)，
    两按钮 x 完全重叠——必须排除误点全屏按钮的可能。"""
    xml = _dump_ui_xml()  # 粘贴后控件树必变，不复用旧缓存
    if not xml:
        return None
    send_node = _find_node(xml, DOUBAO_SEND_ID, clickable_only=True)
    if send_node is None:
        return None
    send_b = _parse_bounds_str(send_node.get('bounds', ''))
    fs_b = _find_id_bounds(xml, DOUBAO_FULLSCREEN_ID)
    c = _bounds_center(send_b)
    # 双保险：点击点绝不能落在全屏按钮矩形内（防 bounds 异常/布局未稳定）
    if c and fs_b:
        fx1, fy1, fx2, fy2 = fs_b
        if fx1 <= c[0] <= fx2 and fy1 <= c[1] <= fy2:
            return None  # 坐标可疑，宁可不点
    if send_b:
        _BOUNDS_CACHE["send"] = send_b
    return c


def _switch_to_text_mode():
    """豆包停在语音模式时，点 action_input(文本输入) 切回文字模式。
    AI 正在流式回复时按钮位置可能反复重排，最多点 3 次，直到 input_text 出现"""
    for attempt in range(3):
        xml = _dump_ui_xml()
        if not xml:
            time.sleep(1.2)
            continue
        if _find_id_bounds(xml, DOUBAO_INPUT_ID):
            return True  # 已经是文字模式
        tb = _find_id_bounds(xml, DOUBAO_VOICE_TOGGLE_ID)
        if not tb:
            time.sleep(1.2)
            continue
        cx, cy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
        try:
            adb_utils.adb_tap(cx, cy)
        except Exception:
            time.sleep(1.2)
            continue
        time.sleep(1.3)  # 等输入框展开动画
    # 3 次都失败，最后再 dump 一次看是不是真的没切过来
    return bool(_dump_ui_xml() and _find_id_bounds(_dump_ui_xml(), DOUBAO_INPUT_ID))


def verify_input_has_text():
    """粘贴后验证输入框是否真的有文字。
    返回 True=有字 / False=空(粘贴失败) / None=无法判断(dump失败)"""
    xml = _dump_ui_xml()
    if not xml:
        return None
    t = _find_node_text(xml, DOUBAO_INPUT_ID)
    if t is None:
        return None
    return bool(t) and "发消息" not in t  # 占位符"发消息或按住说话..."不算有字


def tap_input_box():
    """点击输入框：自动处理语音模式 + uiautomator 动态定位"""
    pt = get_input_center()
    if not pt:
        # 输入框不存在——可能停在语音模式，尝试切换
        set_status("🔄输入框未找到，尝试从语音模式切换…", "#f59e0b")
        if _switch_to_text_mode():
            pt = get_input_center(force=True)
    if not pt:
        set_status("⚠️找不到豆包输入框：请确认豆包在前台对话页", "#ff6b6b")
        return False
    adb_utils.adb_tap(*pt)
    return True


def tap_send_button(retries=3):
    """控件对象定位点击发送按钮——绝不使用硬编码坐标。

    流程（每一步都基于控件树，不猜坐标）：
    1. dump 控件树 → ElementTree 解析 action_send 自身 bounds（要求 clickable）
    2. 点击点取按钮【下四分位】中心：多行文本会同时上移 send 和 fullscreen
       两个按钮，取下半部点击点远离紧贴上沿的全屏输入按钮
    3. 双重区域校验：点击点必须在 send 矩形内、且绝不能落在 fullscreen 矩形内
    4. 点击后【发送结果验证】：输入框清空 + action_send 消失；未生效则重试
    """
    for attempt in range(1, retries + 1):
        xml = _dump_ui_xml()
        if not xml:
            time.sleep(1.2)
            continue
        send_node = _find_node(xml, DOUBAO_SEND_ID, clickable_only=True)
        sb = _parse_bounds_str(send_node.get('bounds', '')) if send_node is not None else None
        if not sb:
            set_status(f"⚠️第{attempt}次未定位到发送按钮(输入框可能没文字)", "#f59e0b")
            time.sleep(1.2)
            continue
        cx = (sb[0] + sb[2]) // 2
        cy = sb[1] + (sb[3] - sb[1]) * 3 // 4   # 下四分位点，实测安全
        if not (sb[0] <= cx <= sb[2] and sb[1] <= cy <= sb[3]):
            set_status("⚠️发送按钮点击点越界，重试", "#f59e0b")
            continue
        fsb = _find_id_bounds(xml, DOUBAO_FULLSCREEN_ID)
        if fsb and fsb[0] <= cx <= fsb[2] and fsb[1] <= cy <= fsb[3]:
            set_status("⚠️点击点与全屏输入按钮重叠，放弃本次点击", "#ff6b6b")
            continue
        adb_utils.adb_tap(cx, cy)
        time.sleep(1.5)
        # 发送后验证：输入框清空 且 发送按钮消失
        xml2 = _dump_ui_xml()
        t = _find_node_text(xml2, DOUBAO_INPUT_ID)
        send_gone = xml2 and _find_node(xml2, DOUBAO_SEND_ID) is None
        if (t is None or t == "" or "发消息" in t) and send_gone:
            return True
        set_status(f"🔄第{attempt}次点击发送未生效(输入框仍有文字)，重试…", "#f59e0b")
        time.sleep(1.0)
    set_status("❌发送失败：多次点击发送按钮无效，请检查豆包页面", "#ff6b6b")
    return False
