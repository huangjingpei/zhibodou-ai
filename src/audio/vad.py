"""客户端音频 VAD。

必须先打开/校准音频，再向豆包发送话术。发送后持续经历
WAITING_SPEECH -> SPEAKING -> ENDED，只有 SPEAKING 后的连续静音才放行下一句。
"""
from __future__ import annotations

import array
import math
import os
import sys
import threading
import time
from collections import deque
from typing import Callable, Optional, Tuple

VAD_ENDED = "ended"
VAD_START_TIMEOUT = "start_timeout"
VAD_SPEECH_TIMEOUT = "speech_timeout"
VAD_CANCELLED = "cancelled"
VAD_UNAVAILABLE = "unavailable"
VAD_AUDIO_ERROR = "audio_error"


class AudioPlaybackMonitor:
    """捕获 scrcpy 转发到电脑的音频并判断豆包语音是否结束。"""

    _LOOPBACK_KEYWORDS = (
        "stereo mix", "wave out", "what u hear", "监听", "loopback",
        "mixing", "立体声混音", "cable output", "voicemeeter output",
    )

    def __init__(
        self,
        energy_threshold_db: float = -42.0,
        silence_hold_sec: float = 2.0,
        log_fn: Callable[[str], None] = print,
        on_level=None,
        speak_confirm_sec: float = 0.3,
        noise_margin_db: float = 6.0,
        end_hysteresis_db: float = 3.0,
    ):
        self.energy_threshold_db = float(energy_threshold_db)
        self.silence_hold_sec = max(0.2, float(silence_hold_sec))
        self.speak_confirm_sec = max(0.05, float(speak_confirm_sec))
        self.noise_margin_db = max(3.0, float(noise_margin_db))
        self.end_hysteresis_db = max(1.0, float(end_hysteresis_db))
        self.start_threshold_db = self.energy_threshold_db
        self.end_threshold_db = self.energy_threshold_db - self.end_hysteresis_db
        self.idle_floor_db = -100.0
        self._log = log_fn
        self._on_level = on_level
        self._pa = None
        self._stream = None
        self._device_index = None
        self._device_name = "(未初始化)"
        self._host_api_name = "?"
        self._sample_rate = 0
        self._frames_per_buffer = 1024
        self._close_lock = threading.Lock()
        self._clock = time.monotonic
        self._init_local_audio()

    @staticmethod
    def _load_config():
        try:
            src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from settings import config
            return config.load_config()
        except Exception:
            return {}

    def _host_name(self, info) -> str:
        try:
            api = self._pa.get_host_api_info_by_index(int(info.get("hostApi", -1)))
            return str(api.get("name") or "?")
        except Exception:
            return "?"

    def _device_rank(self, info, default_index) -> tuple:
        """同名设备优先 WASAPI，避免按名称长度碰运气。"""
        host = self._host_name(info).lower()
        index = int(info.get("index", 10**9))
        if "wasapi" in host:
            api_rank = 0
        elif index == default_index:
            api_rank = 1
        elif "directsound" in host:
            api_rank = 2
        elif "mme" in host:
            api_rank = 3
        else:
            api_rank = 4
        return api_rank, -len(str(info.get("name") or "")), index

    def _init_local_audio(self):
        try:
            import pyaudio
            self._pa = pyaudio.PyAudio()
            self._log("[Client-VAD] 正在枚举音频输入设备...")
            override = str(self._load_config().get("vad_input_device") or "").strip()
            try:
                default_index = int(self._pa.get_default_input_device_info()["index"])
            except Exception:
                default_index = None

            inputs = []
            for i in range(self._pa.get_device_count()):
                try:
                    info = dict(self._pa.get_device_info_by_index(i))
                except Exception:
                    continue
                if int(info.get("maxInputChannels", 0) or 0) > 0:
                    info["index"] = i
                    inputs.append(info)

            exact = []
            named = []
            loopbacks = []
            if override.isdigit():
                exact = [d for d in inputs if int(d["index"]) == int(override)]
            elif override:
                named = [d for d in inputs if override.lower() in str(d.get("name") or "").lower()]
            for info in inputs:
                name = str(info.get("name") or "").lower()
                if any(k in name for k in self._LOOPBACK_KEYWORDS):
                    loopbacks.append(info)

            if exact:
                preferred = exact
            elif named:
                preferred = sorted(named, key=lambda d: self._device_rank(d, default_index))
            elif loopbacks:
                preferred = sorted(loopbacks, key=lambda d: self._device_rank(d, default_index))
            else:
                preferred = sorted(inputs, key=lambda d: self._device_rank(d, default_index))

            ordered = []
            seen = set()
            for info in preferred + sorted(inputs, key=lambda d: self._device_rank(d, default_index)):
                if info["index"] not in seen:
                    ordered.append(info)
                    seen.add(info["index"])

            errors = []
            for info in ordered:
                index = int(info["index"])
                rate = int(info.get("defaultSampleRate", 48000) or 48000)
                frames = max(256, int(rate * 0.02))
                try:
                    stream = self._pa.open(
                        format=pyaudio.paInt16, channels=1, rate=rate, input=True,
                        input_device_index=index, frames_per_buffer=frames,
                    )
                except Exception as exc:
                    errors.append("%s=%s" % (index, exc))
                    continue
                self._stream = stream
                self._device_index = index
                self._device_name = str(info.get("name") or "?")
                self._host_api_name = self._host_name(info)
                self._sample_rate = rate
                self._frames_per_buffer = frames
                break

            if not self._stream:
                self._log("[Client-VAD] ❌ 没有可打开的音频输入设备：%s" % "; ".join(errors[-4:]))
                self.close()
                return
            self._log(
                "[Client-VAD] ✅ 输入设备 idx=%d｜%s｜Host=%s｜%dHz｜帧≈20ms"
                % (self._device_index, self._device_name, self._host_api_name, self._sample_rate)
            )
            if len(named) > 1:
                detail = "、".join(
                    "%d=%s(%s)" % (d["index"], d.get("name"), self._host_name(d))
                    for d in sorted(named, key=lambda d: self._device_rank(d, default_index))
                )
                self._log("[Client-VAD] 同名候选：%s；已按 WASAPI/默认端点优先级选择。" % detail)
        except Exception as exc:
            self._log("[Client-VAD] ❌ 音频初始化失败：%s" % exc)
            self.close()

    @property
    def is_ready(self) -> bool:
        return self._stream is not None

    def _read_rms_db(self) -> Tuple[float, bool]:
        stream = self._stream
        if stream is None:
            return -100.0, False
        try:
            data = stream.read(self._frames_per_buffer, exception_on_overflow=False)
            samples = array.array("h", data)
            if not samples:
                return -100.0, False
            rms = math.sqrt(sum(s * s for s in samples) / len(samples))
            if rms <= 0:
                return -100.0, True
            return 20.0 * math.log10(rms / 32768.0), True
        except Exception:
            return -100.0, False

    def get_current_rms_db(self) -> float:
        """兼容诊断调用；状态机内部会额外检查读取是否成功。"""
        return self._read_rms_db()[0]

    @staticmethod
    def _percentile(values, ratio: float) -> float:
        if not values:
            return -100.0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * ratio)))
        return ordered[index]

    @staticmethod
    def _average_db(levels) -> float:
        """在线性能量域平均，避免直接对 dB 做算术平均。"""
        if not levels:
            return -100.0
        power = sum(10.0 ** (db / 10.0) for db in levels) / len(levels)
        return -100.0 if power <= 1e-10 else 10.0 * math.log10(power)

    def calibrate_idle(
        self,
        sec: float = 0.8,
        stop_event: Optional[threading.Event] = None,
        max_wait_sec: float = 6.0,
    ) -> bool:
        """在发送前等待一个完整静音窗口并测量底噪。"""
        if not self._stream:
            return False
        window_sec = max(0.3, float(sec))
        deadline = self._clock() + max(window_sec, float(max_wait_sec))
        failures = 0
        while self._clock() < deadline:
            levels = []
            window_end = self._clock() + window_sec
            while self._clock() < window_end:
                if stop_event and stop_event.is_set():
                    return False
                db, ok = self._read_rms_db()
                if ok:
                    levels.append(db)
                    failures = 0
                    self._emit_level(
                        db,
                        self._average_db(levels[-5:]),
                        False,
                        None,
                        phase="calibrating",
                    )
                else:
                    failures += 1
                    if failures >= 5:
                        self._log("[Client-VAD] ❌ 校准时连续读取音频失败。")
                        return False
            if not levels:
                continue
            self.idle_floor_db = self._percentile(levels, 0.9)
            self.start_threshold_db = max(
                self.energy_threshold_db, self.idle_floor_db + self.noise_margin_db
            )
            self.end_threshold_db = self.start_threshold_db - self.end_hysteresis_db
            if self.idle_floor_db <= -25.0 and self.start_threshold_db <= -12.0:
                self._log(
                    "[Client-VAD] 校准完成：底噪=%.1fdB｜开口阈值=%.1fdB｜结束阈值=%.1fdB"
                    % (self.idle_floor_db, self.start_threshold_db, self.end_threshold_db)
                )
                return True
            if self._clock() < deadline:
                self._log(
                    "[Client-VAD] 当前仍有音频(%.1fdB)，等待豆包安静后再发送..."
                    % self.idle_floor_db
                )
        self._log(
            "[Client-VAD] ❌ %.1fs 内没有找到干净静音窗口（最后基线 %.1fdB）。"
            "请检查 CABLE/VoiceMeeter 回环或常驻音源。"
            % (max_wait_sec, self.idle_floor_db)
        )
        return False

    def close(self):
        with self._close_lock:
            stream, pa = self._stream, self._pa
            self._stream = None
            self._pa = None
            try:
                if stream:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass
            try:
                if pa:
                    pa.terminate()
            except Exception:
                pass

    def _emit_level(self, db, avg, speaking, silence_elapsed, phase="waiting"):
        if not self._on_level:
            return
        try:
            self._on_level(db, avg, speaking, silence_elapsed, self.silence_hold_sec, phase)
        except Exception:
            pass

    def wait_for_doubao_speech_cycle(
        self,
        max_wait_start_sec: float = 15.0,
        max_speech_timeout_sec: float = 45.0,
        stop_event: Optional[threading.Event] = None,
        close_on_finish: bool = True,
    ) -> str:
        """持续等待一次完整的“开口 -> 说话 -> 静音结束”周期。"""
        self._log(
            "[Client-VAD] 启动状态机：开口阈值=%.1fdB｜结束阈值=%.1fdB｜静音维持=%.1fs"
            % (self.start_threshold_db, self.end_threshold_db, self.silence_hold_sec)
        )
        try:
            if not self._stream:
                self._log("[Client-VAD] ❌ 没有音频流，停止自动轮播。")
                return VAD_UNAVAILABLE
            recent = deque(maxlen=5)
            consecutive_failures = 0
            last_log = 0.0
            sample_rate = float(self._sample_rate or 48000)
            frame_sec = max(0.005, self._frames_per_buffer / sample_rate)
            confirm_window_sec = max(1.0, self.speak_confirm_sec * 4.0)
            voice_window = deque(maxlen=max(10, int(confirm_window_sec / frame_sec)))
            # 手机/虚拟声卡的 PCM 常按块到达，块之间会出现 -100dB 空帧。
            # 在滚动窗口内累计有效语音，不能要求每一帧连续越阈值。
            required_voiced_sec = max(0.06, min(self.speak_confirm_sec, 0.15))
            wait_started = self._clock()
            self._log("[Client-VAD] 状态[WAITING]：等待豆包开口，思考期静音不会切句。")
            while self._clock() - wait_started < max_wait_start_sec:
                if stop_event and stop_event.is_set():
                    return VAD_CANCELLED
                db, ok = self._read_rms_db()
                if not ok:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        self._log("[Client-VAD] ❌ 连续读取音频失败，停止本轮。")
                        return VAD_AUDIO_ERROR
                    continue
                consecutive_failures = 0
                recent.append(db)
                avg = self._average_db(recent)
                now = self._clock()
                speaking_now = db > self.start_threshold_db or avg > self.start_threshold_db
                voice_window.append(speaking_now)
                self._emit_level(db, avg, speaking_now, None, phase="waiting")
                if now - last_log >= 0.75:
                    self._log("[Client-VAD] [WAITING] 当前=%.1f｜平滑=%.1fdB" % (db, avg))
                    last_log = now
                voiced_sec = sum(voice_window) * frame_sec
                if voiced_sec >= required_voiced_sec:
                    self._log(
                        "[Client-VAD] ✅ 状态[→SPEAKING]：%.1fs 窗口累计 %.2fs 有效语音。"
                        % (confirm_window_sec, voiced_sec)
                    )
                    break
            else:
                self._log(
                    "[Client-VAD] ⚠ %.1fs 内未检测到豆包开口，按无语音回答结束本轮。"
                    % max_wait_start_sec
                )
                return VAD_START_TIMEOUT

            speech_started = self._clock()
            silence_started = None
            recent.clear()
            last_log = 0.0
            self._log("[Client-VAD] 状态[SPEAKING]：持续监听，短停顿不会切句。")
            while self._clock() - speech_started < max_speech_timeout_sec:
                if stop_event and stop_event.is_set():
                    return VAD_CANCELLED
                db, ok = self._read_rms_db()
                if not ok:
                    consecutive_failures += 1
                    if consecutive_failures >= 5:
                        self._log("[Client-VAD] ❌ 语音期间音频流中断，停止本轮。")
                        return VAD_AUDIO_ERROR
                    continue
                consecutive_failures = 0
                recent.append(db)
                avg = self._average_db(recent)
                now = self._clock()
                # 分包音频恢复时，首个有效原始帧可能已越阈值，但 5 帧平滑值仍被
                # 前面的 -100dB 空帧拉低。两者任一越阈值都必须取消静音计时，
                # 否则会在豆包刚恢复出声的同一帧误判 ENDED。
                speaking_now = db > self.end_threshold_db or avg > self.end_threshold_db
                silence_elapsed = None if silence_started is None else now - silence_started
                self._emit_level(db, avg, speaking_now, silence_elapsed, phase="speaking")
                if now - last_log >= 0.75:
                    state = "说话中" if speaking_now else "静音计时"
                    self._log("[Client-VAD] [SPEAKING] %.1f/%.1fdB｜%s" % (db, avg, state))
                    last_log = now
                if speaking_now:
                    if silence_started is not None:
                        self._log("[Client-VAD] 静音被语音打断，继续监听。")
                    silence_started = None
                elif silence_started is None:
                    silence_started = now
                    self._log("[Client-VAD] 进入静音，开始 %.1fs 结束确认。" % self.silence_hold_sec)
                elif now - silence_started >= self.silence_hold_sec:
                    self._log(
                        "[Client-VAD] ✅ 状态[→ENDED]：连续静音 %.1fs，放行下一句。"
                        % (now - silence_started)
                    )
                    return VAD_ENDED
            self._log(
                "[Client-VAD] ⚠ 单句超过 %.1fs 硬上限，强制结束本轮。"
                % max_speech_timeout_sec
            )
            return VAD_SPEECH_TIMEOUT
        finally:
            if close_on_finish:
                self.close()

    @classmethod
    def quick_probe(cls, log_fn=print):
        list_audio_input_devices(log_fn)
        mon = cls(log_fn=log_fn)
        try:
            if mon.is_ready:
                log_fn(
                    "[Client-VAD] 自检就绪：idx=%s，%s (%s)"
                    % (mon._device_index, mon._device_name, mon._host_api_name)
                )
            else:
                log_fn("[Client-VAD] 自检失败：没有可用音频输入流。")
        finally:
            mon.close()


def list_audio_input_devices(log_fn=print):
    """列出 PortAudio 输入端点和 Host API，便于锁定 WASAPI 索引。"""
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
    except Exception as exc:
        log_fn("[Client-VAD] 无法枚举设备：%s" % exc)
        return []
    found = []
    try:
        try:
            default_index = int(pa.get_default_input_device_info()["index"])
        except Exception:
            default_index = None
        log_fn("[Client-VAD] 音频输入设备：")
        for i in range(pa.get_device_count()):
            try:
                info = pa.get_device_info_by_index(i)
                if int(info.get("maxInputChannels", 0) or 0) <= 0:
                    continue
                api = pa.get_host_api_info_by_index(int(info.get("hostApi", -1)))
                host = str(api.get("name") or "?")
                name = str(info.get("name") or "?")
                tags = []
                if i == default_index:
                    tags.append("默认")
                if "wasapi" in host.lower():
                    tags.append("推荐")
                tag = " [%s]" % "/".join(tags) if tags else ""
                log_fn("  [%d] %s｜%s｜%dHz%s" % (
                    i, name, host, int(info.get("defaultSampleRate", 0)), tag
                ))
                found.append({"index": i, "name": name, "host_api": host})
            except Exception:
                continue
    finally:
        pa.terminate()
    return found


def run_live_listen_test(duration_sec: float = 6.0, log_fn=print):
    mon = AudioPlaybackMonitor(log_fn=log_fn)
    try:
        if not mon.is_ready:
            return False
        log_fn("[Client-VAD] 先保持静音，校准 0.8 秒...")
        if not mon.calibrate_idle(0.8):
            return False
        log_fn("[Client-VAD] 请让豆包播放语音，监听 %.1f 秒..." % duration_sec)
        end = time.monotonic() + duration_sec
        peak = -100.0
        while time.monotonic() < end:
            db, ok = mon._read_rms_db()
            if not ok:
                log_fn("[Client-VAD] 读取失败")
                return False
            peak = max(peak, db)
            log_fn("  %.1fdB %s" % (db, "#" * max(0, int((db + 60) / 3))))
        ok = peak > mon.start_threshold_db
        log_fn("[Client-VAD] 峰值 %.1fdB，语音链路%s" % (peak, "正常 ✅" if ok else "未接通 ❌"))
        return ok
    finally:
        mon.close()


if __name__ == "__main__":
    list_audio_input_devices()
    run_live_listen_test()
