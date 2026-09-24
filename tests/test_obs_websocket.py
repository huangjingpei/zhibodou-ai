"""OBS WebSocket 远程控制与流媒体源自动注入单元测试。"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath("src"))

from broadcast.obs_websocket import (
    ObsWebSocketClient,
    check_obs_websocket_port,
    probe_obs_ports,
    push_stream_to_obs,
)


class TestObsWebSocket(unittest.TestCase):
    """测试 OBS WebSocket 端口探测与协议交互。"""

    def test_check_port_closed(self):
        """测试未开启的随机端口，应快速返回 False。"""
        # 挑选一个极不可能被监听的端口
        result = check_obs_websocket_port(host="127.0.0.1", port=59999, timeout=0.2)
        self.assertFalse(result)

    def test_probe_obs_ports_none_when_closed(self):
        """当所有 OBS 端口均未开启时，返回 None。"""
        with patch("broadcast.obs_websocket.check_obs_websocket_port", return_value=False):
            res = probe_obs_ports()
            self.assertIsNone(res)

    def test_probe_obs_ports_found(self):
        """当 5544 开启时，返回 5544。"""
        def mock_check(host, port, timeout):
            return port == 5544

        with patch("broadcast.obs_websocket.check_obs_websocket_port", side_effect=mock_check):
            res = probe_obs_ports()
            self.assertEqual(res, 5544)

    def test_push_stream_to_obs_port_closed_message(self):
        """当 OBS 端口 5544 未开启时，push_stream_to_obs 应返回明确提示用户开启服务的文案。"""
        with patch("broadcast.obs_websocket.check_obs_websocket_port", return_value=False), \
             patch("broadcast.obs_websocket.probe_obs_ports", return_value=None):
            res = push_stream_to_obs("http://live.test.com/stream.flv", port=5544)
            self.assertFalse(res.get("success"))
            self.assertFalse(res.get("port_open"))
            msg = res.get("message", "")
            self.assertIn("未检测到 OBS WebSocket 服务", msg)
            self.assertIn("5544", msg)
            self.assertIn("WebSocket 服务器设置", msg)

    def test_obs_websocket_client_mock_handshake_and_create_source(self):
        """测试 OBS WebSocket 客户端完整握手并创建媒体源流程。"""
        mock_ws = MagicMock()

        # 模拟响应队列：
        # 1. OpCode 0 (Hello)
        # 2. OpCode 2 (Identified)
        # 3. OpCode 7 (Response for GetCurrentProgramScene -> 返回当前场景)
        # 4. OpCode 7 (Response for SetInputSettings -> 失败，表示源不存在)
        # 5. OpCode 7 (Response for CreateInput -> 成功)
        responses = [
            json.dumps({"op": 0, "d": {"obsWebSocketVersion": "5.0.0", "rpcVersion": 1}}),
            json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}),
            json.dumps({
                "op": 7,
                "d": {
                    "requestId": "req_GetCurrentProgramScene",
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": {"currentProgramSceneName": "主直播场景"},
                },
            }),
            json.dumps({
                "op": 7,
                "d": {
                    "requestId": "req_SetInputSettings",
                    "requestStatus": {"result": False, "code": 600, "comment": "Source not found"},
                    "responseData": {},
                },
            }),
            json.dumps({
                "op": 7,
                "d": {
                    "requestId": "req_CreateInput",
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": {},
                },
            }),
        ]
        mock_ws.recv.side_effect = responses

        with patch("broadcast.obs_websocket.check_obs_websocket_port", return_value=True), \
             patch("websocket.create_connection", return_value=mock_ws):
            res = push_stream_to_obs("http://live.test.com/stream.m3u8", port=5544, source_name="测试流")
            self.assertTrue(res.get("success"))
            self.assertTrue(res.get("port_open"))
            self.assertEqual(res.get("scene"), "主直播场景")
            self.assertEqual(res.get("source"), "测试流")
            self.assertIn("已成功在 OBS 场景【主直播场景】中创建并添加流媒体源", res.get("message"))


if __name__ == "__main__":
    unittest.main()
