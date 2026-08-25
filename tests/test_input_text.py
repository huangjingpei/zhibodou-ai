import json
import os
import sys
import unittest
from unittest.mock import patch

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from device.input_text import _send_via_agent  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
