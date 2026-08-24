import re
import subprocess
import time

try:
    from src.core.paths import ADB_EXE
except (ImportError, ModuleNotFoundError):
    try:
        from core.paths import ADB_EXE
    except (ImportError, ModuleNotFoundError):
        ADB_EXE = "adb"

try:
    from src.device.accessibility_client import agent_client
except Exception:
    agent_client = None


def get_screen_resolution(device_id: str = None) -> tuple:
    """动态获取物理屏幕分辨率（耗时 < 15ms）"""
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    try:
        res = subprocess.run(base_cmd + ["shell", "wm", "size"], capture_output=True, text=True, timeout=2)
        match = re.search(r'(\d+)x(\d+)', res.stdout)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1080, 2400


def find_doubao_input_and_send(device_id: str = None) -> dict:
    """
    【纯 Agent / 动态锚点定位】
    优先通过 Accessibility Agent 内存获取，次选屏幕动态比例，彻底杜绝 slow dump
    """
    # 1. 优先尝试无障碍 Agent 客户端 (内存级 < 5ms)
    if agent_client and agent_client.ping():
        input_node = agent_client.find_node_by_class("android.widget.EditText")
        if input_node and input_node.get("bounds"):
            b = input_node["bounds"]
            cx = (b[0] + b[2]) // 2
            cy = (b[1] + b[3]) // 2
            return {
                "found": True,
                "mode": "accessibility_agent",
                "input_bounds": (cx, cy),
                "send_bounds": (cx + 300, cy)
            }

    # 2. 降级方案：屏幕黄金比例自适应锚点
    width, height = get_screen_resolution(device_id)
    input_x, input_y = int(width * 0.45), int(height * 0.94)
    send_x, send_y = int(width * 0.92), int(height * 0.94)

    return {
        "found": True,
        "mode": "ratio_anchor",
        "input_bounds": (input_x, input_y),
        "send_bounds": (send_x, send_y)
    }


def click_doubao_input(device_id: str = None):
    """聚焦输入框"""
    loc = find_doubao_input_and_send(device_id)
    x, y = loc["input_bounds"]
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    subprocess.run(base_cmd + ["shell", "input", "tap", str(x), str(y)], capture_output=True, timeout=2)
    return loc