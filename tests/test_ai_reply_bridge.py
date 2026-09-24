"""单元测试：AI 弹幕回复 OBS 浏览器源桥接器、TTS 引擎与软件闪避算法。"""
import os
import sys
import unittest
import urllib.request
import json
import time

# 将 src 加入路径
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from unittest import mock
from unittest.mock import patch, MagicMock

import audio.obs_bridge as obs_bridge_mod
from audio.obs_bridge import OBSAudioBridge, get_obs_bridge
from audio.ducking import SoftwareAudioDuckingManager
from audio.tts_engine import WindowsSAPIEngine, create_tts_engine
from danma.hardware import detect_gpu_tier, ALL_MODE_DISPLAYS
from danma.llm_gateway import evaluate_and_reply, is_llm_configured


class TestOBSBridge(unittest.TestCase):
    """测试方案 A (OBS 浏览器源音频桥接器)。"""

    def setUp(self):
        self.bridge = OBSAudioBridge(port=18599)
        self.assertTrue(self.bridge.start())

    def tearDown(self):
        self.bridge.stop()

    def test_html_page_served(self):
        url = f"http://127.0.0.1:18599/danmu_audio"
        with urllib.request.urlopen(url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("Zhibodou AI Danmu Audio Bridge", content)
            self.assertIn("EventSource('/danmu/events')", content)

    def test_audio_cache_and_fetch(self):
        test_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00data"
        delivered = self.bridge.push_speech(test_wav, duration_sec=2.5, display_text="测试播报")
        self.assertEqual(delivered, 0)  # 没有客户端连接时 delivered 为 0

        # 从内部 cache 取得刚才推入的 audio_id
        with self.bridge._cache_lock:
            self.assertEqual(len(self.bridge._audio_cache), 1)
            audio_id = list(self.bridge._audio_cache.keys())[0]

        fetch_url = f"http://127.0.0.1:18599/audio/{audio_id}"
        with urllib.request.urlopen(fetch_url, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "audio/wav")
            data = resp.read()
            self.assertEqual(data, test_wav)

    def test_get_obs_bridge_from_config(self):
        with obs_bridge_mod._bridge_lock:
            old_bridge = obs_bridge_mod._global_bridge
            obs_bridge_mod._global_bridge = None
        try:
            with patch("settings.config.load_config", return_value={"obs_audio_port": 9999}):
                bridge = get_obs_bridge()
                self.assertEqual(bridge.port, 9999)
        finally:
            with obs_bridge_mod._bridge_lock:
                obs_bridge_mod._global_bridge = old_bridge

    def test_get_obs_bridge_explicit_port(self):
        with obs_bridge_mod._bridge_lock:
            old_bridge = obs_bridge_mod._global_bridge
            obs_bridge_mod._global_bridge = None
        try:
            with patch("settings.config.load_config", return_value={"obs_audio_port": 9999}):
                bridge = get_obs_bridge(port=8888)
                self.assertEqual(bridge.port, 8888)
        finally:
            with obs_bridge_mod._bridge_lock:
                obs_bridge_mod._global_bridge = old_bridge


class TestSoftwareDucking(unittest.TestCase):
    """测试软件算法音频闪避管理器。"""

    def test_duck_and_restore(self):
        manager = SoftwareAudioDuckingManager(target_process="mock_none.exe", duck_ratio=0.25)
        # 测试在目标进程未启动时调用不崩溃
        manager.duck(duration_sec=0.1)
        self.assertFalse(manager._is_ducked)  # 未找到 session 时不标记 ducked
        manager.restore()


class TestTTSEngine(unittest.TestCase):
    """测试 TTS 引擎原生 WAV 生成与时长计算。"""

    def test_sapi_synthesize_to_wav(self):
        engine = WindowsSAPIEngine()
        wav_bytes, duration = engine.synthesize_to_wav("老板大气！")
        self.assertTrue(len(wav_bytes) > 100)
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertTrue(duration > 0.1)

    def test_factory(self):
        e1 = create_tts_engine("playwright")
        self.assertTrue(e1.is_text_only())

class TestDanmuCollectorMethods(unittest.TestCase):
    """测试弹幕采集器类结构、方法绑定与模式配置。"""

    def test_danmu_collector_methods_exist(self):
        from danma.main import DanmuBrowserCollector, cleanup_browser_profile
        self.assertTrue(hasattr(DanmuBrowserCollector, "getUserData"))
        self.assertTrue(hasattr(DanmuBrowserCollector, "browser_launch"))
        self.assertTrue(hasattr(DanmuBrowserCollector, "browser_close"))
        self.assertTrue(hasattr(DanmuBrowserCollector, "PostMessage"))

        collector = DanmuBrowserCollector(
            platform="douyin",
            url="https://live.douyin.com/123456",
            online_only=True,
        )
        self.assertEqual(collector.platform, "douyin")
        self.assertTrue(collector.online_only)
        user_data = collector.getUserData()
        self.assertIn("DanmuBrowserProfile", user_data)

    def test_cleanup_browser_profile(self):
        from danma.main import cleanup_browser_profile
        cleanup_browser_profile(None)
        cleanup_browser_profile("")
        cleanup_browser_profile("non_existent_profile_path_12345")

    def test_ai_reply_worker_danmu_mode_config(self):
        from danma.ai_reply_worker import AIReplyWorker
        from settings import config
        worker = AIReplyWorker()

        with patch.object(config, "load_config", return_value={"danmu_mode": "【自适应】IndexTTS 旗舰语音 (显存≥8G)"}), \
             patch("danma.ai_reply_worker.create_tts_engine") as mock_create:
            worker.init_engines()
            mock_create.assert_called_once()
            self.assertEqual(mock_create.call_args[0][0], "index_tts")

        with patch.object(config, "load_config", return_value={"danmu_mode": "【自适应】MOSS-TTS-Nano 轻量语音 (显存4-8G)"}), \
             patch("danma.ai_reply_worker.create_tts_engine") as mock_create:
            worker.init_engines()
            self.assertEqual(mock_create.call_args[0][0], "moss_tts")

        with patch.object(config, "load_config", return_value={"danmu_mode": "【预留】Playwright 公屏文本回复 (低显存/无独显)"}), \
             patch("danma.ai_reply_worker.create_tts_engine") as mock_create:
            worker.init_engines()
            self.assertEqual(mock_create.call_args[0][0], "playwright")

    def test_douyin_pb_robustness(self):
        from live_plate.douyin.dy import douyin_pb, _extract_user
        self.assertEqual(douyin_pb(""), [])
        self.assertEqual(douyin_pb(None), [])
        self.assertEqual(douyin_pb(b"12345678"), [])
        name, img = _extract_user({})
        self.assertEqual(name, "游客")
        self.assertEqual(img, "")
        name2, img2 = _extract_user({"user": {"nickname": "测试用户", "avatarThumb": {"urlList": ["http://img.png"]}}})
        self.assertEqual(name2, "测试用户")
        self.assertEqual(img2, "http://img.png")

    def test_danmu_ui_display_chat_message(self):
        import tkinter as tk
        from screen import danmu
        from gui import ui
        root = tk.Tk()
        root.withdraw()
        try:
            txt = tk.Text(root)
            ui.txt_danmu = txt
            danmu._metrics_only = False

            # 模拟收到弹幕消息
            danmu.process_message({
                "type": "ChatMessage",
                "name": "忠实观众",
                "content": "主播这件衣服怎么卖？",
            })

            content = txt.get("1.0", tk.END)
            self.assertIn("忠实观众", content)
            self.assertIn("主播这件衣服怎么卖？", content)
        finally:
            root.destroy()
            ui.txt_danmu = None

    def test_danmu_low_cpu_execute_js(self):
        from danma.main import DanmuBrowserCollector
        collector = DanmuBrowserCollector(platform="douyin", url="https://live.douyin.com/123456")
        mock_page = mock.MagicMock()
        mock_page.url = "https://live.douyin.com/123456"
        collector.page = mock_page

        collector.execute_js()
        self.assertEqual(mock_page.evaluate.call_count, 2)
        title_eval = mock_page.evaluate.call_args_list[0][0][0]
        script_eval = mock_page.evaluate.call_args_list[1][0][0]
        self.assertIn("弹幕采集中", title_eval)
        self.assertIn("继续播放", script_eval)
        self.assertIn("el.pause()", script_eval)

    def test_should_abort_media_request(self):
        from danma.main import should_abort_media_request
        # 视频媒体类型或扩展名应当被识别以降低 CPU
        self.assertTrue(should_abort_media_request("https://pull.stream.com/live.flv", "other"))
        self.assertTrue(should_abort_media_request("https://pull.stream.com/live.m3u8?token=123", "xhr"))
        self.assertTrue(should_abort_media_request("https://pull.stream.com/segment.m4s", "fetch"))
        self.assertTrue(should_abort_media_request("https://pull.stream.com/segment.ts", "fetch"))
        self.assertTrue(should_abort_media_request("https://pull.stream.com/stream", "media"))

        # 图片、字体、脚本、网页自身等非音视频资源绝不被拦截，保证网页互动和弹幕正常
        self.assertFalse(should_abort_media_request("https://p3.douyinpic.com/avatar.jpeg", "image"))
        self.assertFalse(should_abort_media_request("https://sf1-cdn-tos.douyinstatic.com/font.woff2", "font"))
        self.assertFalse(should_abort_media_request("https://live.douyin.com/webcast/im/push/v2/", "websocket"))
        self.assertFalse(should_abort_media_request("https://sf1-cdn-tos.douyinstatic.com/lib.js", "script"))
        self.assertFalse(should_abort_media_request("https://live.douyin.com/123456", "document"))

    def test_danmu_login_and_reply_interfaces(self):
        from danma.main import DanmuBrowserCollector
        from screen import danmu as danmu_screen
        from core import state

        collector = DanmuBrowserCollector(platform="douyin", url="https://live.douyin.com/123456")

        # 1. 页面未就绪时的状态测试
        collector.page = None
        self.assertFalse(collector.check_login_status()["logged_in"])
        self.assertFalse(collector.trigger_login()["success"])
        self.assertFalse(collector.send_danmu_reply("测试")["success"])

        # 2. 模拟页面已就绪
        mock_page = mock.MagicMock()
        mock_page.is_closed.return_value = False
        mock_context = mock.MagicMock()
        mock_context.cookies.return_value = [
            {"name": "sessionid", "value": "test_session_123"},
            {"name": "passport_csrf_token", "value": "test_token"},
        ]
        mock_browser = mock.MagicMock()
        mock_browser.contexts = [mock_context]
        collector.browser = mock_browser
        collector.page = mock_page

        # 测试登录状态检查（基于 Cookie）
        status = collector.check_login_status()
        self.assertTrue(status["logged_in"])
        self.assertIn("sessionid", status["message"])

        # 测试触发登录（已登录状态）
        trig = collector.trigger_login()
        self.assertTrue(trig["success"])
        self.assertTrue(trig["already_logged_in"])

        # 测试模拟 Locator 成功输入并按回车回复
        mock_locator = mock.MagicMock()
        mock_locator.is_visible.return_value = True
        mock_page.locator.return_value.first = mock_locator
        reply_res = collector.send_danmu_reply("欢迎各位老板进入直播间！")
        self.assertTrue(reply_res["success"])
        mock_locator.click.assert_called()
        mock_locator.fill.assert_called_with("欢迎各位老板进入直播间！")
        mock_locator.press.assert_called_with("Enter")

        # 3. 测试 is_login_modal_open 与 screen/danmu 模块级桥接接口
        state.danmu_collector = collector
        try:
            mock_page.evaluate.return_value = True
            self.assertTrue(collector.is_login_modal_open())
            self.assertTrue(danmu_screen.is_login_modal_open())
            self.assertTrue(danmu_screen.check_login_status()["logged_in"])
            self.assertTrue(danmu_screen.trigger_login()["success"])
            self.assertTrue(danmu_screen.send_danmu_reply("666")["success"])
        finally:
            state.danmu_collector = None


if __name__ == "__main__":
    unittest.main()



