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

from audio.obs_bridge import OBSAudioBridge
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

        e2 = create_tts_engine("index_tts")
        self.assertFalse(e2.is_text_only())


if __name__ == "__main__":
    unittest.main()
