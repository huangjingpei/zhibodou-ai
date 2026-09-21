"""AI 智能弹幕回复协调与执行工作线程 (AIReplyWorker)。

全链路协同流程（方案 A - 零 FFmpeg 原生架构）：
1. 监听弹幕与礼物消息 (GiftMessage / ChatMessage)；
2. 调用 DeepSeek / Ollama 语义网关执行价值研判与高情商口播生成；
3. 根据硬件自适应档位选择 TTS 合成（IndexTTS / MOSS-TTS / 原生SAPI / Playwright预留），直出 WAV；
4. 纯软件算法音频闪避：弹幕语音到达时，不中断豆包，通过 WASAPI 算法平滑下压豆包音量至 25%，双声并存；
5. 将合成的语音推入 OBS 浏览器源原生音频通道 (OBSAudioBridge) 实时播放，播毕平滑恢复豆包音量。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

from audio.ducking import get_ducking_manager
from audio.obs_bridge import get_obs_bridge
from audio.tts_engine import create_tts_engine, TTSEngine
from danma.hardware import detect_gpu_hardware
from danma.llm_gateway import evaluate_and_reply, is_llm_configured
from settings import config

logger = logging.getLogger(__name__)


class AIReplyWorker:
    """AI 智能弹幕回复工作者。"""

    def __init__(self):
        self.running = False
        self.message_queue: queue.Queue[dict] = queue.Queue(maxsize=50)
        self.worker_thread: Optional[threading.Thread] = None

        self.hardware_info = detect_gpu_hardware()
        self.tts_engine: Optional[TTSEngine] = None
        self.obs_bridge = get_obs_bridge()
        self.ducking_manager = get_ducking_manager()

        self._last_reply_time = 0.0
        self._cooldown_sec = 1.5  # 两次口播之间的最小安全间隔

    def init_engines(self):
        """根据最新配置初始化 TTS 引擎。"""
        cfg = config.load_config() or {}
        tier = self.hardware_info.get("tier", "playwright")
        self.tts_engine = create_tts_engine(tier, cfg)
        logger.info(
            "AI 回复引擎初始化完成: Tier=%s, TTS=%s",
            tier,
            type(self.tts_engine).__name__,
        )

    def start(self) -> bool:
        if self.running:
            return True

        self.init_engines()
        self.obs_bridge.start()

        self.running = True
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name="AIReply-Worker",
            daemon=True,
        )
        self.worker_thread.start()
        logger.info("✅ AI 弹幕回复后台工作线程已启动")
        return True

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            try:
                self.message_queue.put_nowait({"_sentinel": True})
            except queue.Full:
                pass
            self.worker_thread.join(timeout=1.0)
            self.worker_thread = None

        self.obs_bridge.stop()
        self.ducking_manager.restore()
        logger.info("AI 弹幕回复工作线程已停止")

    def enqueue_message(self, message: dict):
        """将待研判的弹幕/礼物消息推入工作队列。"""
        if not self.running:
            return
        if not message or not isinstance(message, dict):
            return

        msg_type = str(message.get("type") or "")
        if msg_type not in ("GiftMessage", "ChatMessage"):
            return

        try:
            self.message_queue.put_nowait(message)
        except queue.Full:
            try:
                self.message_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.message_queue.put_nowait(message)
            except queue.Full:
                pass

    def _worker_loop(self):
        while self.running:
            try:
                msg = self.message_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if msg.get("_sentinel"):
                break

            try:
                self._handle_single_message(msg)
            except Exception as exc:
                logger.error("处理弹幕消息异常: %s", exc)

    def _handle_single_message(self, msg: dict):
        from gui import ui

        msg_type = str(msg.get("type") or "")
        name = str(msg.get("name") or "观众").strip() or "观众"
        content = str(msg.get("content") or "").strip()
        gift_name = str(msg.get("gift_name") or "礼物").strip()
        gift_count = int(msg.get("gift_count") or 1)

        # 1. 调用 LLM 决策
        cfg = config.load_config() or {}
        product_context = {
            "product_name": str(cfg.get("product_name") or "爆款商品"),
            "product_desc": str(cfg.get("product_desc") or ""),
            "pre_meet_text": str(cfg.get("pre_meet_text") or ""),
        }
        res = evaluate_and_reply(msg, product_context, cfg)
        if not res.get("should_reply") or not res.get("reply_text"):
            return

        reply_type = res.get("reply_type") or "chat"
        reply_text = str(res.get("reply_text") or "").strip()
        ui.log_screen(f"【AI弹幕回复】[{reply_type}] 决策: {reply_text}")

        # 2. 纯文本模式 (Tier C / Playwright 预留)
        if self.tts_engine.is_text_only():
            ui.log_screen(f"【AI弹幕回复】[公屏打字回复·预留] 拟发送: {reply_text}")
            return

        # 3. 冷却防炸麦保护
        now = time.monotonic()
        elapsed = now - self._last_reply_time
        if elapsed < self._cooldown_sec:
            time.sleep(self._cooldown_sec - elapsed)

        # 4. 语音合成与双声共存闪避
        try:
            wav_bytes, duration_sec = self.tts_engine.synthesize_to_wav(reply_text)
            if wav_bytes:
                # 触发软件算法闪避：将豆包伴奏音量压低至 25%，不打断播报
                self.ducking_manager.duck(duration_sec, log_fn=ui.log_screen)

                # 推送到 OBS 浏览器源播放
                delivered = self.obs_bridge.push_speech(
                    wav_bytes=wav_bytes,
                    duration_sec=duration_sec,
                    display_text=reply_text,
                )
                self._last_reply_time = time.monotonic()
                if delivered > 0:
                    ui.log_screen(f"【AI弹幕回复】✅ 已推送至 OBS 浏览器源播放 ({delivered} 个客户端连接)")
                else:
                    ui.log_screen("【AI弹幕回复】✅ 语音已推流 (OBS 浏览器源未连接，请添加 http://127.0.0.1:8554/danmu_audio)")
            else:
                ui.log_screen("【AI弹幕回复】⚠ TTS 语音合成返回为空")
        except Exception as exc:
            ui.log_screen(f"【AI弹幕回复】❌ 合成或播放异常: {exc}")


# 全局单例
_global_worker: Optional[AIReplyWorker] = None
_worker_lock = threading.Lock()


def get_ai_reply_worker() -> AIReplyWorker:
    global _global_worker
    with _worker_lock:
        if _global_worker is None:
            _global_worker = AIReplyWorker()
        return _global_worker
