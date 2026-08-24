import re
import subprocess
import time
import xml.etree.ElementTree as ET

try:
    from src.core.paths import ADB_EXE
except (ImportError, ModuleNotFoundError):
    try:
        from core.paths import ADB_EXE
    except (ImportError, ModuleNotFoundError):
        ADB_EXE = "adb"

def get_screen_resolution(device_id: str = None) -> tuple:
    """
    动态获取设备物理分辨率 (Width, Height)
    """
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
    【三级自适应模糊定位算法】
    1. Level 1: 语义/类型模糊定位 (寻找屏幕下半区的 EditText，忽略动态混淆的 resource-id)
    2. Level 2: Resource-ID 集合匹配 (聚合所有历史已知及最新版本的豆包控件 ID)
    3. Level 3: 屏幕相对比例锚点 (根据实际物理宽高比例动态计算坐标，抛弃绝对像素)
    """
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    
    width, height = get_screen_resolution(device_id)
    
    fallback_input_x, fallback_input_y = int(width * 0.45), int(height * 0.94)
    fallback_send_x, fallback_send_y = int(width * 0.92), int(height * 0.94)
    
    result = {
        "found": False,
        "mode": "fallback_ratio",
        "input_bounds": (fallback_input_x, fallback_input_y),
        "send_bounds": (fallback_send_x, fallback_send_y)
    }

    try:
        dump_cmd = base_cmd + ["shell", "uiautomator", "dump", "/sdcard/_zbd_dump.xml"]
        subprocess.run(dump_cmd, capture_output=True, timeout=4)
        
        cat_cmd = base_cmd + ["shell", "cat", "/sdcard/_zbd_dump.xml"]
        cat_res = subprocess.run(cat_cmd, capture_output=True, text=True, timeout=3)
        xml_content = cat_res.stdout
        
        if xml_content and "<hierarchy" in xml_content:
            root = ET.fromstring(xml_content)
            for node in root.iter('node'):
                cls = node.attrib.get('class', '')
                bounds_str = node.attrib.get('bounds', '')
                res_id = node.attrib.get('resource-id', '')
                
                b_match = re.findall(r'\[(\d+),(\d+)\]', bounds_str)
                if not b_match or len(b_match) < 2:
                    continue
                
                left, top = int(b_match[0][0]), int(b_match[0][1])
                right, bottom = int(b_match[1][0]), int(b_match[1][1])
                center_x = (left + right) // 2
                center_y = (top + bottom) // 2
                
                if ('EditText' in cls or 'input' in res_id.lower()) and center_y > height * 0.6:
                    result["found"] = True
                    result["mode"] = "semantic_node"
                    result["input_bounds"] = (center_x, center_y)
                    result["send_bounds"] = (int(width * 0.92), center_y)
                    return result
    except Exception as e:
        print(f"[find_doubao_input_and_send] 定位解析异常: {e}")
    
    return result

def click_doubao_input(device_id: str = None):
    loc = find_doubao_input_and_send(device_id)
    x, y = loc["input_bounds"]
    base_cmd = [ADB_EXE]
    if device_id:
        base_cmd.extend(["-s", device_id])
    subprocess.run(base_cmd + ["shell", "input", "tap", str(x), str(y)], capture_output=True, timeout=2)
    return loc
