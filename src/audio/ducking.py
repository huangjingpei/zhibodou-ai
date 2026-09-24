"""纯软件算法音频闪避管理器 (Software Audio Ducking Manager)。

使用 Windows Core Audio / WASAPI 会话音量控制算法：
当弹幕 TTS 语音播报时，通过算法在 50~80ms 内对 scrcpy.exe 进程的音频进行平滑淡出压低
（降至 25% 左右的伴奏背景音量），使两个声音和谐共存；
弹幕 TTS 播报完毕后，通过算法在 100~150ms 内平滑淡入恢复至原始音量。
完全不触碰手机硬件或 ADB 音量，纯由宿主机软件算法处理。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _ramp_volume(session_vol, start_vol: float, end_vol: float, duration_sec: float = 0.08, steps: int = 8):
    """音频增益平滑线性插值过渡算法 (避免硬切产生电噪杂音)。"""
    try:
        dt = max(0.005, duration_sec / steps)
        for i in range(1, steps + 1):
            ratio = i / steps
            current = start_vol + (end_vol - start_vol) * ratio
            session_vol.SetMasterVolume(float(current), None)
            time.sleep(dt)
    except Exception as exc:
        logger.debug("音量过渡异常: %s", exc)


class SoftwareAudioDuckingManager:
    """Windows 进程级纯软件音频闪避器。"""

    def __init__(self, target_process: str = "scrcpy.exe", duck_ratio: Optional[float] = None):
        self.target_process = target_process.lower()
        if duck_ratio is None:
            try:
                from settings import config
                duck_ratio = float(config.load_config().get("audio_duck_ratio", 0.25))
            except Exception:
                duck_ratio = 0.25
        self.duck_ratio = duck_ratio  # 压低后的音量比例（默认25%）
        self._lock = threading.Lock()
        self._is_ducked = False
        self._original_volume: float = 1.0
        self._restore_timer: Optional[threading.Timer] = None
        self._restore_deadline: float = 0.0

    def _find_target_session(self):
        """定位目标进程 (scrcpy.exe) 的 WASAPI 音频会话。"""
        try:
            from pycaw.pycaw import AudioUtilities
            for session in AudioUtilities.GetAllSessions():
                proc = session.Process
                if proc:
                    try:
                        pname = proc.name().lower()
                        if pname == self.target_process:
                            return session.SimpleAudioVolume
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug("枚举音频会话失败: %s", exc)
        return None

    def duck(self, duration_sec: float, log_fn=None):
        """执行软件压音算法：在指定时长内将豆包伴奏音量压低。"""
        with self._lock:
            now = time.monotonic()
            # 延长闪避恢复期限
            self._restore_deadline = max(self._restore_deadline, now + duration_sec + 0.3)

            if self._restore_timer:
                try:
                    self._restore_timer.cancel()
                except Exception:
                    pass
                self._restore_timer = None

            if not self._is_ducked:
                vol_control = self._find_target_session()
                if vol_control:
                    try:
                        cur_vol = vol_control.GetMasterVolume()
                        self._original_volume = cur_vol if cur_vol > 0.05 else 1.0
                        target_vol = max(0.1, self._original_volume * self.duck_ratio)
                        # 开启独立线程执行平滑淡出，不阻塞 TTS 播放
                        threading.Thread(
                            target=_ramp_volume,
                            args=(vol_control, cur_vol, target_vol, 0.06, 6),
                            daemon=True,
                        ).start()
                        self._is_ducked = True
                        msg = f"【软件音量闪避】🔽 弹幕播报中，豆包音量平滑下压至 {int(target_vol * 100)}%"
                        logger.info(msg)
                        if log_fn:
                            log_fn(msg)
                    except Exception as exc:
                        logger.debug("执行压音失败: %s", exc)

            # 安排恢复定时器
            remaining = max(0.3, self._restore_deadline - time.monotonic())
            self._restore_timer = threading.Timer(remaining, self._on_timer_expire, args=[log_fn])
            self._restore_timer.daemon = True
            self._restore_timer.start()

    def _on_timer_expire(self, log_fn=None):
        with self._lock:
            if time.monotonic() >= self._restore_deadline - 0.05:
                self._restore_locked(log_fn)
            else:
                remaining = max(0.2, self._restore_deadline - time.monotonic())
                self._restore_timer = threading.Timer(remaining, self._on_timer_expire, args=[log_fn])
                self._restore_timer.daemon = True
                self._restore_timer.start()

    def restore(self, log_fn=None):
        """主动恢复原始音量。"""
        with self._lock:
            if self._restore_timer:
                try:
                    self._restore_timer.cancel()
                except Exception:
                    pass
                self._restore_timer = None
            self._restore_locked(log_fn)

    def _restore_locked(self, log_fn=None):
        if self._is_ducked:
            vol_control = self._find_target_session()
            if vol_control:
                try:
                    cur_vol = vol_control.GetMasterVolume()
                    target_vol = self._original_volume if self._original_volume is not None else 1.0
                    threading.Thread(
                        target=_ramp_volume,
                        args=(vol_control, cur_vol, target_vol, 0.12, 8),
                        daemon=True,
                    ).start()
                    msg = f"【软件音量闪避】🔼 弹幕播报结束，豆包音量平滑恢复至 {int(target_vol * 100)}%"
                    logger.info(msg)
                    if log_fn:
                        log_fn(msg)
                except Exception as exc:
                    logger.debug("执行音量恢复失败: %s", exc)
        self._is_ducked = False


# 全局单例
_global_ducking: Optional[SoftwareAudioDuckingManager] = None
_ducking_lock = threading.Lock()


def get_ducking_manager() -> SoftwareAudioDuckingManager:
    global _global_ducking
    with _ducking_lock:
        if _global_ducking is None:
            _global_ducking = SoftwareAudioDuckingManager()
        return _global_ducking
