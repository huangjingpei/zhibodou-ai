import math
import subprocess
import time

try:
    from src.core.paths import ADB_EXE
except (ImportError, ModuleNotFoundError):
    try:
        from core.paths import ADB_EXE
    except (ImportError, ModuleNotFoundError):
        ADB_EXE = "adb"

class AudioPlaybackMonitor:
    """
    【声音播放状态感知与 VAD 动态检测中枢】
    彻底解决：
    1. 豆包长回复被定时器中途打断
    2. 豆包短回复后直播间长时间冷场
    3. 播放失败或异常时的状态失步
    """
    def __init__(self, device_id: str = None, energy_threshold_db: float = -38.0, silence_hold_sec: float = 0.8):
        self.device_id = device_id
        self.energy_threshold_db = energy_threshold_db
        self.silence_hold_sec = silence_hold_sec
        self.base_adb = [ADB_EXE]
        if device_id:
            self.base_adb.extend(["-s", device_id])

    def check_system_audio_playing(self) -> bool:
        """
        【模式 A：Android 系统底层 AudioTrack 状态直读 (免侵入)】
        读取 dumpsys audio 中当前是否有应用处于 state:started (播放中)
        """
        try:
            cmd = self.base_adb + ["shell", "dumpsys", "audio"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            out = res.stdout
            
            # 匹配 STREAM_MUSIC 的 player 状态
            if "state:started" in out or "AudioTrack state: 1" in out:
                return True
        except Exception as e:
            print(f"[check_system_audio_playing] 查询系统音频状态异常: {e}")
        return False

    def wait_for_doubao_speech_cycle(self, max_wait_start_sec: float = 8.0, max_speech_timeout_sec: float = 60.0) -> bool:
        """
        【核心动态状态机】
        1. 发送话术后，进入 等待豆包开始发声 (WAIT_START)
        2. 监听到发声后，进入 持续播放锁定 (PLAYING)
        3. 连续检测到静音超出阈值，判定 朗读自然结束 (FINISHED)
        4. 立即无缝返回 True，触发下一轮话术下发
        """
        print("[AudioMonitor] 1. 等待豆包开始合成并播放语音...")
        start_time = time.time()
        speech_started = False

        # 阶段 1：等待发声开始
        while time.time() - start_time < max_wait_start_sec:
            if self.check_system_audio_playing():
                speech_started = True
                print("[AudioMonitor] 2. 豆包已开始发声播放！进入语流锁定状态...")
                break
            time.sleep(0.15)

        if not speech_started:
            print("[AudioMonitor] 提示：在设定时间内未探测到语音开始，自动流转")
            return False

        # 阶段 2：等待播放自然结束 (VAD / AudioTrack 状态检测)
        speech_play_start = time.time()
        silence_start_time = None

        while time.time() - speech_play_start < max_speech_timeout_sec:
            is_playing = self.check_system_audio_playing()
            
            if not is_playing:
                if silence_start_time is None:
                    silence_start_time = time.time()
                elif time.time() - silence_start_time >= self.silence_hold_sec:
                    # 连续静音达到设定时长，判定朗读完毕
                    duration = round(time.time() - speech_play_start, 2)
                    print(f"[AudioMonitor] 3. 朗读完毕！持续播放 {duration}s，无缝切入下一轮！")
                    return True
            else:
                # 重新发声，重置静音计时
                silence_start_time = None
            
            time.sleep(0.1)

        print("[AudioMonitor] 提示：达到单轮话术最大超时限制，流转至下一条")
        return True
