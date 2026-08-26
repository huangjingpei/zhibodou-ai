import json
import os
import sys
import unittest
from unittest.mock import patch

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from device.input_text import _find_semantic_node, _send_via_agent  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class AgentProtocolTests(unittest.TestCase):
    @patch("device.input_text.urllib.request.urlopen")
    def test_android_code_zero_is_success_without_second_click(self, urlopen):
        urlopen.return_value = FakeResponse({"code": 0, "msg": "success"})
        self.assertTrue(_send_via_agent("测试", click_send=True))
        self.assertEqual(1, urlopen.call_count)
        self.assertIn("/inject_and_send?", urlopen.call_args.args[0])

    @patch("device.input_text.urllib.request.urlopen")
    def test_legacy_success_response_is_still_supported(self, urlopen):
        urlopen.return_value = FakeResponse({"success": True})
        self.assertTrue(_send_via_agent("测试", click_send=False))
        self.assertIn("/set_text?", urlopen.call_args.args[0])

    def test_semantic_locator_uses_doubao_resource_ids(self):
        xml = """<hierarchy>
          <node class="android.widget.EditText" resource-id="com.larus.nova:id/input_text"
                text="" content-desc="" bounds="[40,1900][880,2200]" />
          <node class="android.widget.ImageView" resource-id="com.larus.nova:id/action_send"
                text="" content-desc="发送" bounds="[900,2050][1060,2220]" />
        </hierarchy>"""
        self.assertTrue(_find_semantic_node(xml, "input")["resource-id"].endswith("/input_text"))
        self.assertTrue(_find_semantic_node(xml, "send")["resource-id"].endswith("/action_send"))

    def test_semantic_locator_does_not_guess_bottom_right_control(self):
        xml = """<hierarchy><node class="android.widget.ImageView" resource-id="photo_picker"
          clickable="true" bounds="[900,2000][1080,2240]" /></hierarchy>"""
        self.assertIsNone(_find_semantic_node(xml, "input"))
        self.assertIsNone(_find_semantic_node(xml, "send"))


if __name__ == "__main__":
    unittest.main()
