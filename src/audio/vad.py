"""客户端音频 VAD。

必须先打开/校准音频，再向豆包发送话术。发送后持续经历
WAITING_SPEECH -> SPEAKING -> ENDED，只有 SPEAKING 后的连续静音才放行下一句。
"""
from __future__ import annotations

import array
import ctypes
import math
import os
import sys
import threading
import time
from collections import deque
from typing import Callable, Optional, Tuple

VAD_ENDED = "ended"
VAD_START_TIMEOUT = "start_timeout"
VAD_CANCELLED = "cancelled"
VAD_UNAVAILABLE = "unavailable"
VAD_AUDIO_ERROR = "audio_error"


class _WindowsRenderPeakMeter:
    """读取 Windows 默认播放端点的真实峰值，作为 CABLE 的第二路证据。

    PyAudio/PortAudio 通过部分 VB-CABLE Host API 读取时会产生长空洞；Core
    Audio 的 IAudioMeterInformation 位于播放端点本身，不经过录音 Host API，
    因此能判断 scrcpy 是否仍在向 CABLE Input 输出声音。
    """

    _CLSID_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
    _IID_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
    _IID_DEVICE = "{D666063F-1587-4E43-81F1-B948E807363F}"
    _IID_METER = "{C02216F6-8C67-4B5B-9D00-D008E73E0064}"
    _CLSCTX_ALL = 23
    _interfaces = None

    def __init__(self, log_fn=print):
        self._log = log_fn
        self._thread_meters = {}
        self._lock = threading.Lock()
        self._logged_ready = False
        self._logged_failure = False

    @classmethod
    def _get_interfaces(cls):
        if cls._interfaces is not None:
            return cls._interfaces
        if os.name != "nt":
            cls._interfaces = False
            return False
        try:
            from ctypes import POINTER, c_float, c_int, c_uint32, c_void_p
            from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

            class AudioMeterInformation(IUnknown):
                _iid_ = GUID(cls._IID_METER)
                _methods_ = [
                    COMMETHOD([], HRESULT, "GetPeakValue",
                              (["out"], POINTER(c_float), "peak")),
                    COMMETHOD([], HRESULT, "GetMeteringChannelCount",
                              (["out"], POINTER(c_uint32), "count")),
                    COMMETHOD([], HRESULT, "GetChannelsPeakValues",
                              (["in"], c_uint32, "count"),
                              (["out"], POINTER(c_float), "peaks")),
                    COMMETHOD([], HRESULT, "QueryHardwareSupport",
                              (["out"], POINTER(c_uint32), "mask")),
                ]

            class AudioDevice(IUnknown):
                _iid_ = GUID(cls._IID_DEVICE)
                _methods_ = [
                    COMMETHOD([], HRESULT, "Activate",
                              (["in"], GUID, "iid"),
                              (["in"], c_int, "context"),
                              (["in"], c_void_p, "params"),
                              (["out"], POINTER(c_void_p), "interface")),
                ]

            class DeviceEnumerator(IUnknown):
                _iid_ = GUID(cls._IID_ENUMERATOR)
                _methods_ = [
                    COMMETHOD([], HRESULT, "EnumAudioEndpoints",
                              (["in"], c_int, "flow"),
                              (["in"], c_int, "state_mask"),
                              (["out"], POINTER(c_void_p), "devices")),
                    COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint",
                              (["in"], c_int, "flow"),
                              (["in"], c_int, "role"),
                              (["out"], POINTER(POINTER(AudioDevice)), "device")),
                ]

            cls._interfaces = (GUID, IUnknown, AudioMeterInformation, DeviceEnumerator)
        except Exception:
            cls._interfaces = False
        return cls._interfaces

    def _open_for_current_thread(self):
        interfaces = self._get_interfaces()
        if not interfaces:
            return None
        GUID, _IUnknown, Meter, Enumerator = interfaces
        thread_id = threading.get_ident()
        with self._lock:
            cached = self._thread_meters.get(thread_id)
            if cached:
                return cached[-1]
        try:
            ctypes.windll.ole32.CoInitialize(None)
            enumerator = ctypes.POINTER(Enumerator)()
            hr = ctypes.windll.ole32.CoCreateInstance(
                ctypes.byref(GUID(self._CLSID_ENUMERATOR)),
                None,
                self._CLSCTX_ALL,
                ctypes.byref(Enumerator._iid_),
                ctypes.byref(enumerator),
            )
            if hr < 0 or not enumerator:
                return None
            # eRender=0, eConsole=0；scrcpy 启动前也校验这一默认播放端点。
            device = enumerator.GetDefaultAudioEndpoint(0, 0)
            raw_meter = device.Activate(Meter._iid_, self._CLSCTX_ALL, None)
            meter = ctypes.cast(raw_meter, ctypes.POINTER(Meter))
            if not meter:
                return None
            with self._lock:
                # 保留枚举器和设备引用，确保 meter 生命周期覆盖整个监听线程。
                self._thread_meters[thread_id] = (enumerator, device, meter)
                if not self._logged_ready:
                    self._logged_ready = True
                    self._log("[Client-VAD] ✅ 已启用 Windows CABLE 播放端点峰值辅助检测。")
            return meter
        except Exception as exc:
            if not self._logged_failure:
                self._logged_failure = True
                self._log("[Client-VAD] ⚠ 系统播放端点峰值不可用，退回 PyAudio：%s" % exc)
            return None

    @staticmethod
    def _linear_peak_to_db(peak: float) -> float:
        peak = max(0.0, float(peak))
        return -100.0 if peak <= 1e-5 else 20.0 * math.log10(peak)

    def read_db(self) -> Optional[float]:
        meter = self._open_for_current_thread()
        if meter is None:
            return None
        try:
            return self._linear_peak_to_db(meter.GetPeakValue())
        except Exception:
            return None


class AudioPlaybackMonitor:
    """捕获 scrcpy 转发到电脑的音频并判断豆包语音是否结束。"""

    _LOOPBACK_KEYWORDS = (
        "stereo mix", "wave out", "what u hear", "监听", "loopback",
        "mixing", "立体声混音", "cable output", "voicemeeter output",
    )
    _trusted_mic_floor_db = None

    @classmethod
    def reset_session_baseline(cls):
        """每次正式开播重新建立可信麦克风静音基线。"""
        cls._trusted_mic_floor_db = None

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
        self.active_silence_hold_sec = self.silence_hold_sec
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
        self._render_meter = (
            _WindowsRenderPeakMeter(self._log)
            if self._stream and self._uses_digital_loopback()
            else None
        )

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
        """为同名端点选择稳定的 Host API。

        VB-CABLE/VoiceMeeter 在部分 Windows 驱动上通过 WASAPI 单声道读取会只
        返回空帧，而默认 MME 录音端点仍能收到有效 PCM。因此数字回环优先使用
        Windows 当前默认输入，其次 MME；实体麦克风仍优先低延迟 WASAPI。
        DirectSound 会在部分 VB-CABLE 版本中重复最后一个缓冲块，必须后置，
        否则真实播放结束后 VAD 会永远认为仍在说话。
        """
        host = self._host_name(info).lower()
        index = int(info.get("index", 10**9))
        name = str(info.get("name") or "").lower()
        digital = any(keyword in name for keyword in self._LOOPBACK_KEYWORDS)
        if digital and index == default_index:
            api_rank = 0
        elif digital and "mme" in host:
            api_rank = 1
        elif digital and "wasapi" in host:
            api_rank = 2
        elif digital and "directsound" in host:
            api_rank = 3
        elif "wasapi" in host:
            api_rank = 0
        elif index == default_index:
            api_rank = 1
        elif "mme" in host:
            api_rank = 2
        elif "directsound" in host:
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
                self._log(
                    "[Client-VAD] 同名候选：%s；已按数字回环稳定性/默认端点优先级选择。"
                    % detail
                )
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
        pcm_db = -100.0
        pcm_ok = False
        try:
            data = stream.read(self._frames_per_buffer, exception_on_overflow=False)
            samples = array.array("h", data)
            if samples:
                rms = math.sqrt(sum(s * s for s in samples) / len(samples))
                pcm_db = -100.0 if rms <= 0 else 20.0 * math.log10(rms / 32768.0)
                pcm_ok = True
        except Exception:
            pass
        render_meter = getattr(self, "_render_meter", None)
        render_db = render_meter.read_db() if render_meter else None
        if render_db is not None:
            return max(pcm_db, render_db), True
        return pcm_db, pcm_ok

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

    @staticmethod
    def _weighted_db(previous_db: Optional[float], current_db: float) -> float:
        """上一值占 5/8、最新值占 3/8 的指数平滑。"""
        if previous_db is None:
            return current_db
        return previous_db * (5.0 / 8.0) + current_db * (3.0 / 8.0)

    def _uses_digital_loopback(self) -> bool:
        """虚拟音频线可用固定阈值；实体麦克风必须按本机底噪自适应。"""
        name = str(self._device_name or "").lower()
        return any(keyword in name for keyword in self._LOOPBACK_KEYWORDS)

    def calibrate_idle(
        self,
        sec: float = 0.8,
        stop_event: Optional[threading.Event] = None,
        max_wait_sec: Optional[float] = 6.0,
    ) -> bool:
        """在发送前等待一个完整静音窗口并测量底噪。

        ``max_wait_sec=None`` 表示没有时间上限，只由音频真正静音或用户取消
        决定。这用于 CABLE 数字回环，避免上一段长话术尚未播完时因固定等待
        上限停止直播。
        """
        if not self._stream:
            return False
        window_sec = max(0.3, float(sec))
        deadline = (
            None
            if max_wait_sec is None
            else self._clock() + max(window_sec, float(max_wait_sec))
        )
        failures = 0
        waiting_logged_at = 0.0
        while deadline is None or self._clock() < deadline:
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
            candidate_floor_db = self._percentile(levels, 0.9)
            self.idle_floor_db = candidate_floor_db
            is_digital_loopback = self._uses_digital_loopback()
            trusted_floor_db = AudioPlaybackMonitor._trusted_mic_floor_db
            if (
                not is_digital_loopback
                and trusted_floor_db is not None
                and candidate_floor_db > trusted_floor_db + 1.5
            ):
                self._log(
                    "[Client-VAD] ⚠ 当前基线 %.1fdB 比本次直播静音基线 %.1fdB 高，"
                    "豆包可能仍在播放；继续等待，不发送下一句。"
                    % (candidate_floor_db, trusted_floor_db)
                )
                continue
            if is_digital_loopback:
                mode = "数字回环"
                # VB-CABLE 可能把连续声音拆成稀疏 PCM 块；2 秒窗口会在句中块间隙
                # 误判结束。数字回环至少确认 4 秒静音，但不限制语音总时长。
                self.active_silence_hold_sec = max(4.0, self.silence_hold_sec)
                self.start_threshold_db = max(
                    self.energy_threshold_db, self.idle_floor_db + self.noise_margin_db
                )
                self.end_threshold_db = self.start_threshold_db - self.end_hysteresis_db
            else:
                # 实体麦克风收到的是扬声器经过空气传播后的声音，电平通常比数字回环
                # 低很多。日志中的底噪约 -50dB、豆包语音约 -45dB，固定 -42dB
                # 会让整段语音都无法进入 SPEAKING。使用相对底噪阈值，并设置安全下限。
                mode = "麦克风自适应"
                mic_margin_db = max(2.5, min(4.0, self.noise_margin_db * 0.5))
                self.start_threshold_db = max(
                    -65.0,
                    min(self.energy_threshold_db, self.idle_floor_db + mic_margin_db),
                )
                # 结束检测要覆盖轻声段。以静音 P90 上方 0.5dB 为界，比原来的
                # start-1dB 更敏感；后续再用时间窗口过滤环境噪声尖峰。
                self.end_threshold_db = max(-65.0, self.idle_floor_db + 0.5)
                # 麦克风电平会随距离、声学回声消除和轻声段大幅波动。日志中连续
                # 2～3 秒低于阈值仍可能只是句内弱音，因此使用更保守的结束窗口。
                self.active_silence_hold_sec = max(8.0, self.silence_hold_sec)
            if self.idle_floor_db <= -25.0 and self.start_threshold_db <= -12.0:
                self._log(
                    "[Client-VAD] 校准完成：模式=%s｜底噪=%.1fdB｜开口阈值=%.1fdB｜"
                    "结束阈值=%.1fdB｜结束确认=%.1fs"
                    % (
                        mode,
                        self.idle_floor_db,
                        self.start_threshold_db,
                        self.end_threshold_db,
                        self.active_silence_hold_sec,
                    )
                )
                if not is_digital_loopback and trusted_floor_db is None:
                    AudioPlaybackMonitor._trusted_mic_floor_db = self.idle_floor_db
                return True
            if deadline is None or self._clock() < deadline:
                now = self._clock()
                if now - waiting_logged_at < 2.0:
                    continue
                waiting_logged_at = now
                self._log(
                    "[Client-VAD] 当前仍有音频(%.1fdB)，持续等待真正静音；"
                    "不会发送下一句，可点停止直播取消。" % self.idle_floor_db
                )
        if max_wait_sec is None:
            # 无限等待只可能由 stop_event 或读取错误提前返回，正常流程不会到这里。
            return False
        self._log(
            "[Client-VAD] ❌ %.1fs 内没有找到干净静音窗口（最后基线 %.1fdB）。"
            "请检查 CABLE/VoiceMeeter 回环或常驻音源。"
            % (float(max_wait_sec), self.idle_floor_db)
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
            self._on_level(
                db,
                avg,
                speaking,
                silence_elapsed,
                self.active_silence_hold_sec,
                phase,
            )
        except Exception:
            pass

    def wait_for_doubao_speech_cycle(
        self,
        max_wait_start_sec: float = 15.0,
        stop_event: Optional[threading.Event] = None,
        close_on_finish: bool = True,
    ) -> str:
        """持续等待“开口 -> 说话 -> 静音结束”，不限制豆包播放时长。"""
        self._log(
            "[Client-VAD] 启动状态机：开口阈值=%.1fdB｜结束阈值=%.1fdB｜静音维持=%.1fs"
            % (self.start_threshold_db, self.end_threshold_db, self.active_silence_hold_sec)
        )
        try:
            if not self._stream:
                self._log("[Client-VAD] ❌ 没有音频流，停止自动轮播。")
                return VAD_UNAVAILABLE
            weighted_db = None
            consecutive_failures = 0
            last_log = 0.0
            sample_rate = float(self._sample_rate or 48000)
            frame_sec = max(0.005, self._frames_per_buffer / sample_rate)
            digital_loopback = self._uses_digital_loopback()
            confirm_window_sec = (
                max(4.0, self.speak_confirm_sec * 8.0)
                if digital_loopback
                else max(1.0, self.speak_confirm_sec * 4.0)
            )
            voice_window = deque(maxlen=max(10, int(confirm_window_sec / frame_sec)))
            # 手机/虚拟声卡的 PCM 常按块到达，块之间会出现 -100dB 空帧。
            # 在滚动窗口内累计有效语音，不能要求每一帧连续越阈值。
            required_voiced_sec = (
                max(frame_sec * 2.0, 0.04)
                if digital_loopback
                else max(0.06, min(self.speak_confirm_sec, 0.15))
            )
            wait_started = self._clock()
            peak_db = -100.0
            voiced_frames_total = 0
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
                weighted_db = self._weighted_db(weighted_db, db)
                avg = weighted_db
                peak_db = max(peak_db, db, weighted_db)
                now = self._clock()
                speaking_now = db > self.start_threshold_db or avg > self.start_threshold_db
                if speaking_now:
                    voiced_frames_total += 1
                voice_window.append(speaking_now)
                self._emit_level(db, avg, speaking_now, None, phase="waiting")
                if now - last_log >= 0.75:
                    self._log("[Client-VAD] [WAITING] 当前=%.1f｜平滑=%.1fdB" % (db, avg))
                    last_log = now
                voiced_sec = sum(voice_window) * frame_sec
                strong_digital_frame = (
                    digital_loopback and db > self.start_threshold_db + 12.0
                )
                if strong_digital_frame or voiced_sec >= required_voiced_sec:
                    self._log(
                        "[Client-VAD] ✅ 状态[→SPEAKING]：%s；%.1fs 窗口累计 %.2fs 有效语音。"
                        % (
                            "捕获到强数字音频块" if strong_digital_frame else "语音累计确认",
                            confirm_window_sec,
                            voiced_sec,
                        )
                    )
                    break
            else:
                if peak_db > self.start_threshold_db:
                    self._log(
                        "[Client-VAD] ❌ 检测到越阈值音频（峰值 %.1fdB，共 %d 帧），"
                        "但有效持续时间不足；禁止切换下一句，请检查 CABLE 音频是否连续。"
                        % (peak_db, voiced_frames_total)
                    )
                elif peak_db > self.idle_floor_db + 2.0:
                    self._log(
                        "[Client-VAD] ❌ 仅检测到低电平信号（峰值 %.1fdB，开口阈值 %.1fdB）；"
                        "禁止切换下一句，请检查音频路由或阈值。"
                        % (peak_db, self.start_threshold_db)
                    )
                else:
                    self._log(
                        "[Client-VAD] ❌ %.1fs 内未检测到豆包开口（峰值 %.1fdB）；"
                        "禁止切换下一句，请检查采集设备。"
                        % (max_wait_start_sec, peak_db)
                    )
                return VAD_START_TIMEOUT

            speech_started = self._clock()
            silence_started = None
            weighted_db = None
            end_voice_window = deque(maxlen=max(10, int(1.2 / frame_sec)))
            last_log = 0.0
            self._log("[Client-VAD] 状态[SPEAKING]：持续监听，短停顿不会切句。")
            while True:
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
                weighted_db = self._weighted_db(weighted_db, db)
                avg = weighted_db
                now = self._clock()
                if digital_loopback:
                    # 数字回环的单个有效 PCM 块就是真实语音，必须立即取消静音计时。
                    frame_has_voice = db > self.end_threshold_db or avg > self.end_threshold_db
                    speaking_now = frame_has_voice
                else:
                    # 实体麦克风的轻声语音可能接近底噪。1.2 秒窗口累计达到
                    # 0.06 秒才算仍在说话。帧判定使用 5/8 + 3/8 加权值，
                    # 连续轻声会逐步越阈值，单个键盘/风扇尖峰不会立即重置计时。
                    frame_has_voice = avg > self.end_threshold_db
                    end_voice_window.append(frame_has_voice)
                    speaking_now = sum(end_voice_window) * frame_sec >= 0.06
                silence_elapsed = None if silence_started is None else now - silence_started
                self._emit_level(
                    db,
                    avg,
                    speaking_now,
                    silence_elapsed,
                    phase="speaking",
                )
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
                    self._log(
                        "[Client-VAD] 进入静音，开始 %.1fs 结束确认。"
                        % self.active_silence_hold_sec
                    )
                elif now - silence_started >= self.active_silence_hold_sec:
                    self._log(
                        "[Client-VAD] ✅ 状态[→ENDED]：连续静音 %.1fs，放行下一句。"
                        % (now - silence_started)
                    )
                    return VAD_ENDED
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
