import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from screen.scrcpy_embed import _is_virtual_audio_route, open_app_volume_settings, start_scrcpy_embed


class ScrcpyAudioCompatibilityTests(unittest.TestCase):
    def test_microphone_route_can_use_legacy_phone_speaker(self):
        self.assertFalse(_is_virtual_audio_route("扬声器", "麦克风阵列"))

    def test_virtual_route_requires_scrcpy_audio_forwarding(self):
        self.assertTrue(_is_virtual_audio_route("CABLE Input", "CABLE Output"))
        self.assertTrue(_is_virtual_audio_route("VoiceMeeter Input", "VoiceMeeter Output"))

    def test_open_app_volume_settings(self):
        with patch("os.startfile", create=True) as mock_startfile:
            open_app_volume_settings()
            mock_startfile.assert_called_once_with("ms-settings:apps-volume")

    @patch("screen.scrcpy_embed.subprocess.Popen")
    @patch("screen.scrcpy_embed.os.path.exists", return_value=True)
    @patch("screen.scrcpy_embed._get_android_sdk", return_value=33)
    def test_scrcpy_runs_without_changing_windows_default_playback_device(self, mock_sdk, mock_exists, mock_popen):
        proc = MagicMock()
        proc.poll.return_value = None
        mock_popen.return_value = proc

        fake_pa = MagicMock()
        fake_pa.get_default_output_device_info.return_value = {"name": "Realtek High Definition Audio (Speakers)"}
        fake_pa.get_device_count.return_value = 2
        fake_pa.get_device_info_by_index.side_effect = [
            {"name": "Realtek High Definition Audio (Speakers)", "maxOutputChannels": 2},
            {"name": "CABLE Input (VB-Audio Virtual Cable)", "maxOutputChannels": 2},
        ]

        with patch("pyaudio.PyAudio", return_value=fake_pa), \
             patch("gui.ui.log_screen") as mock_log, \
             patch("tkinter.messagebox.showerror") as mock_err:
            ok = start_scrcpy_embed()
            self.assertTrue(ok)
            mock_err.assert_not_called()
            # Verify it proceeded to start scrcpy subprocess
            mock_popen.assert_called()


if __name__ == "__main__":
    unittest.main()
