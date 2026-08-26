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
    VAD_START_TIMEOUT,
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
        self.active_silence_hold_sec = self.silence_hold_sec
        self.idle_floor_db = -100.0
        self._log = lambda _msg: None
        self._on_level = None
        self._stream = object()
        self._pa = None
        self._device_name = "CABLE Output"
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
    def test_weighted_db_uses_previous_five_eighths(self):
        value = AudioPlaybackMonitor._weighted_db(-50.0, -42.0)
        self.assertAlmostEqual(-47.0, value)

        value = AudioPlaybackMonitor._weighted_db(value, -42.0)
        self.assertAlmostEqual(-45.125, value)

    def test_waiting_silence_does_not_end_before_speech(self):
        levels = [-100.0] * 25 + [-20.0] * 35 + [-100.0] * 30
        mon = FakeMonitor(levels)
        result = mon.wait_for_doubao_speech_cycle(3.0)
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
        result = mon.wait_for_doubao_speech_cycle(2.0)
        self.assertEqual(VAD_ENDED, result)
        self.assertGreater(mon._now, 1.2)

    def test_packetized_speech_frames_can_enter_speaking(self):
        # 手机/虚拟声卡会在有效 PCM 块之间插入空帧；有效语音无需逐帧连续。
        packetized_speech = ([-18.0] * 2 + [-100.0] * 3) * 8
        mon = FakeMonitor(packetized_speech + [-100.0] * 30)
        result = mon.wait_for_doubao_speech_cycle(2.0)
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
        result = mon.wait_for_doubao_speech_cycle(2.0)
        self.assertEqual(VAD_ENDED, result)
        resumed = [args for args in emitted if abs(args[0] - (-43.9)) < 0.01]
        self.assertTrue(resumed)
        self.assertTrue(resumed[-1][2])

    def test_consecutive_capture_errors_stop_instead_of_counting_as_silence(self):
        mon = FakeMonitor([None] * 5)
        result = mon.wait_for_doubao_speech_cycle(2.0)
        self.assertEqual(VAD_AUDIO_ERROR, result)

    def test_cancelled_round_cannot_release_next_script(self):
        mon = FakeMonitor([-100.0] * 20)
        stop = threading.Event()
        stop.set()
        result = mon.wait_for_doubao_speech_cycle(2.0, stop_event=stop)
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

    def test_microphone_calibration_uses_relative_noise_floor(self):
        AudioPlaybackMonitor.reset_session_baseline()
        mon = FakeMonitor([-50.3] * 60)
        mon._device_name = "麦克风阵列 (Realtek(R) Audio)"
        self.assertTrue(mon.calibrate_idle(0.5))
        self.assertAlmostEqual(-47.3, mon.start_threshold_db)
        self.assertAlmostEqual(-49.8, mon.end_threshold_db)
        self.assertAlmostEqual(8.0, mon.active_silence_hold_sec)

    def test_realistic_microphone_level_can_complete_speech_cycle(self):
        mon = FakeMonitor([-45.5] * 30 + [-55.0] * 30)
        mon._device_name = "麦克风阵列 (Realtek(R) Audio)"
        mon.idle_floor_db = -50.3
        mon.start_threshold_db = -47.3
        mon.end_threshold_db = -49.8
        mon.active_silence_hold_sec = 8.0
        result = mon.wait_for_doubao_speech_cycle(2.0)
        self.assertEqual(VAD_ENDED, result)

    def test_microphone_noise_spikes_do_not_keep_round_alive_forever(self):
        # 进入说话态后恢复底噪；每两秒一次的单帧噪声不能重置 4 秒结束确认。
        quiet_with_spikes = [-55.0] * 260
        quiet_with_spikes[80] = -47.0
        quiet_with_spikes[180] = -47.0
        mon = FakeMonitor([-45.0] * 20 + quiet_with_spikes)
        mon._device_name = "麦克风阵列 (Realtek(R) Audio)"
        mon.idle_floor_db = -50.3
        mon.start_threshold_db = -47.3
        mon.end_threshold_db = -49.8
        mon.active_silence_hold_sec = 8.0
        result = mon.wait_for_doubao_speech_cycle(2.0)
        self.assertEqual(VAD_ENDED, result)
        self.assertLess(mon._now, 10.0)

    def test_microphone_rejects_contaminated_next_round_baseline(self):
        AudioPlaybackMonitor.reset_session_baseline()
        first = FakeMonitor([-50.3] * 60)
        first._device_name = "麦克风阵列"
        self.assertTrue(first.calibrate_idle(0.5))

        second = FakeMonitor([-47.5] * 400)
        second._device_name = "麦克风阵列"
        self.assertFalse(second.calibrate_idle(0.5, max_wait_sec=2.0))

    def test_start_timeout_is_an_unsafe_result(self):
        mon = FakeMonitor([-55.0] * 80)
        result = mon.wait_for_doubao_speech_cycle(0.5)
        self.assertEqual(VAD_START_TIMEOUT, result)

    def test_speech_duration_has_no_fixed_limit(self):
        # 模拟超过旧 45 秒上限的连续语音，必须等真正静音后才结束。
        mon = FakeMonitor([-20.0] * 2500 + [-100.0] * 30)
        result = mon.wait_for_doubao_speech_cycle(1.0)
        self.assertEqual(VAD_ENDED, result)
        self.assertGreater(mon._now, 50.0)


if __name__ == "__main__":
    unittest.main()
