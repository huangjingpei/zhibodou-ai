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
        # 1. 内存级设置文本
        enc = urllib.parse.quote(text)
        url_text = f"http://127.0.0.1:{port}/set_text?text={enc}"
        with urllib.request.urlopen(url_text, timeout=1.5) as r1:
            data = json.loads(r1.read().decode("utf-8"))
            if not data.get("success", False):
                return False

        # 2. 点击发送
        if click_send:
            time.sleep(0.1)
            url_click = f"http://127.0.0.1:{port}/click?text={urllib.parse.quote('发送')}"
            try:
                urllib.request.urlopen(url_click, timeout=1.5)
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"[input_text] Agent 注入异常: {e}")
        return False


# ==============================================================================
# 2. 原生 ADB 剪贴板与屏幕动态比例注入 (自包含内嵌降级通道)
# ==============================================================================

def _get_screen_size(device_id: str = None) -> tuple:
    """动态获取物理屏幕分辨率"""
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    try:
        res = subprocess.run(base_cmd + ["shell", "wm", "size"], capture_output=True, text=True, timeout=2)
        m = re.search(r'(\d+)x(\d+)', res.stdout or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1080, 2400


def _send_via_native_adb(text: str, device_id: str = None, click_send: bool = True) -> tuple:
    """
    【纯原生 ADB 剪贴板注入与发送】
    1. 动态自适应屏幕比例点击输入框
    2. Android 10+ 原生 cmd clipboard set 写入剪贴板 + keyevent 279 粘贴
    3. 点击右下角发送按钮
    """
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])

    try:
        width, height = _get_screen_size(device_id)
        input_x, input_y = int(width * 0.45), int(height * 0.94)
        send_x, send_y = int(width * 0.92), int(height * 0.94)

        # 1. 点击输入框获取焦点
        subprocess.run(base_cmd + ["shell", "input", "tap", str(input_x), str(input_y)], capture_output=True, timeout=2)
        time.sleep(0.12)

        # 2. 写入手机原生剪贴板 (转义特殊字符)
        safe_text = text.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        subprocess.run(base_cmd + ["shell", f'cmd clipboard set "{safe_text}"'], capture_output=True, text=True, timeout=3)
        time.sleep(0.08)

        # 3. 模拟系统粘贴键 (KEYCODE_PASTE = 279)
        subprocess.run(base_cmd + ["shell", "input", "keyevent", "279"], capture_output=True, timeout=2)

        # 4. 点击右下角发送按钮
        if click_send:
            time.sleep(0.15)
            subprocess.run(base_cmd + ["shell", "input", "tap", str(send_x), str(send_y)], capture_output=True, timeout=2)

        return True, "原生 ADB 注入并发送成功"

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
    print("[Input] ⚡ 正在通过原生 ADB 剪贴板通道下发...")
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