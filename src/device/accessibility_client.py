# ==============================================================================
# src/device/accessibility_client.py
# 无障碍 Agent 客户端 (HTTP 端口直连 12051 -> 内存级直驱豆包)
# ==============================================================================
import json
import subprocess
import time
import urllib.parse
import urllib.request

try:
    from src.core.paths import ADB_EXE
except (ImportError, ModuleNotFoundError):
    try:
        from core.paths import ADB_EXE
    except (ImportError, ModuleNotFoundError):
        ADB_EXE = "adb"


class AccessibilityAgentClient:
    def __init__(self, port: int = 12051, device_id: str = None):
        self.port = port
        self.device_id = device_id
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.ensure_adb_forward()

    def ensure_adb_forward(self) -> bool:
        """自动打通 PC 与手机 Agent 之间的 ADB 端口转发"""
        cmd = [ADB_EXE]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(["forward", f"tcp:{self.port}", f"tcp:{self.port}"])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            return res.returncode == 0
        except Exception:
            return False

    def is_agent_alive(self) -> bool:
        """检查手机端无障碍 Agent 是否正常运行中"""
        try:
            url = f"{self.base_url}/ping"
            req = urllib.request.Request(url, headers={"User-Agent": "ZhibodouClient"})
            with urllib.request.urlopen(req, timeout=0.8) as response:
                return response.status == 200
        except Exception:
            # 尝试重新 forward 再测一次
            self.ensure_adb_forward()
            try:
                with urllib.request.urlopen(f"{self.base_url}/ping", timeout=0.8) as response:
                    return response.status == 200
            except Exception:
                return False

    def send_text_direct(self, text: str) -> bool:
        """
        【Agent 核心功能 1: 内存级文本直注】
        直接在豆包当前输入框填入文字，零剪贴板、零输入法限制
        """
        try:
            encoded_text = urllib.parse.quote(text)
            url = f"{self.base_url}/set_text?text={encoded_text}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.5) as res:
                data = json.loads(res.read().decode("utf-8"))
                return data.get("success", False)
        except Exception as e:
            print(f"[AgentClient] 文本直注异常: {e}")
            return False

    def click_send_button(self) -> bool:
        """
        【Agent 核心功能 2: 控件级发送点击】
        通过无障碍树直接寻找并点击豆包的发送按钮
        """
        try:
            # 尝试按关键词/描述点击“发送”
            url = f"{self.base_url}/click?text={urllib.parse.quote('发送')}"
            with urllib.request.urlopen(url, timeout=1.5) as res:
                data = json.loads(res.read().decode("utf-8"))
                if data.get("success"):
                    return True
        except Exception:
            pass

        # 备选：请求 Agent 触发当前活动界面的发送动作
        try:
            url = f"{self.base_url}/action?type=send"
            with urllib.request.urlopen(url, timeout=1.5) as res:
                data = json.loads(res.read().decode("utf-8"))
                return data.get("success", False)
        except Exception:
            return False

# 单例
agent_client = AccessibilityAgentClient()