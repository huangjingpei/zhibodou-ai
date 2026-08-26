import os
import sys
import unittest
from unittest import mock

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from audio.vad import VAD_ENDED, VAD_START_TIMEOUT  # noqa: E402
from broadcast import live  # noqa: E402


class ResultMonitor:
    def __init__(self, result):
        self.result = result

    def wait_for_doubao_speech_cycle(self, **_kwargs):
        return self.result

    def close(self):
        pass


class LiveVadSafetyTests(unittest.TestCase):
    def setUp(self):
        live._live_generation = 0
        live._current_monitor = None
        live.can_next_speak = False

    @staticmethod
    def _cfg():
        return {"wait_start": 15.0, "silence_hold": 2.0}

    def test_start_timeout_stops_instead_of_releasing_next_script(self):
        with mock.patch.object(live.ui, "log_screen"), \
                mock.patch.object(live.ui, "reset_volume_meter"), \
                mock.patch.object(live, "_halt_live_from_worker") as halt:
            live.wait_next_round_worker(
                ResultMonitor(VAD_START_TIMEOUT), 0, None, self._cfg()
            )
        halt.assert_called_once()
        self.assertFalse(live.can_next_speak)

    def test_every_doubao_prompt_is_constrained_to_host_speech(self):
        with mock.patch.object(
            live.config,
            "load_config",
            return_value={"doubao_host_prompt": "只输出主播口播，不要对话。"},
        ):
            prompt = live.build_doubao_host_prompt("介绍这款日用品")
        self.assertIn("只输出主播口播，不要对话。", prompt)
        self.assertIn("本次直播话术要求：介绍这款日用品", prompt)

    def test_only_confirmed_end_releases_next_script(self):
        with mock.patch.object(live.ui, "log_screen"), \
                mock.patch.object(live.ui, "reset_volume_meter"):
            live.wait_next_round_worker(ResultMonitor(VAD_ENDED), 0, None, self._cfg())
        self.assertTrue(live.can_next_speak)

if __name__ == "__main__":
    unittest.main()
