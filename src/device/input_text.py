# ==============================================================================
# src/device/input_text.py
# 智播豆 2.0 终极完整自包含文本注入引擎
# 双模自适应：1. 优先无障碍 Agent 内存直注； 2. 自动降级纯原生 ADB 剪贴板直注
# ==============================================================================
import re
import subprocess
import time
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    from src.core.paths import ADB_EXE
except (ImportError, ModuleNotFoundError):
    try:
        from core.paths import ADB_EXE
    except (ImportError, ModuleNotFoundError):
        ADB_EXE = "adb"


# ==============================================================================
# 1. 无障碍 Agent 客户端 (自包含内嵌，不依赖外部文件)
# ==============================================================================

def _ensure_agent_forward(device_id: str = None, port: int = 12051) -> bool:
    """自动打通 PC 与手机 Agent 之间的 ADB 端口转发"""
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    cmd = base_cmd + ["forward", f"tcp:{port}", f"tcp:{port}"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False


def _is_agent_alive(port: int = 12051) -> bool:
    """检查手机端无障碍 Agent HTTP 服务是否存活"""
    try:
        url = f"http://127.0.0.1:{port}/ping"
        req = urllib.request.Request(url, headers={"User-Agent": "ZBDClient"})
        with urllib.request.urlopen(req, timeout=0.5) as res:
            return res.status == 200
    except Exception:
        return False


def _send_via_agent(text: str, port: int = 12051, click_send: bool = True) -> bool:
    """通过无障碍 Agent 内存直注文字与点击"""
    try:
        # 手机端当前返回 {"code": 0, "message": "ok"}，旧客户端只认
        # {"success": true}，会误判失败并重复走 ADB 兜底。
        enc = urllib.parse.quote(text)
        action = "inject_and_send" if click_send else "set_text"
        url_text = f"http://127.0.0.1:{port}/{action}?text={enc}"
        with urllib.request.urlopen(url_text, timeout=1.5) as r1:
            data = json.loads(r1.read().decode("utf-8"))
            success = data.get("success") is True or data.get("code") == 0
            if not success:
                return False
        return True
    except Exception as e:
        print(f"[input_text] Agent 注入异常: {e}")
        return False


# ==============================================================================
# 2. 原生 ADB 剪贴板与屏幕动态比例注入 (自包含内嵌降级通道)
# ==============================================================================

def _adb_base(device_id: str = None) -> list:
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    return base_cmd


def _parse_bounds(value: str):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value or "")
    if not match:
        return None
    left, top, right, bottom = map(int, match.groups())
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _find_semantic_node(xml_text: str, role: str):
    """从 Android UI 树按控件语义查找，绝不猜测屏幕坐标。"""
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError):
        return None
    candidates = []
    for node in root.iter("node"):
        resource_id = (node.attrib.get("resource-id") or "").lower()
        class_name = (node.attrib.get("class") or "").lower()
        text = node.attrib.get("text") or ""
        desc = node.attrib.get("content-desc") or ""
        bounds = _parse_bounds(node.attrib.get("bounds") or "")
        if not bounds:
            continue
        if role == "input":
            if resource_id.endswith("/input_text"):
                score = 100
            elif class_name == "android.widget.edittext":
                score = 70
            else:
                continue
        elif role == "text_toggle":
            if resource_id.endswith("/action_input") or "文本输入" in desc + text:
                score = 100
            else:
                continue
        elif role == "send":
            if resource_id.endswith("/action_send"):
                score = 100
            elif "发送" in desc or text == "发送":
                score = 80
            else:
                continue
        else:
            return None
        # 同类节点优先屏幕下方，避免搜索框等 EditText。
        candidates.append((score, bounds[1], node.attrib))
    return max(candidates, default=None, key=lambda item: (item[0], item[1]))[2] if candidates else None


def _dump_ui_xml(base_cmd: list) -> tuple:
    remote_path = "/sdcard/zbd_ui.xml"
    try:
        dumped = subprocess.run(
            base_cmd + ["shell", "uiautomator", "dump", remote_path],
            capture_output=True, text=True, timeout=8,
        )
        pulled = subprocess.run(
            base_cmd + ["exec-out", "cat", remote_path],
            capture_output=True, timeout=4,
        )
        xml_text = pulled.stdout.decode("utf-8", errors="replace")
        if "<hierarchy" not in xml_text:
            detail = (dumped.stderr or dumped.stdout or "无法读取 UI 树").strip()
            return None, detail[-300:]
        return xml_text, ""
    except Exception as exc:
        return None, str(exc)


def _tap_node(base_cmd: list, node) -> bool:
    bounds = _parse_bounds((node or {}).get("bounds") or "")
    if not bounds:
        return False
    left, top, right, bottom = bounds
    result = subprocess.run(
        base_cmd + ["shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2)],
        capture_output=True, timeout=2,
    )
    return result.returncode == 0


def _send_via_native_adb(text: str, device_id: str = None, click_send: bool = True) -> tuple:
    """
    【原生 ADB 语义控件注入与发送】
    1. 从 UI 树按 resource-id/class 定位输入框
    2. Android 10+ 原生 cmd clipboard set 写入剪贴板 + keyevent 279 粘贴
    3. 按 action_send/“发送”语义定位按钮；找不到就失败，绝不猜坐标
    """
    base_cmd = _adb_base(device_id)

    try:
        xml_text, error = _dump_ui_xml(base_cmd)
        if not xml_text:
            return False, "无法读取豆包界面控件：%s" % error
        input_node = _find_semantic_node(xml_text, "input")
        if not input_node:
            toggle = _find_semantic_node(xml_text, "text_toggle")
            if toggle and _tap_node(base_cmd, toggle):
                time.sleep(0.3)
                xml_text, error = _dump_ui_xml(base_cmd)
                input_node = _find_semantic_node(xml_text, "input") if xml_text else None
        if not input_node:
            return False, "当前不是豆包对话输入界面或未找到输入框；请返回聊天页，并在新手机安装启用智播豆无障碍 Agent"

        # 1. 点击输入框获取焦点
        if not _tap_node(base_cmd, input_node):
            return False, "豆包输入框控件点击失败"
        time.sleep(0.12)

        # 2. 写入手机原生剪贴板 (转义特殊字符)
        safe_text = text.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        clipboard = subprocess.run(
            base_cmd + ["shell", f'cmd clipboard set "{safe_text}"'],
            capture_output=True, text=True, timeout=3,
        )
        if clipboard.returncode != 0:
            return False, "新手机原生剪贴板写入失败，请安装并启用智播豆无障碍 Agent"
        time.sleep(0.08)

        # 3. 模拟系统粘贴键 (KEYCODE_PASTE = 279)
        subprocess.run(base_cmd + ["shell", "input", "keyevent", "279"], capture_output=True, timeout=2)

        # 4. 点击右下角发送按钮
        if click_send:
            time.sleep(0.3)
            xml_text, error = _dump_ui_xml(base_cmd)
            send_node = _find_semantic_node(xml_text, "send") if xml_text else None
            if not send_node:
                return False, "文本已尝试写入，但豆包发送按钮未出现；已停止，未执行坐标猜测"
            if not _tap_node(base_cmd, send_node):
                return False, "豆包发送按钮控件点击失败"

        return True, "原生 ADB 按控件语义注入并发送成功"

    except Exception as e:
        return False, f"原生 ADB 注入异常: {e}"


# ==============================================================================
# 3. 统一对外全功能入口 (send_text_to_doubao)
# ==============================================================================

def send_text_to_doubao(text: str, device_id: str = None, click_send: bool = True) -> tuple:
    """
    【向豆包发送文本的统一全功能入口】
    返回值: (bool, str) -> (是否成功, 说明信息)
    """
    text = (text or "").strip()
    if not text:
        return False, "发送文本为空"

    # 尝试打通 Agent 端口转发
    _ensure_agent_forward(device_id, port=12051)

    # 1. 优先尝试无障碍 Agent
    if _is_agent_alive(port=12051):
        print("[Input] 🚀 检测到手机端 Accessibility Agent 运行中，正在执行内存直驱注入...")
        ok = _send_via_agent(text, port=12051, click_send=click_send)
        if ok:
            return True, "已通过无障碍 Agent 成功注入并发送"
        print("[Input] ⚠️ Agent 注入返回失败，自动切换原生 ADB 通道兜底...")

    # 2. 自动降级走纯原生 ADB 剪贴板注入
    print("[Input] ⚠️ 新手机未连接无障碍 Agent，改用 ADB 控件语义兜底（不使用固定坐标）...")
    return _send_via_native_adb(text, device_id=device_id, click_send=click_send)


# ==============================================================================
# 兼容旧代码调用的空桩 (保证老模块直接调用不报错)
# ==============================================================================
ADB_IME_ID = ""
def _ime_current(device_id=None): return ""
def check_adbkeyboard_installed(device_id=None): return True
def check_clipper_installed(device_id=None): return True
def install_adbkeyboard(device_id=None): return True
def set_adbkeyboard_ime(device_id=None): return True
def reset_default_ime(device_id=None): return True
