import os
import sys
import unittest
from unittest import mock

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from danma import hardware, llm_gateway


class HardwareDetectionTests(unittest.TestCase):
    def test_detect_gpu_tier_index_tts_on_large_vram(self):
        with mock.patch.object(hardware, "_query_nvidia_smi", return_value=(8192, "NVIDIA GeForce RTX 4060")):
            res = hardware.detect_gpu_tier()
            self.assertEqual(res["tier"], hardware.TIER_INDEX_TTS)
            self.assertIn("IndexTTS", res["display_name"])
            self.assertEqual(res["vram_mb"], 8192)

    def test_detect_gpu_tier_moss_tts_on_medium_vram(self):
        with mock.patch.object(hardware, "_query_nvidia_smi", return_value=(6144, "NVIDIA GeForce GTX 1660")):
            res = hardware.detect_gpu_tier()
            self.assertEqual(res["tier"], hardware.TIER_MOSS_TTS)
            self.assertIn("MOSS-TTS-Nano", res["display_name"])
            self.assertEqual(res["vram_mb"], 6144)

    def test_detect_gpu_tier_playwright_on_low_vram(self):
        with mock.patch.object(hardware, "_query_nvidia_smi", return_value=(2048, "NVIDIA Quadro P520")):
            res = hardware.detect_gpu_tier()
            self.assertEqual(res["tier"], hardware.TIER_PLAYWRIGHT)
            self.assertIn("Playwright", res["display_name"])
            self.assertEqual(res["vram_mb"], 2048)

    def test_detect_gpu_tier_fallback_to_wmi_when_smi_fails(self):
        with mock.patch.object(hardware, "_query_nvidia_smi", return_value=(0, "")), \
                mock.patch.object(hardware, "_query_wmi_vram", return_value=(4096, "AMD Radeon")):
            res = hardware.detect_gpu_tier()
            self.assertEqual(res["tier"], hardware.TIER_MOSS_TTS)
            self.assertEqual(res["gpu_name"], "AMD Radeon")
            self.assertEqual(res["vram_mb"], 4096)


class LLMGatewayTests(unittest.TestCase):
    def test_is_local_ollama_identification(self):
        self.assertTrue(llm_gateway.is_local_ollama("http://localhost:11434"))
        self.assertTrue(llm_gateway.is_local_ollama("http://127.0.0.1:11434/v1"))
        self.assertFalse(llm_gateway.is_local_ollama("https://api.deepseek.com"))

    def test_is_llm_configured(self):
        # 1. 均未配置
        ok, msg = llm_gateway.is_llm_configured({})
        self.assertFalse(ok)

        # 2. 配置了 API Key
        ok, msg = llm_gateway.is_llm_configured({"deepseek_api_key": "sk-123456"})
        self.assertTrue(ok)

        # 3. 未配 Key 但指定了本地 Ollama
        ok, msg = llm_gateway.is_llm_configured({"deepseek_api_base": "http://127.0.0.1:11434"})
        self.assertTrue(ok)

    def test_build_chat_endpoint(self):
        self.assertEqual(
            llm_gateway.build_chat_endpoint("https://api.deepseek.com"),
            "https://api.deepseek.com/v1/chat/completions"
        )
        self.assertEqual(
            llm_gateway.build_chat_endpoint("http://localhost:11434/v1"),
            "http://localhost:11434/v1/chat/completions"
        )

    def test_evaluate_and_reply_filters_likes_and_enters(self):
        res = llm_gateway.evaluate_and_reply({"type": "LikeMessage"}, {}, {})
        self.assertFalse(res["should_reply"])
        self.assertEqual(res["reason"], "like_or_enter")

    def test_evaluate_and_reply_filters_trivial_content(self):
        cfg = {"deepseek_api_key": "sk-test"}
        res = llm_gateway.evaluate_and_reply({"type": "ChatMessage", "content": "666"}, {}, cfg)
        self.assertFalse(res["should_reply"])
        self.assertEqual(res["reason"], "empty_or_trivial")

    def test_evaluate_and_reply_gift_acknowledgement(self):
        cfg = {"deepseek_api_key": "sk-test"}
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "感谢大哥送出的小心心，下方小黄车直接拍！"}}]
        }

        with mock.patch("requests.post", return_value=mock_resp):
            msg = {"type": "GiftMessage", "user": "王总", "giftName": "小心心", "giftCount": 5}
            ctx = {"product_name": "保温杯", "product_desc": "29.9包邮"}
            res = llm_gateway.evaluate_and_reply(msg, ctx, cfg)

        self.assertTrue(res["should_reply"])
        self.assertEqual(res["reply_type"], "gift")
        self.assertIn("感谢大哥送出的小心心", res["reply_text"])

    def test_evaluate_and_reply_question_decision_json(self):
        cfg = {"deepseek_api_key": "sk-test"}
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"should_reply": true, "reply_type": "question", "reply_text": "拍下48小时内顺丰发货，假一赔三！", "reason": "咨询发货时效"}'
                }
            }]
        }

        with mock.patch("requests.post", return_value=mock_resp):
            msg = {"type": "ChatMessage", "user": "小李", "content": "几天能发货啊？"}
            ctx = {"product_name": "保温杯", "product_desc": "顺丰48小时直发"}
            res = llm_gateway.evaluate_and_reply(msg, ctx, cfg)

        self.assertTrue(res["should_reply"])
        self.assertEqual(res["reply_type"], "question")
        self.assertIn("顺丰发货", res["reply_text"])


if __name__ == "__main__":
    unittest.main()
