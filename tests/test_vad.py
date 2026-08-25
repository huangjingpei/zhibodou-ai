import os
import sys
import threading
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from audio.vad import (  # noqa: E402
    AudioPlaybackMonitor,
    VAD_AUDIO_ERROR,
    VAD_CANCELLED,
    VAD_ENDED,
)


class FakeMonitor(AudioPlaybackMonitor):
    """不初始化声卡，用确定性时钟驱动状态机。"""

    def __init__(self, levels, step=0.02):
        self.energy_threshold_db = -42.0
        self.silence_hold_sec = 0.4
        self.speak_confirm_sec = 0.2
        self.noise_margin_db = 6.0
        self.end_hysteresis_db = 3.0
        self.start_threshold_db = -42.0
        self.end_threshold_db = -45.0
        self.idle_floor_db = -100.0
        self._log = lambda _msg: None
        self._on_level = None
        self._stream = object()
        self._pa = None
        self._sample_rate = 48000
        self._frames_per_buffer = 960
        self._levels = list(levels)
        self._last = self._levels[-1] if self._levels else -100.0
        self._now = 0.0
        self._step = step
        self._clock = lambda: self._now
        self.closed = False

    def _read_rms_db(self):
        self._now += self._step
        if self._levels:
            value = self._levels.pop(0)
            if value is None:
                return -100.0, False
            self._last = value
        return self._last, True

    def close(self):
        self.closed = True


class VadStateMachineTests(unittest.TestCase):
    def test_waiting_silence_does_not_end_before_speech(self):
        levels = [-100.0] * 25 + [-20.0] * 35 + [-100.0] * 30
        mon = FakeMonitor(levels)
        result = mon.wait_for_doubao_speech_cycle(3.0, 5.0)
        self.assertEqual(VAD_ENDED, result)
        self.assertGreaterEqual(mon._now, 1.2)
        self.assertTrue(mon.closed)

    def test_short_pause_does_not_end_speech(self):
        levels = (
            [-20.0] * 20
            + [-100.0] * 10  # 0.2s，短于 0.4s 静音确认
            + [-20.0] * 20
            + [-100.0] * 30
        )
        mon = FakeMonitor(levels)
        result = mon.wait_for_doubao_speech_cycle(2.0, 5.0)
        self.assertEqual(VAD_ENDED, result)
        self.assertGreater(mon._now, 1.2)

    def test_packetized_speech_frames_can_enter_speaking(self):
        # 手机/虚拟声卡会在有效 PCM 块之间插入空帧；有效语音无需逐帧连续。
        packetized_speech = ([-18.0] * 2 + [-100.0] * 3) * 8
        mon = FakeMonitor(packetized_speech + [-100.0] * 30)
        result = mon.wait_for_doubao_speech_cycle(2.0, 5.0)
        self.assertEqual(VAD_ENDED, result)

    def test_raw_voice_frame_cancels_pending_silence_before_average_recovers(self):
        levels = (
            [-20.0] * 10
            + [-100.0] * 20
            + [-43.9]  # 5 帧平滑约 -50.9dB，但原始帧已经高于结束阈值
            + [-20.0] * 8
            + [-100.0] * 30
        )
        emitted = []
        mon = FakeMonitor(levels)
        mon._on_level = lambda *args: emitted.append(args)
        result = mon.wait_for_doubao_speech_cycle(2.0, 5.0)
        self.assertEqual(VAD_ENDED, result)
        resumed = [args for args in emitted if abs(args[0] - (-43.9)) < 0.01]
        self.assertTrue(resumed)
        self.assertTrue(resumed[-1][2])

    def test_consecutive_capture_errors_stop_instead_of_counting_as_silence(self):
        mon = FakeMonitor([None] * 5)
        result = mon.wait_for_doubao_speech_cycle(2.0, 5.0)
        self.assertEqual(VAD_AUDIO_ERROR, result)

    def test_cancelled_round_cannot_release_next_script(self):
        mon = FakeMonitor([-100.0] * 20)
        stop = threading.Event()
        stop.set()
        result = mon.wait_for_doubao_speech_cycle(2.0, 5.0, stop_event=stop)
        self.assertEqual(VAD_CANCELLED, result)

    def test_calibration_uses_noise_floor_but_keeps_configured_minimum(self):
        mon = FakeMonitor([-60.0] * 60)
        emitted = []
        mon._on_level = lambda *args: emitted.append(args)
        self.assertTrue(mon.calibrate_idle(0.5))
        self.assertAlmostEqual(-60.0, mon.idle_floor_db)
        self.assertAlmostEqual(-42.0, mon.start_threshold_db)
        self.assertAlmostEqual(-45.0, mon.end_threshold_db)
        self.assertTrue(emitted)
        self.assertEqual("calibrating", emitted[-1][-1])

    def test_calibration_waits_for_existing_audio_to_stop(self):
        mon = FakeMonitor([-15.0] * 25 + [-60.0] * 40)
        self.assertTrue(mon.calibrate_idle(0.4, max_wait_sec=2.0))
        self.assertGreater(mon._now, 0.4)
        self.assertAlmostEqual(-60.0, mon.idle_floor_db)


if __name__ == "__main__":
    unittest.main()
