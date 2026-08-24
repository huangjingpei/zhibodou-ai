# ==============================================================================
# src/audio/vad.py
# 纯电脑客户端本地音频 VAD 监听引擎 (毫秒级 PCM 能量检测，零 ADB 依赖)
#
# 设计约定（与产品流程一致）：
#   判断豆包有没有在说话 = 在【客户端】拿到豆包的声音流，做 VAD 检测。
#     - 有声音 → 豆包在说话 → 不打断；
#     - 静音持续超过 silence_hold_sec → 豆包说完了 → 继续下一个话术。
#
# 音频源说明（这是 VAD 能否生效的关键）：
#   豆包在手机上发声，客户端要"收到它的流"通常有两种可靠方式：
#     A. Windows 启用「立体声混音 / Stereo Mix / 监听」输入设备 —— 本机播放的
#        声音(含 scrcpy 转发的手机音频)会被当成输入流捕获，最干净；
#     B. 退而求其次用默认麦克风 —— 需让手机扬声器靠近电脑麦克风，受环境噪音影响。
#   本模块优先找 A 类回环/混音设备，找不到再退回 B(麦克风)，并在日志里明确提示。
# ==============================================================================
import time
import math
import array


class AudioPlaybackMonitor:
    """
    【本地客户端语音活动检测器 (VAD)】
    直接在电脑本地捕获音频输入流(回环混音/麦克风)，计算真实分贝值与语流状态，
    彻底抛弃 slow ADB dumpsys audio。
    """

    # 回环/混音类输入设备的关键字（命中即优先选用，可捕获本机播放的声音）
    _LOOPBACK_KEYWORDS = ("stereo mix", "wave out", "what u hear",
                          "监听", "loopback", "mixing", "立体声混音")

    def __init__(self, energy_threshold_db: float = -42.0,
                 silence_hold_sec: float = 1.0, log_fn=print):
        self.energy_threshold_db = energy_threshold_db   # 静音判定阈值 (dB)
        self.silence_hold_sec = silence_hold_sec         # 语毕静音维持时间 (秒)
        self._log = log_fn                                # 日志回调(可传 ui.log_screen)
        self._pa = None
        self._stream = None
        self._device_index = None
        self._device_name = "(未初始化)"
        self._init_local_audio()

    def _init_local_audio(self):
        """尝试初始化本地音频输入流。
        优先选用回环/混音设备(可捕获本机播放的豆包声音)，否则退回默认麦克风。"""
        try:
            import pyaudio
            self._pa = pyaudio.PyAudio()

            default_in = None
            loopback_idx = None
            for i in range(self._pa.get_device_count()):
                try:
                    info = self._pa.get_device_info_by_index(i)
                except Exception:
                    continue
                name = (info.get("name") or "").lower()
                max_in = int(info.get("maxInputChannels", 0) or 0)
                if max_in <= 0:
                    continue
                if default_in is None:
                    default_in = i
                if any(k in name for k in self._LOOPBACK_KEYWORDS):
                    loopback_idx = i

            if loopback_idx is not None:
                self._device_index = loopback_idx
            elif default_in is not None:
                self._device_index = default_in

            if self._device_index is not None:
                info = self._pa.get_device_info_by_index(self._device_index)
                self._device_name = info.get("name", "?")
                rate = int(info.get("defaultSampleRate", 16000) or 16000)
                self._stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    input=True,
                    input_device_index=self._device_index,
                    frames_per_buffer=1024,
                )
                self._log("[Client-VAD] 已打开音频输入设备[%s] idx=%s rate=%d"
                          % (self._device_name, self._device_index, rate))
                if loopback_idx is None:
                    self._log("[Client-VAD] ⚠ 未找到立体声混音/回环设备，当前用【麦克风】。"
                              "若豆包声音没被捕获：请在 Windows 声音设置里启用「立体声混音」，"
                              "或让手机扬声器靠近电脑麦克风；也可配合 scrcpy 音频转发使用回环捕获。")
            else:
                self._stream = None
                self._log("[Client-VAD] ⚠ 未找到任何音频输入设备，VAD 将旁路。")
        except Exception as e:
            self._stream = None
            self._pa = None
            self._log("[Client-VAD] ⚠ 初始化音频失败：%s（多半是没装 pyaudio，"
                      "请 pip install pyaudio 并确认麦克风/混音设备可用）" % e)

    def get_current_rms_db(self) -> float:
        """读取本地当前一帧音频的分贝能量值 (dBFS)。失败/无流返回 -100。"""
        if self._stream:
            try:
                data = self._stream.read(1024, exception_on_overflow=False)
                shorts = array.array('h', data)
                if not shorts:
                    return -100.0
                sum_squares = sum(s * s for s in shorts)
                rms = math.sqrt(sum_squares / len(shorts))
                if rms <= 0:
                    return -100.0
                return 20 * math.log10(rms / 32768.0)
            except Exception:
                return -100.0
        return -100.0

    def close(self):
        """释放声卡资源（每轮必须调用，否则设备会泄漏导致后续轮次 VAD 失效）。"""
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass
        finally:
            self._stream = None
            self._pa = None

    def wait_for_doubao_speech_cycle(self, max_wait_start_sec: float = 6.0,
                                     max_speech_timeout_sec: float = 60.0) -> bool:
        """
        【本地 VAD 完整生命周期检测】
        1. 监听本地音频流：等待豆包开始发声；
        2. 豆包说话中：持续锁定语流；
        3. 豆包说完：本地静音维持超过 silence_hold_sec 后立即切入下一轮。

        返回 True 表示「本轮已结束(可继续下一轮)」；False 表示「等待开口超时」。
        """
        self._log("[Client-VAD] 启动监听：阈值=%.1fdB 静音维持=%.1fs 设备=%s"
                  % (self.energy_threshold_db, self.silence_hold_sec, self._device_name))
        try:
            # 没打开到任何音频设备：VAD 无法工作，明确告警并旁路，避免"假生效"
            if not self._stream:
                self._log("[Client-VAD] ⚠ VAD 已旁路(无音频设备/未装pyaudio)："
                          "本轮仅固定等待 4s 后继续，不会真正检测豆包是否说完！")
                time.sleep(4.0)
                return True

            recent = []          # 近期 dB 滑动窗口(用于平滑，避免单帧抖动误判)
            last_log_t = 0.0

            # ---- 阶段 1：等待豆包开口 ----
            start_wait = time.time()
            speech_started = False
            self._log("[Client-VAD] 阶段1：等待豆包开口发声(最多 %.1fs)..." % max_wait_start_sec)
            while time.time() - start_wait < max_wait_start_sec:
                db = self.get_current_rms_db()
                recent.append(db)
                recent = recent[-8:]
                avg = sum(recent) / len(recent)
                now = time.time()
                if now - last_log_t >= 0.5:
                    self._log("[Client-VAD]   监听中 dB=%.1f 均值=%.1f 阈值=%.1f"
                              % (db, avg, self.energy_threshold_db))
                    last_log_t = now
                if avg > self.energy_threshold_db:
                    speech_started = True
                    self._log("[Client-VAD] ✅ 检测到语流开始(均值%.1f > 阈值%.1f)"
                              % (avg, self.energy_threshold_db))
                    break
                time.sleep(0.05)

            if not speech_started:
                self._log("[Client-VAD] ⚠ 等待开口超时：%.1fs 内没检测到声音。"
                          "可能豆包没出声，或音频源没捕获到它的声音(检查混音/麦克风)。"
                          % max_wait_start_sec)
                return False

            # ---- 阶段 2：语流维持 + 静音判定 ----
            speech_start_time = time.time()
            silence_start = None
            recent = []
            self._log("[Client-VAD] 阶段2：监听语流，等豆包说完...")
            while time.time() - speech_start_time < max_speech_timeout_sec:
                db = self.get_current_rms_db()
                recent.append(db)
                recent = recent[-8:]
                avg = sum(recent) / len(recent)
                now = time.time()
                if now - last_log_t >= 0.5:
                    state_txt = "说话中" if avg > self.energy_threshold_db else "静音"
                    self._log("[Client-VAD]   监听中 dB=%.1f 均值=%.1f 状态=%s"
                              % (db, avg, state_txt))
                    last_log_t = now

                if avg <= self.energy_threshold_db:
                    if silence_start is None:
                        silence_start = now
                        self._log("[Client-VAD] 进入静音，开始计时静音维持(%.1fs)"
                                  % self.silence_hold_sec)
                    elif now - silence_start >= self.silence_hold_sec:
                        dur = round(now - speech_start_time, 2)
                        self._log("[Client-VAD] ✅ 语流结束！本次播报时长 %.2fs，立即切入下一轮"
                                  % dur)
                        return True
                else:
                    if silence_start is not None:
                        self._log("[Client-VAD] 静音被打断，恢复语流，继续监听")
                    silence_start = None
                time.sleep(0.05)

            dur = round(time.time() - speech_start_time, 2)
            self._log("[Client-VAD] ⚠ 达到最大监听时长 %.1fs(本轮强制结束)，继续下一轮"
                      % max_speech_timeout_sec)
            return True
        finally:
            # 关键修复：每轮必须释放音频设备，否则几轮后设备被占满、VAD 静默失效
            self.close()
