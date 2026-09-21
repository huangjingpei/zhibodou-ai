"""AI 弹幕回复语音合成引擎 (TTS Engine)。

根据硬件显存自适应调度：
- 模式 A (tier='index_tts', 显存>=8G)：IndexTTS 语音克隆/高质量模型，未部署时平滑降级到 SAPI；
- 模式 B (tier='moss_tts', 4G<=显存<8G)：MOSS-TTS-Nano 极速轻量模型，未部署时平滑降级；
- 模式 C (tier='playwright', 显存<4G)：公屏文本回复（预留占位与文本日志输出）；
- 底座引擎 (WindowsSAPIEngine)：基于 Windows 原生 SAPI/pyttsx3，零显存占用，零模型下载，秒级产出。
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
from typing import Optional

import pyttsx3

logger = logging.getLogger(__name__)


def _convert_wav_to_mpegts(wav_path: str, ffmpeg_bin: Optional[str] = None) -> bytes:
    """使用 ffmpeg 将 wav 临时文件编码为 AAC 并封装成标准 MPEG-TS 二进制数据 (可选)。"""
    try:
        if ffmpeg_bin is None:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return b""

    with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
        tmp_ts = f.name

    try:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            wav_path,
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-f",
            "mpegts",
            tmp_ts,
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
        if res.returncode == 0 and os.path.exists(tmp_ts):
            with open(tmp_ts, "rb") as tf:
                return tf.read()
        logger.warning("FFmpeg 转码 MPEG-TS 失败 (code=%s)", res.returncode)
        return b""
    except Exception as exc:
        logger.error("FFmpeg 转码异常: %s", exc)
        return b""
    finally:
        if os.path.exists(tmp_ts):
            try:
                os.remove(tmp_ts)
            except OSError:
                pass


def _get_wav_duration(wav_path: str) -> float:
    """获取 wav 音频时长（秒）。"""
    try:
        import wave
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return float(frames) / float(rate) if rate > 0 else 1.0
    except Exception:
        return 1.0


class TTSEngine:
    """TTS 合成引擎抽象基类。"""

    def synthesize_to_wav(self, text: str) -> tuple[bytes, float]:
        """合成语音文本，直接返回 (WAV 二进制数据, 音频时长秒数)。无需 FFmpeg 转码。"""
        raise NotImplementedError

    def synthesize(self, text: str) -> tuple[bytes, float]:
        """向后兼容：默认委托给 synthesize_to_wav。"""
        return self.synthesize_to_wav(text)

    def synthesize_to_ts(self, text: str) -> bytes:
        """合成语音文本并返回 MPEG-TS 二进制数据（如需）。"""
        wav_bytes, _ = self.synthesize_to_wav(text)
        if not wav_bytes:
            return b""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_wav = f.name
        try:
            return _convert_wav_to_mpegts(tmp_wav)
        finally:
            if os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass

    def is_text_only(self) -> bool:
        """是否为纯公屏文本回复模式（不产出音频流）。"""
        return False


class WindowsSAPIEngine(TTSEngine):
    """基于 Windows 原生 SAPI / pyttsx3 的零资源占用合成引擎。"""

    def __init__(self, rate: int = 150, volume: float = 0.95):
        self.rate = rate
        self.volume = volume
        self._lock = threading.Lock()

    def synthesize_to_wav(self, text: str) -> tuple[bytes, float]:
        if not text or not text.strip():
            return b"", 0.0

        clean_text = text.strip()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_wav = f.name

        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass

            with self._lock:
                eng = pyttsx3.init()
                eng.setProperty("rate", self.rate)
                eng.setProperty("volume", self.volume)
                eng.save_to_file(clean_text, tmp_wav)
                eng.runAndWait()
                eng.stop()

            if not os.path.exists(tmp_wav) or os.path.getsize(tmp_wav) == 0:
                logger.warning("SAPI 合成 WAV 失败或文件为空")
                return b"", 0.0

            duration_sec = _get_wav_duration(tmp_wav)
            with open(tmp_wav, "rb") as wf:
                wav_bytes = wf.read()
            return wav_bytes, duration_sec
        except Exception as exc:
            logger.error("SAPI 合成异常: %s", exc)
            return b"", 0.0
        finally:
            if os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass


class IndexTTSEngine(TTSEngine):
    """适用于显存 >= 8GB 的 IndexTTS 引擎（支持外挂 Sidecar 服务与自动降级）。"""

    def __init__(self, sidecar_url: str = "http://127.0.0.1:9880/tts"):
        self.sidecar_url = sidecar_url
        self._fallback_sapi = WindowsSAPIEngine()

    def synthesize_to_ts(self, text: str) -> bytes:
        import requests

        try:
            resp = requests.post(
                self.sidecar_url,
                json={"text": text, "format": "wav"},
                timeout=4.0,
            )
            if resp.status_code == 200 and resp.content:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(resp.content)
                    tmp_wav = f.name
                try:
                    return _convert_wav_to_mpegts(tmp_wav)
                finally:
                    if os.path.exists(tmp_wav):
                        os.remove(tmp_wav)
        except Exception:
            logger.info("【IndexTTS】未检测到本地 9880 服务，自动使用轻量原生 SAPI 引擎合成")

        return self._fallback_sapi.synthesize_to_ts(text)


class MossTTSEngine(TTSEngine):
    """适用于 4GB <= 显存 < 8GB 的 MOSS-TTS-Nano 引擎（支持外挂 Sidecar 与自动降级）。"""

    def __init__(self, sidecar_url: str = "http://127.0.0.1:9881/tts"):
        self.sidecar_url = sidecar_url
        self._fallback_sapi = WindowsSAPIEngine()

    def synthesize_to_ts(self, text: str) -> bytes:
        import requests

        try:
            resp = requests.post(
                self.sidecar_url,
                json={"text": text, "model": "moss-tts-nano"},
                timeout=3.0,
            )
            if resp.status_code == 200 and resp.content:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(resp.content)
                    tmp_wav = f.name
                try:
                    return _convert_wav_to_mpegts(tmp_wav)
                finally:
                    if os.path.exists(tmp_wav):
                        os.remove(tmp_wav)
        except Exception:
            logger.info("【MOSS-TTS】未检测到本地 9881 服务，自动使用轻量原生 SAPI 引擎合成")

        return self._fallback_sapi.synthesize_to_ts(text)


class PlaywrightReplyAdapter(TTSEngine):
    """适用于低显存 (<4GB) 的 Playwright 公屏文字回复模式（预留接口）。"""

    def is_text_only(self) -> bool:
        return True

    def synthesize_to_ts(self, text: str) -> bytes:
        return b""


def create_tts_engine(tier: str, config: Optional[dict] = None) -> TTSEngine:
    """工厂方法：根据硬件自适应档位创建对应的 TTS 引擎实例。"""
    tier = (tier or "").lower().strip()
    if tier == "index_tts":
        url = (config or {}).get("index_tts_url", "http://127.0.0.1:9880/tts")
        return IndexTTSEngine(sidecar_url=url)
    elif tier == "moss_tts":
        url = (config or {}).get("moss_tts_url", "http://127.0.0.1:9881/tts")
        return MossTTSEngine(sidecar_url=url)
    elif tier == "playwright":
        return PlaywrightReplyAdapter()
    else:
        return WindowsSAPIEngine()
