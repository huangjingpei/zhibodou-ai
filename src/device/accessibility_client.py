import json
import socket
import subprocess
import time
from typing import Optional, Dict, Any
from src.core.paths import ADB_EXE

class AccessibilityClient:
    """
    【方案 A 客户端：Python 与 Android 常驻无障碍 Agent 通信桥梁】
    
    协议规范：
    - 基于 TCP JSON-RPC (默认端口 18888)
    - 走 ADB forward tcp:18888 tcp:18888 建立极速回环
    - 单次发送耗时 < 3ms，零进程 fork、零坐标计算、零输入法切换
    """
    def __init__(self, device_id: Optional[str] = None, local_port: int = 18888):
        self.device_id = device_id
        self.local_port = local_port
        self.base_adb = [ADB_EXE]
        if device_id:
            self.base_adb.extend(["-s", device_id])
        self.setup_forward()

    def setup_forward(self) -> bool:
        """建立 ADB 端口映射"""
        cmd = self.base_adb + ["forward", f"tcp:{self.local_port}", "tcp:18888"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0

    def _call_rpc(self, request_payload: Dict[str, Any], timeout_sec: float = 3.0) -> Optional[Dict[str, Any]]:
        """发送 JSON-RPC 请求并获取响应"""
        try:
            with socket.create_connection(("127.0.0.1", self.local_port), timeout=timeout_sec) as s:
                raw_req = (json.dumps(request_payload, ensure_ascii=False) + "\n").encode('utf-8')
                s.sendall(raw_req)
                
                raw_resp = s.recv(4096).decode('utf-8').strip()
                if not raw_resp:
                    return None
                return json.loads(raw_resp)
        except Exception as e:
            return None

    def ping(self) -> bool:
        """探活无障碍服务 RPC"""
        resp = self._call_rpc({"action": "ping"}, timeout_sec=1.0)
        return resp is not None and resp.get("code") == 0

    def send_script_direct(self, text: str, click_send: bool = True) -> bool:
        """
        【一键直注并触发发送】
        由手机端无障碍服务在内存中直接触发 AccessibilityNodeInfo.performAction(ACTION_SET_TEXT)
        """
        resp = self._call_rpc({
            "action": "inject_and_send",
            "text": text,
            "click_send": click_send
        }, timeout_sec=4.0)

        if resp and resp.get("code") == 0:
            cost_ms = resp.get("cost_ms", 0)
            print(f"[AccessibilityClient] 话术直注成功！手机端耗时: {cost_ms}ms")
            return True
        else:
            print(f"[AccessibilityClient] 话术注入失败: {resp}")
            return False

    def clear_input(self) -> bool:
        """清空输入框"""
        resp = self._call_rpc({"action": "clear_text"}, timeout_sec=2.0)
        return resp is not None and resp.get("code") == 0

    def get_ui_status(self) -> Dict[str, Any]:
        """获取当前豆包 UI 控件状态"""
        resp = self._call_rpc({"action": "get_ui_state"}, timeout_sec=2.0)
        return resp.get("data", {}) if resp else {}
