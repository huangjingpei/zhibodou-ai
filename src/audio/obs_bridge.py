"""OBS 浏览器源原生音频桥接服务 (方案 A - 零外部依赖)。

利用 OBS 内置的 Chromium 浏览器源 (Browser Source)，通过本地轻量 Web 页面
实现弹幕语音的独立音轨推流与采集：
- 零 FFmpeg 依赖，纯 Python 标准库实现；
- OBS 来源添加「浏览器」，URL 填入 http://127.0.0.1:8554/danmu_audio；
- 勾选「通过 OBS 控制音频」，OBS 调音台自动生成独立的弹幕音频通道；
- 支持未来礼物动效、气泡弹窗与语音的音画一体化渲染。
"""
from __future__ import annotations

import http.server
import json
import logging
import queue
import socketserver
import threading
import time
import uuid
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Zhibodou AI Danmu Audio Bridge</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 16px;
      background: transparent;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    #badge-container {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .danmu-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(17, 24, 39, 0.88);
      border: 1px solid rgba(0, 229, 255, 0.4);
      color: #ffffff;
      padding: 8px 14px;
      border-radius: 9999px;
      font-size: 14px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
      animation: fadeIn 0.3s ease-out;
      max-width: 460px;
    }
    .danmu-icon {
      font-size: 16px;
    }
    .danmu-text {
      color: #38bdf8;
      font-weight: 500;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeOut {
      from { opacity: 1; transform: translateY(0); }
      to { opacity: 0; transform: translateY(-8px); }
    }
  </style>
</head>
<body>
  <div id="badge-container"></div>

  <script>
    const container = document.getElementById('badge-container');

    function showBadge(text, durationSec) {
      if (!text) return;
      const el = document.createElement('div');
      el.className = 'danmu-badge';
      el.innerHTML = `<span class="danmu-icon">💬</span><span class="danmu-text">${text}</span>`;
      container.appendChild(el);
      setTimeout(() => {
        el.style.animation = 'fadeOut 0.4s ease-out forwards';
        setTimeout(() => el.remove(), 400);
      }, Math.max(2, durationSec || 3) * 1000);
    }

    function playAudio(url, volume) {
      if (!url) return;
      const audio = new Audio(url);
      audio.volume = (volume !== undefined) ? volume : 1.0;
      audio.play().catch(err => {
        console.warn('[AudioBridge] Autoplay warning:', err);
      });
    }

    function connectSSE() {
      const es = new EventSource('/danmu/events');
      es.onmessage = function(event) {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'speech' && data.audio_url) {
            playAudio(data.audio_url, data.volume || 1.0);
            showBadge(data.display_text, data.duration || 3);
          }
        } catch(e) {
          console.error('[AudioBridge] Parse error:', e);
        }
      };
      es.onerror = function() {
        es.close();
        setTimeout(connectSSE, 2000);
      };
    }

    connectSSE();
  </script>
</body>
</html>
"""


class OBSAudioBridge:
    """OBS 浏览器源原生音频桥接器。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8554):
        self.host = host
        self.port = port
        self.server: Optional[socketserver.ThreadingTCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False

        self._audio_cache: Dict[str, tuple[bytes, float]] = {}  # id -> (wav_bytes, expire_ts)
        self._cache_lock = threading.Lock()
        self._sse_clients: Set[queue.Queue] = set()
        self._clients_lock = threading.Lock()

    @property
    def bridge_url(self) -> str:
        return f"http://{self.host}:{self.port}/danmu_audio"

    def start(self) -> bool:
        if self.running:
            return True

        bridge_ref = self

        class BridgeHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # 过滤高频日志

            def do_GET(self):
                # 1. 静态 HTML 页面
                if self.path in ("/", "/danmu_audio", "/index.html"):
                    body = HTML_PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return

                # 2. SSE 实时事件通道
                if self.path == "/danmu/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()

                    client_q: queue.Queue = queue.Queue(maxsize=50)
                    with bridge_ref._clients_lock:
                        bridge_ref._sse_clients.add(client_q)
                    logger.info("OBS 浏览器源已建立音频连接: %s", self.client_address)

                    try:
                        # 初始握手包
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        while bridge_ref.running:
                            try:
                                msg = client_q.get(timeout=10.0)
                                payload = f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode("utf-8")
                                self.wfile.write(payload)
                                self.wfile.flush()
                            except queue.Empty:
                                # 心跳保活
                                self.wfile.write(b": heartbeat\n\n")
                                self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    except Exception as exc:
                        logger.debug("OBS 浏览器源断开: %s", exc)
                    finally:
                        with bridge_ref._clients_lock:
                            bridge_ref._sse_clients.discard(client_q)
                        logger.info("OBS 浏览器源已断开连接: %s", self.client_address)
                    return

                # 3. 动态音频 WAV 获取
                if self.path.startswith("/audio/"):
                    audio_id = self.path[len("/audio/"):].split("?")[0]
                    with bridge_ref._cache_lock:
                        entry = bridge_ref._audio_cache.get(audio_id)
                    if entry:
                        wav_data = entry[0]
                        self.send_response(200)
                        self.send_header("Content-Type", "audio/wav")
                        self.send_header("Content-Length", str(len(wav_data)))
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(wav_data)
                        return
                    else:
                        self.send_error(404, "Audio Not Found")
                        return

                self.send_error(404)

        try:
            socketserver.ThreadingTCPServer.allow_reuse_address = True
            self.server = socketserver.ThreadingTCPServer((self.host, self.port), BridgeHandler)
        except Exception as exc:
            logger.error("启动 OBS 浏览器音频服务失败: %s", exc)
            return False

        self.running = True
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="OBS-AudioBridge",
            daemon=True,
        )
        self.server_thread.start()

        # 启动缓存清理线程
        threading.Thread(target=self._clean_cache_loop, daemon=True).start()
        logger.info("✅ OBS 浏览器音频桥接服务已就绪: %s", self.bridge_url)
        return True

    def _clean_cache_loop(self):
        """定期清理过期音频缓存。"""
        while self.running:
            time.sleep(15)
            now = time.time()
            with self._cache_lock:
                expired = [k for k, v in self._audio_cache.items() if v[1] < now]
                for k in expired:
                    del self._audio_cache[k]

    def push_speech(self, wav_bytes: bytes, duration_sec: float = 2.0, display_text: str = "") -> int:
        """推送一段合成完成的语音并通知 OBS 播放。返回接收成功的客户端数。"""
        if not wav_bytes:
            return 0

        audio_id = f"{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        with self._cache_lock:
            # 缓存保留 60 秒供 OBS 浏览器获取
            self._audio_cache[audio_id] = (wav_bytes, time.time() + 60.0)

        event_payload = {
            "type": "speech",
            "audio_url": f"/audio/{audio_id}",
            "duration": round(duration_sec, 2),
            "display_text": display_text,
            "volume": 1.0,
        }

        delivered = 0
        with self._clients_lock:
            for q in list(self._sse_clients):
                try:
                    q.put_nowait(event_payload)
                    delivered += 1
                except queue.Full:
                    pass

        return delivered

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        with self._clients_lock:
            self._sse_clients.clear()
        with self._cache_lock:
            self._audio_cache.clear()
        logger.info("OBS 浏览器音频服务已停止")


# 全局单例
_global_bridge: Optional[OBSAudioBridge] = None
_bridge_lock = threading.Lock()


def get_obs_bridge(port: int = 8554) -> OBSAudioBridge:
    global _global_bridge
    with _bridge_lock:
        if _global_bridge is None:
            _global_bridge = OBSAudioBridge(port=port)
        return _global_bridge
