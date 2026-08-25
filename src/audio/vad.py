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
                 silence_hold_sec: float = 1.0, log_fn=print, on_level=None,
                 speak_confirm_sec: float = 0.3):
        self.energy_threshold_db = energy_threshold_db   # 静音判定阈值 (dB)
        self.silence_hold_sec = silence_hold_sec         # 语毕静音维持时间 (秒)——即"静音超此值判播报结束"
        self.speak_confirm_sec = speak_confirm_sec       # 进入"说话"态需连续有语音确认时长(消抖，防单帧提示音/杂音误触发)
        self._log = log_fn                                # 日志回调(可传 ui.log_screen)
        self._on_level = on_level                         # 实时音量回调(可传 ui.set_volume_meter)
        self._pa = None
        self._stream = None
        self._device_index = None
        self._device_name = "(未初始化)"
        self._init_local_audio()

    def _init_local_audio(self):
        """尝试初始化本地音频输入流。
        优先选用回环/混音设备(可捕获本机播放的豆包声音)，否则退回默认麦克风。
        可在 config.vad_input_device 中指定设备名包含字或索引，指向虚拟音频线。"""
        try:
            import pyaudio
            self._pa = pyaudio.PyAudio()
            self._log("[Client-VAD] 引擎初始化：pyaudio 可用，正在枚举音频输入设备...")

            # 用户显式指定捕获设备（如虚拟音频线 "CABLE Output"）：优先按名/索引匹配
            dev_override = ""
            _cfg = None
            try:
                # 保证 `src` 在 sys.path，使 `from settings import config` 在
                # `python -m src.audio.vad` 与 `main.py` 两种启动方式下都能读到同一份配置
                import os as _os, sys as _sys
                _src_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                if _src_dir not in _sys.path:
                    _sys.path.insert(0, _src_dir)
                from settings import config as _cfg
            except Exception:
                _cfg = None
            if _cfg is not None:
                dev_override = (_cfg.load_config().get("vad_input_device") or "").strip()

            default_in = None
            loopback_idx = None
            named_idx = None
            named_matches = []   # 记录所有名字命中的设备，便于多虚拟线时提示精确索引
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
                # 显式指定：索引精确匹配 > 设备名包含字串(首个命中即停，避免多虚拟线歧义)
                if dev_override:
                    if dev_override.isdigit() and int(dev_override) == i:
                        named_idx = i
                    elif dev_override.lower() in name:
                        if named_idx is None:
                            named_idx = i
                        named_matches.append(i)

            # 选择优先级：显式指定 > 回环/混音 > 默认麦克风
            if named_idx is not None:
                self._device_index = named_idx
            elif loopback_idx is not None:
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
                self._log("[Client-VAD] ✅ 已旁听输入设备【%s】：豆包经 scrcpy→CABLE Input→"
                          "CABLE Output 的语音流将在此被检测（只读旁听，不改原始音频）"
                          % self._device_name)
                if named_idx is not None:
                    self._log("[Client-VAD] 使用显式指定设备(可配合虚拟音频线做纯数字分流，避免回环抢音频图)。")
                    if len(named_matches) > 1:
                        _detail = "、".join(
                            "%d=%r" % (mi, self._pa.get_device_info_by_index(mi).get("name"))
                            for mi in named_matches)
                        self._log("[Client-VAD] ⚠ 设备名「%s」命中了多个输入设备：%s；已取首个(%d)。"
                                  "注：idx=36 是「VB-Audio Point」(配对不同，勿用)；若 VAD 听不到豆包，"
                                  "请把 vad_input_device 改成精确索引(如 \"9\" 或 \"21\"，均为标准 Virtual Cable)以锁定。"
                                  "（部分设备名被 Windows 截断，以索引为准）"
                                  % (dev_override, _detail, named_matches[0]))
                elif loopback_idx is None:
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

    @classmethod
    def quick_probe(cls, log_fn=print):
        """开机自检用：枚举所有输入设备 + 打印将选用的设备，用完即释放。"""
        list_audio_input_devices(log_fn)
        try:
            mon = cls(log_fn=log_fn)
            if mon._stream is None:
                log_fn("[Client-VAD] 自检结果：⚠ 未就绪（pyaudio 未装 或 无音频输入设备），"
                       "直播时 VAD 将旁路为固定等待。")
            else:
                log_fn("[Client-VAD] 自检结果：✅ 已就绪，将使用设备 [%s]，"
                       "直播时会实时监听豆包语流。" % mon._device_name)
            mon.close()
        except Exception as e:
            log_fn("[Client-VAD] 自检异常：%s" % e)

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

    def _emit_level(self, db, avg, speaking, silence_elapsed, silence_hold):
        """把实时音量/说话状态推给 UI 回调（每帧调用，驱动音量指示条）。"""
        if self._on_level:
            try:
                self._on_level(db, avg, speaking, silence_elapsed, silence_hold)
            except Exception:
                pass

    def wait_for_doubao_speech_cycle(self, max_wait_start_sec: float = 6.0,
                                     max_speech_timeout_sec: float = 60.0) -> bool:
        """
        【本地 VAD 完整状态机】(修复"豆包思考期被误判播报结束"问题)

        ★ 设计核心（务必照此理解，勿理解为"固定检测 2 秒"）：
          - VAD 检测是【持续】的：整个轮次每 ~50ms 读一帧算 dB，从发消息到播报结束从不中断；
          - 2s(silence_hold_sec) 不是"检测窗口"，而是【SPEAKING 态下"连续静音"的维持阈值】；
          - 切话术完全由【VAD 检测结果的状态变化】驱动：
                有语音(均值>阈值) → 进入/保持 SPEAKING；
                连续无语音(均值≤阈值)累计满 2s → 状态变化到 ENDED → 切入下一轮。
          即：检测一直在，控制只看"说话态↔静音态"的跳变，不是数到 2 秒就判定。

        状态：WAITING_SPEECH(发消息后等豆包开口/思考) → SPEAKING(检测到真实语音) → ENDED(静音超阈值)
        约定：客户端给豆包发消息瞬间默认无语音。WAITING 期间静音属正常、绝不切句；
             仅 SPEAKING 状态下连续静音超 silence_hold_sec 才判"播报结束"切入下一轮。
             进入 SPEAKING 需连续 speak_confirm_sec 有语音(消抖)，防单帧提示音/杂音误触发。
        返回 True=本轮结束(可继续下一轮)；False=思考超时(豆包无语音回答，直接进下一句)。
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

            # ===== 完整状态机：发消息 → WAITING(等语音) → SPEAKING(有语音) → ENDED(静音超阈值) =====
            # 核心约定：客户端给豆包发消息的瞬间【默认无语音】。
            #   WAITING 状态：豆包在"思考/生成"，此期间静音属【正常】，绝不触发切句；
            #            只等待"真实语音出现"，或等待思考超时(视作豆包无语音回答)。
            #   SPEAKING 状态：仅在此状态下，连续静音超 silence_hold_sec 才判"播报结束"，切下一句。
            #   这样可避免：豆包还在思考(数秒无语音)就被误判"播报结束"而切走；也避免单帧提示音/杂音误入 SPEAKING。
            state = "WAITING_SPEECH"
            start_wait = time.time()
            speech_started = False
            confirm_frames = 0
            confirm_need = max(1, int(round(self.speak_confirm_sec / 0.05)))  # 需连续多少帧(0.05s/帧)确认真实语音
            recent = []
            last_log_t = 0.0
            self._log("[Client-VAD] 状态[WAITING]：已发消息，等待豆包开口(思考期无语音属正常；最多等 %.1fs)"
                      % max_wait_start_sec)
            while time.time() - start_wait < max_wait_start_sec:
                db = self.get_current_rms_db()
                recent.append(db)
                recent = recent[-8:]
                avg = sum(recent) / len(recent)
                now = time.time()
                # 注意：检测是持续运行的，这里把"真实是否过阈值"反映给音量条，
                # 让 WAITING 期也能看到豆包一开口音量条立刻变绿（体现"检测一直在"）。
                # 但【状态切换】仍走下方 confirm_frames 消抖逻辑，音量条显示与控制解耦。
                speaking_now = avg > self.energy_threshold_db
                self._emit_level(db, avg, speaking_now, None, self.silence_hold_sec)
                if now - last_log_t >= 0.5:
                    self._log("[Client-VAD]   [WAITING] 思考中 dB=%.1f 均值=%.1f (无语音属正常，继续等)"
                              % (db, avg))
                    last_log_t = now
                if avg > self.energy_threshold_db:
                    confirm_frames += 1
                    if confirm_frames >= confirm_need:
                        speech_started = True
                        self._log("[Client-VAD] ✅ 状态[→SPEAKING]：检测到真实语音(均值%.1f>阈值%.1f，连续%.2fs)："
                                  "豆包开始播报，音频流从 CABLE Input→CABLE Output 接通"
                                  % (avg, self.energy_threshold_db, self.speak_confirm_sec))
                        break
                else:
                    confirm_frames = 0
                time.sleep(0.05)

            if not speech_started:
                self._log("[Client-VAD] ⚠ 等待开口超时：%.1fs 内豆包未发声(可能文字回答/无语音)。"
                          "视作本轮无播报，直接进下一句。" % max_wait_start_sec)
                return False

            # ---- 状态 SPEAKING：监听语流，仅此状态静音超阈值才判结束 ----
            state = "SPEAKING"
            speech_start_time = time.time()
            silence_start = None
            recent = []
            self._log("[Client-VAD] 状态[SPEAKING]：监听语流，等豆包说完(静音超 %.1fs 即判播报结束)"
                      % self.silence_hold_sec)
            while time.time() - speech_start_time < max_speech_timeout_sec:
                db = self.get_current_rms_db()
                recent.append(db)
                recent = recent[-8:]
                avg = sum(recent) / len(recent)
                now = time.time()
                speaking = avg > self.energy_threshold_db
                sil_el = (now - silence_start) if (not speaking and silence_start is not None) else None
                self._emit_level(db, avg, speaking, sil_el, self.silence_hold_sec)
                if now - last_log_t >= 0.5:
                    state_txt = "说话中" if avg > self.energy_threshold_db else "静音(等结束)"
                    self._log("[Client-VAD]   [SPEAKING] dB=%.1f 均值=%.1f 状态=%s"
                              % (db, avg, state_txt))
                    last_log_t = now

                if avg <= self.energy_threshold_db:
                    if silence_start is None:
                        silence_start = now
                        self._log("[Client-VAD] 状态[SPEAKING]：进入静音，开始计时静音维持(%.1fs)"
                                  % self.silence_hold_sec)
                    elif now - silence_start >= self.silence_hold_sec:
                        dur = round(now - speech_start_time, 2)
                        self._log("[Client-VAD] ✅ 状态[→ENDED]：语流结束！本次播报时长 %.2fs，立即切入下一轮"
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


def run_live_listen_test(duration_sec: float = 6.0, log_fn=print):
    """诊断用：实时旁听当前 vad_input_device 的 dB，验证'声音是否真的到达 VAD'。
    无需豆包/开播——只要往 CABLE Input 放任意声音(如播段音乐、或开播让豆包说话)，
    这里 dB 明显上升(超过阈值)即证明 scrcpy→CABLE→VAD 链路接通。"""
    log_fn("[Client-VAD] ▶ 实时旁听测试 %.1fs：请此刻往 CABLE Input 播放声音"
          "(或开播让豆包说话)…" % duration_sec)
    mon = AudioPlaybackMonitor(log_fn=log_fn)
    if mon._stream is None:
        log_fn("[Client-VAD] ⚠ 无音频设备，无法测试。")
        return
    try:
        start = time.time()
        peak = -100.0
        while time.time() - start < duration_sec:
            db = mon.get_current_rms_db()
            peak = max(peak, db)
            bar = "#" * max(0, int((db + 60) / 3))
            log_fn("  dB=%.1f %s" % (db, bar))
            time.sleep(0.3)
        if peak > mon.energy_threshold_db:
            log_fn("[Client-VAD] 测试结束：峰值 dB=%.1f → 有声音到达 VAD ✅（链路接通）" % peak)
        else:
            log_fn("[Client-VAD] 测试结束：峰值 dB=%.1f → 长期静音，链路未接通 ❌"
                  "（查 scrcpy 是否真用 CABLE Input / 或把 CABLE Input 设为默认播放设备）" % peak)
    finally:
        mon.close()


def list_audio_input_devices(log_fn=print):
    """枚举并打印本机所有音频【输入】设备（名称+索引），标注回环/混音类。

    用于确认 config.vad_input_device 该填什么：选带「回环/混音」标记的设备名(或索引)。
    运行 `python -m src.audio.vad` 即可直接查看。"""
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
    except Exception as e:
        log_fn("[Client-VAD] ⚠ 无法枚举设备(pyaudio 未装?)：%s" % e)
        return []
    found = []
    log_fn("[Client-VAD] 本机音频输入设备清单：")
    for i in range(pa.get_device_count()):
        try:
            info = pa.get_device_info_by_index(i)
        except Exception:
            continue
        name = (info.get("name") or "?")
        max_in = int(info.get("maxInputChannels", 0) or 0)
        if max_in <= 0:
            continue
        is_loop = any(k in name.lower() for k in AudioPlaybackMonitor._LOOPBACK_KEYWORDS)
        tag = "  ← 回环/混音(推荐给 VAD)" if is_loop else ""
        log_fn("  [%d] %s%s" % (i, name, tag))
        found.append({"index": i, "name": name, "loopback": is_loop})
    pa.terminate()
    if not found:
        log_fn("[Client-VAD] (无可用输入设备)")
    return found


if __name__ == "__main__":
    # 直接运行本模块：列出本机音频输入设备 + 自检 VAD + 实时旁听测试(确认链路接通)
    list_audio_input_devices()
    AudioPlaybackMonitor.quick_probe()
    run_live_listen_test(6.0)
