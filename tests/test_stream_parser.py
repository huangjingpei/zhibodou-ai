"""StreamGet 多平台直播流解析单元测试。"""
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath("src"))

from broadcast.stream_parser import (
    QUALITY_NAMES,
    async_parse_stream,
    detect_platform,
    parse_stream,
)


class TestStreamParser(unittest.TestCase):
    """测试多平台 URL 识别与 StreamGet 解析逻辑。"""

    def test_detect_platform_major_sites(self):
        """验证主流平台域名自动识别。"""
        cases = [
            ("https://live.douyin.com/123456", "抖音直播"),
            ("https://v.douyin.com/iABCDEF/", "抖音直播"),
            ("https://live.kuaishou.com/u/kwai123", "快手直播"),
            ("https://v.kuaishou.com/shortUrl", "快手直播"),
            ("https://live.bilibili.com/26066074", "哔哩哔哩"),
            ("https://b23.tv/liveBili", "哔哩哔哩"),
            ("https://www.huya.com/991111", "虎牙直播"),
            ("https://www.douyu.com/99999", "斗鱼直播"),
            ("https://www.tiktok.com/@creator/live", "TikTok"),
            ("https://www.twitch.tv/shroud", "Twitch"),
            ("https://www.youtube.com/watch?v=liveid", "YouTube Live"),
            ("https://www.xiaohongshu.com/discovery/item/123", "小红书直播"),
        ]
        for url, expected_name in cases:
            with self.subTest(url=url):
                name, cls = detect_platform(url)
                self.assertEqual(name, expected_name)
                self.assertIsNotNone(cls)

    def test_detect_platform_unsupported(self):
        """未知或无效 URL 应返回 None。"""
        name, cls = detect_platform("https://unknown-live-site.example.com/live/1")
        self.assertIsNone(name)
        self.assertIsNone(cls)

        name, cls = detect_platform("")
        self.assertIsNone(name)
        self.assertIsNone(cls)

    def test_parse_empty_url(self):
        """空 URL 解析应安全返回失败字典。"""
        res = parse_stream("")
        self.assertFalse(res.get("success"))
        self.assertIn("请输入有效的直播间地址", res.get("message"))

    def test_parse_unknown_url(self):
        """不支持的 URL 解析应安全返回友好提示。"""
        res = parse_stream("https://example.com/test")
        self.assertFalse(res.get("success"))
        self.assertIn("未能识别该直播间所属平台", res.get("message"))

    @patch("broadcast.stream_parser.detect_platform")
    def test_async_parse_stream_success(self, mock_detect):
        """模拟成功解析直播间流地址。"""
        mock_handler = MagicMock()
        mock_handler.fetch_web_stream_data = AsyncMock(return_value={
            "anchor_name": "测试主播",
            "title": "测试直播间标题",
            "is_live": True,
        })
        mock_stream_obj = MagicMock()
        mock_stream_obj.flv_url = "http://stream.example.com/live.flv"
        mock_stream_obj.m3u8_url = "http://stream.example.com/live.m3u8"
        mock_handler.fetch_stream_url = AsyncMock(return_value=mock_stream_obj)

        mock_cls = MagicMock(return_value=mock_handler)
        mock_detect.return_value = ("测试平台", mock_cls)

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(async_parse_stream("https://live.test.com/123"))
        finally:
            loop.close()

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("platform"), "测试平台")
        self.assertEqual(res.get("anchor_name"), "测试主播")
        self.assertTrue(res.get("is_live"))
        self.assertIn("OD", res.get("streams", {}))
        self.assertEqual(res.get("streams")["OD"]["flv"], "http://stream.example.com/live.flv")
        self.assertEqual(res.get("streams")["OD"]["m3u8"], "http://stream.example.com/live.m3u8")
        self.assertIn("FLV", res.get("available_formats", []))
        self.assertIn("M3U8", res.get("available_formats", []))


if __name__ == "__main__":
    unittest.main()
