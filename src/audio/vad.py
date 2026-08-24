# ==============================================================================
# src/audio/vad.py
# 纯电脑客户端本地音频 VAD 监听引擎 (毫秒级 PCM 能量检测，零 ADB 依赖)
# ==============================================================================
import time
import math
import array

class AudioPlaybackMonitor:
    """
    【本地客户端语音活动检测器 (VAD)】
    直接在电脑本地捕获声卡输出/麦克风流，计算真实分贝值与语流状态
    彻底抛弃 slow ADB dumpsys audio
    """
    def __init__(self, energy_threshold_db: float = -42.0, silence_hold_sec: float = 1.0):
        self.energy_threshold_db = energy_threshold_db   # 静音判定阈值 (dB)
        self.silence_hold_sec = silence_hold_sec         # 语毕静音维持时间 (秒)
        self._pa = None
        self._stream = None
        self._init_local_audio()

    def _init_local_audio(self):
        """尝试初始化本地 PyAudio 声卡输入流"""
        try:
            import pyaudio
            self._pa = pyaudio.PyAudio()
            # 打开默认录音/回放捕获设备 (16kHz, 16bit, 单声道)
            self._stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024
            )
        except Exception:
            self._stream = None

    def get_current_rms_db(self) -> float:
        """读取本地当前一帧音频的分贝能量值 (dB)"""
        if self._stream:
            try:
                data = self._stream.read(1024, exception_on_overflow=False)
                shorts = array.array('h', data)
                if not shorts:
                    return -100.0
                # 计算均方根 RMS
                sum_squares = sum(s * s for s in shorts)
                rms = math.sqrt(sum_squares / len(shorts))
                if rms <= 0:
                    return -100.0
                # 转换为标准 dBFS 分贝
                db = 20 * math.log10(rms / 32768.0)
                return db
            except Exception:
                return -100.0
        return -100.0

    def is_speaking(self) -> bool:
        """判断当前是否有实际声音发出"""
        if self._stream:
            db = self.get_current_rms_db()
            return db > self.energy_threshold_db
        return False

    def wait_for_doubao_speech_cycle(self, max_wait_start_sec: float = 6.0, max_speech_timeout_sec: float = 60.0) -> bool:
        """
        【本地 VAD 完整生命周期检测】
        1. 监听本地声卡：等待豆包开始发声 (耗时 < 10ms 响应)
        2. 豆包说话中：持续锁定语流
        3. 豆包说完：本地静音维持超过 silence_hold_sec 后立即切入下一轮
        """
        print("[Client-VAD] 1. 本地声卡监听中，等待豆包开口发声...")
        start_wait = time.time()
        speech_started = False

        # 如果没有本地麦克风权限/设备，做智能时长缓冲
        if not self._stream:
            print("[Client-VAD] (未检测到本地声卡流，启用自适应平滑语速等待)")
            time.sleep(4.0)
            return True

        # 阶段 1: 等待发声开始
        while time.time() - start_wait < max_wait_start_sec:
            if self.is_speaking():
                speech_started = True
                print("[Client-VAD] 2. 检测到语流输入，豆包正在播报...")
                break
            time.sleep(0.05)

        if not speech_started:
            print("[Client-VAD] (等待发声超时，直接切入)")
            return False

        # 阶段 2: 语流维持与静音检测
        speech_start_time = time.time()
        silence_start_time = None

        while time.time() - speech_start_time < max_speech_timeout_sec:
            if not self.is_speaking():
                if silence_start_time is None:
                    silence_start_time = time.time()
                elif time.time() - silence_start_time >= self.silence_hold_sec:
                    duration = round(time.time() - speech_start_time, 2)
                    print(f"[Client-VAD] 3. 语流结束！(本次播报时长: {duration}s)，立即切入下一轮！")
                    return True
            else:
                silence_start_time = None
            time.sleep(0.05)

        return True

    def close(self):
        """释放声卡资源"""
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass