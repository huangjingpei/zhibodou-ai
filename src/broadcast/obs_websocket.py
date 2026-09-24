"""OBS WebSocket 远程控制与流媒体源自动注入服务。

支持通过 OBS Studio 28+ 原生内置的 obs-websocket (v5 协议) 及其向前兼容协议，
实现一键检测 OBS 连接状态并自动在 OBS 当前场景中添加或更新网络流媒体源。
用户在界面勾选后，解析出的高质量直播流 (FLV / M3U8) 将自动无缝注入 OBS 作为输入源。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import socket
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_OBS_PORT = 5544
ALT_OBS_PORTS = (5544, 4455, 4444)


def check_obs_websocket_port(host: str = "127.0.0.1", port: int = DEFAULT_OBS_PORT, timeout: float = 0.8) -> bool:
    """快速探测 OBS WebSocket 端口是否处于监听接收状态。

    :param host: OBS 所在主机地址，默认 127.0.0.1
    :param port: OBS WebSocket 端口，默认 5544
    :param timeout: 超时时间（秒）
    :return: 端口是否可连接
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        return result == 0
    except Exception:
        return False


def probe_obs_ports(host: str = "127.0.0.1") -> Optional[int]:
    """探测常见的 OBS 端口，返回首个可用的端口号，若均未开放返回 None。"""
    for p in ALT_OBS_PORTS:
        if check_obs_websocket_port(host=host, port=p, timeout=0.4):
            return p
    return None


class ObsWebSocketClient:
    """轻量级 OBS WebSocket 客户端 (专精于场景查询与流媒体源创建/更新)。"""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_OBS_PORT, password: str = "", timeout: float = 3.0):
        self.host = host
        self.port = int(port)
        self.password = password or ""
        self.timeout = timeout
        self.ws = None
        self._identified = False

    def connect(self) -> Tuple[bool, str]:
        """建立 WebSocket 连接并完成 OBS v5 握手认证。"""
        try:
            import websocket
        except ImportError:
            return False, "Python 环境缺少 websocket-client 依赖，请运行 pip install websocket-client"

        # 1. 优先端口预检
        if not check_obs_websocket_port(self.host, self.port, timeout=1.0):
            found_alt = probe_obs_ports(self.host)
            if found_alt and found_alt != self.port:
                return False, f"未在端口 {self.port} 检测到 OBS，但在端口 {found_alt} 发现了活动服务，请将端口配置调整为 {found_alt}"
            return False, f"未检测到 OBS WebSocket 服务 (端口 {self.port})！\n请启动 OBS Studio，并在菜单【工具】->【WebSocket 服务器设置】中勾选【启用 WebSocket 服务器】，并将端口设置为 {self.port}。"

        try:
            uri = f"ws://{self.host}:{self.port}"
            self.ws = websocket.create_connection(uri, timeout=self.timeout)

            # 读取第一帧：OpCode 0 (Hello)
            raw = self.ws.recv()
            hello = json.loads(raw)
            if hello.get("op") != 0:
                return False, f"无法识别的 OBS 握手响应: {raw[:100]}"

            d = hello.get("d", {})
            auth_info = d.get("authentication")

            # 准备 Identify 报文 (OpCode 1)
            identify_d: Dict[str, Any] = {"rpcVersion": 1}

            if auth_info:
                # 需要密码认证
                challenge = auth_info.get("challenge", "")
                salt = auth_info.get("salt", "")
                if not self.password:
                    return False, f"OBS WebSocket 启用了密码验证，但当前未提供连接密码"

                # 协议: base64(sha256(base64(sha256(password + salt)) + challenge))
                secret_hash = hashlib.sha256((self.password + salt).encode("utf-8")).digest()
                secret_b64 = base64.b64encode(secret_hash).decode("utf-8")
                auth_hash = hashlib.sha256((secret_b64 + challenge).encode("utf-8")).digest()
                auth_b64 = base64.b64encode(auth_hash).decode("utf-8")
                identify_d["authentication"] = auth_b64

            # 发送 Identify
            self.ws.send(json.dumps({"op": 1, "d": identify_d}))

            # 等待 Identified 响应 (OpCode 2)
            raw2 = self.ws.recv()
            ident_resp = json.loads(raw2)
            if ident_resp.get("op") == 2:
                self._identified = True
                return True, "OBS WebSocket 连接并认证成功"
            else:
                return False, f"OBS 认证失败: {ident_resp.get('d', {}).get('error', raw2)}"

        except Exception as e:
            self.close()
            return False, f"连接 OBS WebSocket 异常: {e}"

    def send_request(self, request_type: str, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """向 OBS 发送 RPC 请求并等待响应 (OpCode 6 -> OpCode 7)。"""
        if not self.ws or not self._identified:
            return {"success": False, "message": "尚未与 OBS 建立有效连接"}

        req_id = f"req_{request_type}"
        msg = {
            "op": 6,
            "d": {
                "requestType": request_type,
                "requestId": req_id,
                "requestData": request_data or {},
            },
        }

        try:
            self.ws.send(json.dumps(msg))
            # 循环接收直到匹配当前 requestId 的响应
            while True:
                resp_raw = self.ws.recv()
                data = json.loads(resp_raw)
                if data.get("op") == 7 and data.get("d", {}).get("requestId") == req_id:
                    d = data["d"]
                    status = d.get("requestStatus", {})
                    result = status.get("result", False)
                    resp_data = d.get("responseData", {})
                    return {
                        "success": result,
                        "code": status.get("code"),
                        "comment": status.get("comment", ""),
                        "data": resp_data,
                    }
        except Exception as e:
            return {"success": False, "message": f"发送请求 {request_type} 失败: {e}"}

    def get_current_program_scene(self) -> Optional[str]:
        """获取 OBS 当前活动（程序预览）场景名称。"""
        res = self.send_request("GetCurrentProgramScene")
        if res.get("success"):
            data = res.get("data", {})
            return data.get("currentProgramSceneName") or data.get("sceneName")
        return None

    def add_or_update_stream_source(
        self,
        stream_url: str,
        source_name: str = "智播豆网络流",
        scene_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """在 OBS 当前场景中添加或更新网络流媒体源 (ffmpeg_source)。

        :param stream_url: 直播流地址 (FLV / M3U8)
        :param source_name: OBS 中的源名称，默认 "智播豆网络流"
        :param scene_name: 目标场景名称，若为 None 则自动获取当前活动场景
        :return: 结果字典 {"success": bool, "action": "created"|"updated", "message": str}
        """
        if not scene_name:
            scene_name = self.get_current_program_scene()
            if not scene_name:
                return {"success": False, "message": "未能获取 OBS 当前活动场景，请确认 OBS 中已有场景"}

        # 网络流配置项 (ffmpeg_source 标准配置)
        input_settings = {
            "is_local_file": False,
            "input": stream_url,
            "restart_on_activate": True,
            "buffering_mb": 2,
            "reconnect_delay_sec": 2,
            "hw_decode": True,
            "clear_on_media_end": False,
        }

        # 1. 优先尝试更新已存在的源属性 (SetInputSettings)
        update_res = self.send_request(
            "SetInputSettings",
            {
                "inputName": source_name,
                "inputSettings": input_settings,
                "overlay": True,
            },
        )

        if update_res.get("success"):
            return {
                "success": True,
                "action": "updated",
                "scene": scene_name,
                "source": source_name,
                "message": f"已成功更新 OBS 场景【{scene_name}】中的流媒体源【{source_name}】！",
            }

        # 2. 若源不存在，则在当前场景中创建新源 (CreateInput)
        create_res = self.send_request(
            "CreateInput",
            {
                "sceneName": scene_name,
                "inputName": source_name,
                "inputKind": "ffmpeg_source",
                "inputSettings": input_settings,
                "sceneItemEnabled": True,
            },
        )

        if create_res.get("success"):
            return {
                "success": True,
                "action": "created",
                "scene": scene_name,
                "source": source_name,
                "message": f"已成功在 OBS 场景【{scene_name}】中创建并添加流媒体源【{source_name}】！",
            }
        else:
            comment = create_res.get("comment") or create_res.get("message")
            return {
                "success": False,
                "message": f"在 OBS 中创建源失败: {comment}",
            }

    def close(self):
        """关闭 WebSocket 连接。"""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._identified = False


def push_stream_to_obs(
    stream_url: str,
    host: str = "127.0.0.1",
    port: int = DEFAULT_OBS_PORT,
    password: str = "",
    source_name: str = "智播豆网络流",
) -> Dict[str, Any]:
    """一键将流地址推送到 OBS Studio 的高层接口。

    若 OBS 未开启或端口未配置，返回明确友好的引导提示。
    :param stream_url: 解析出的直播网络流地址
    :param host: OBS 地址
    :param port: OBS WebSocket 端口，默认 5544
    :param password: 连接密码（若有）
    :param source_name: 源名称
    :return: {"success": bool, "port_open": bool, "message": str}
    """
    if not stream_url:
        return {"success": False, "port_open": False, "message": "直播流地址为空，请先成功解析直播间"}

    client = ObsWebSocketClient(host=host, port=port, password=password)
    ok, msg = client.connect()
    if not ok:
        client.close()
        return {"success": False, "port_open": False, "message": msg}

    try:
        res = client.add_or_update_stream_source(stream_url=stream_url, source_name=source_name)
        return {
            "success": res.get("success", False),
            "port_open": True,
            "scene": res.get("scene", ""),
            "source": res.get("source", source_name),
            "message": res.get("message", ""),
        }
    finally:
        client.close()
