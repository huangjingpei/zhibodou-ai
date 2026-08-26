import os
import sys
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from screen.scrcpy_embed import _is_virtual_audio_route  # noqa: E402


class ScrcpyAudioCompatibilityTests(unittest.TestCase):
    def test_microphone_route_can_use_legacy_phone_speaker(self):
        self.assertFalse(_is_virtual_audio_route("扬声器", "麦克风阵列"))

    def test_virtual_route_requires_scrcpy_audio_forwarding(self):
        self.assertTrue(_is_virtual_audio_route("CABLE Input", "CABLE Output"))
        self.assertTrue(_is_virtual_audio_route("VoiceMeeter Input", "VoiceMeeter Output"))


if __name__ == "__main__":
    unittest.main()
