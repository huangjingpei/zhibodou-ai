import os
import queue
import sys
import unittest
from unittest.mock import patch

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core import state  # noqa: E402
from screen import danmu  # noqa: E402


class FakeLabel:
    def __init__(self):
        self.text = ""

    def config(self, **kwargs):
        self.text = kwargs.get("text", self.text)


class FakeText:
    def __init__(self):
        self.value = ""

    def insert(self, _where, text):
        self.value += text

    def see(self, _where):
        return None


class FakeValue:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class DanmuBridgeTests(unittest.TestCase):
    def setUp(self):
        state.online_num = 0
        state.like_cnt = 0
        state.gift_cnt = 0
        state.comment_cnt = 0
        state.last_danmu_text = ""
        self.online = FakeLabel()
        self.like = FakeLabel()
        self.gift = FakeLabel()
        self.text = FakeText()
        self.patchers = [
            patch.object(danmu.ui, "lab_online", self.online),
            patch.object(danmu.ui, "lab_like", self.like),
            patch.object(danmu.ui, "lab_gift", self.gift),
            patch.object(danmu.ui, "txt_danmu", self.text),
        ]
        for item in self.patchers:
            item.start()

    def tearDown(self):
        for item in reversed(self.patchers):
            item.stop()

    def test_chat_message_updates_client_directly(self):
        danmu.process_message({"type": "ChatMessage", "name": "小明", "content": "怎么买"})
        self.assertEqual(1, state.comment_cnt)
        self.assertEqual("怎么买", state.last_danmu_text)
        self.assertIn("小明：怎么买", self.text.value)

    def test_room_like_and_gift_counters(self):
        danmu.process_message({"type": "RoomMessage", "count": "88"})
        danmu.process_message({"type": "LikeMessage", "name": "A", "count": "3"})
        danmu.process_message({
            "type": "GiftMessage", "name": "B", "gift_name": "玫瑰", "gift_count": "2"
        })
        self.assertEqual(88, state.online_num)
        self.assertEqual(3, state.like_cnt)
        self.assertEqual(2, state.gift_cnt)
        self.assertIn("在线：88", self.online.text)
        self.assertIn("点赞：3", self.like.text)
        self.assertIn("礼物：2", self.gift.text)
        self.assertIn("玫瑰 × 2", self.text.value)

    def test_full_queue_drops_oldest_message(self):
        old_queue = state.danmu_queue
        try:
            state.danmu_queue = queue.Queue(maxsize=2)
            danmu.enqueue_messages([
                {"type": "ChatMessage", "content": "1"},
                {"type": "ChatMessage", "content": "2"},
                {"type": "ChatMessage", "content": "3"},
            ])
            contents = [state.danmu_queue.get_nowait()["content"] for _ in range(2)]
            self.assertEqual(["2", "3"], contents)
        finally:
            state.danmu_queue = old_queue

    def test_ui_platform_url_and_headless_override_saved_config(self):
        with (
            patch.object(danmu.ui, "cmb_danmu_platform", FakeValue("bili")),
            patch.object(danmu.ui, "ent_danmu_url", FakeValue("https://live.bilibili.com/123")),
            patch.object(danmu.ui, "var_danmu_headless", FakeValue(False)),
        ):
            options = danmu._read_options()
        self.assertEqual("bili", options["platform"])
        self.assertEqual("https://live.bilibili.com/123", options["url"])
        self.assertFalse(options["headless"])


if __name__ == "__main__":
    unittest.main()
