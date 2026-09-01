"""弹幕采集器与客户端 UI 之间的进程内桥接。

浏览器采集线程只负责把标准消息放入有界队列；Tk 主线程定时批量消费，
不再经过本机 HTTP/Flask 或旧的 WebSocket 中转服务。
"""
from __future__ import annotations

import importlib.util
import queue
import threading
import time
import tkinter as tk
from typing import Iterable

from core import state
from gui import theme, ui
from settings import config

_UI_POLL_MS = 100
_UI_BATCH_SIZE = 100
_MAX_UI_LINES = 1000
_ui_pump_started = False
_ui_after_id = None
_lifecycle_lock = threading.Lock()


def _as_messages(data) -> Iterable[dict]:
    if isinstance(data, dict):
        return (data,)
    if isinstance(data, (list, tuple)):
        return (item for item in data if isinstance(item, dict))
    return ()


def enqueue_messages(data):
    """采集线程入口；队列满时丢最旧消息，保证直播客户端不会耗尽内存。"""
    for message in _as_messages(data):
        try:
            state.danmu_queue.put_nowait(message)
        except queue.Full:
            try:
                state.danmu_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                state.danmu_queue.put_nowait(message)
            except queue.Full:
                pass


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _set_label(widget, text):
    if widget is not None:
        widget.config(text=text)


def _set_capture_ui(text, color="#9ca3af", running=None):
    if ui.is_shutting_down():
        return
    if ui.lab_danmu_status is not None:
        ui.lab_danmu_status.config(text=f"💬弹幕：{text}", fg=color)
    if ui.btn_danmu is not None and running is not None:
        if running:
            ui.btn_danmu.config(text="停止弹幕", bg="#9A6226", activebackground=theme.AMBER)
        else:
            ui.btn_danmu.config(text="启动弹幕", bg=theme.PRIMARY,
                                activebackground=theme.PRIMARY_HOVER)


def _append_danmu(name, content, event=""):
    if ui.txt_danmu is None:
        return
    timestamp = time.strftime("%H:%M:%S")
    prefix = f"{event} " if event else ""
    ui.txt_danmu.insert(tk.END, f"[{timestamp}] {prefix}{name}：{content}\n")
    ui.txt_danmu.see(tk.END)
    # 长时间直播不能让 Text 控件无限增长。
    try:
        line_count = int(ui.txt_danmu.index("end-1c").split(".")[0])
        if line_count > _MAX_UI_LINES:
            ui.txt_danmu.delete("1.0", f"{line_count - _MAX_UI_LINES + 1}.0")
    except (AttributeError, tk.TclError, ValueError):
        pass


def process_message(message: dict):
    """在 Tk 主线程处理一条采集器标准消息。"""
    msg_type = str(message.get("type") or "")
    name = str(message.get("name") or "游客").strip() or "游客"
    content = str(message.get("content") or "").strip()

    if msg_type == "SystemMessage":
        if content:
            ui.log_screen(f"【弹幕采集】{content}")
            if "采集页面已启动" in content:
                _set_capture_ui("监听中", "#34d399", True)
            elif "意外退出" in content:
                _set_capture_ui("重连中", "#fbbf24", True)
        return
    if msg_type == "CollectorStatus":
        status = str(message.get("status") or "")
        if status == "error":
            _set_capture_ui(content or "启动失败", "#ff6b6b", False)
        elif status == "starting":
            _set_capture_ui("启动中", "#22d3ee", True)
        return
    if msg_type == "RoomMessage":
        state.online_num = max(0, _safe_int(message.get("count")))
        _set_label(ui.lab_online, f"📶 在线：{state.online_num} 人")
        return
    if msg_type == "LikeMessage":
        state.like_cnt += max(1, _safe_int(message.get("count"), 1))
        _set_label(ui.lab_like, f"👍 点赞：{state.like_cnt}")
        return
    if msg_type == "GiftMessage":
        count = max(1, _safe_int(message.get("gift_count"), 1))
        state.gift_cnt += count
        gift_name = str(message.get("gift_name") or "礼物")
        _set_label(ui.lab_gift, f"🎁礼物：{state.gift_cnt}")
        _append_danmu(name, f"{gift_name} × {count}", "🎁")
        return
    if msg_type == "ChatMessage":
        if not content:
            return
        state.comment_cnt += 1
        state.last_danmu_text = content
        _set_capture_ui("接收中", "#34d399", True)
        _append_danmu(name, content)
        return
    if msg_type == "MemberMessage":
        _append_danmu(name, content or "进入直播间", "👋")
        return
    if msg_type == "SocialMessage":
        _append_danmu(name, content or "分享或关注了直播间", "⭐")


def _drain_ui_queue():
    global _ui_after_id
    if ui.is_shutting_down():
        _ui_after_id = None
        return
    for _ in range(_UI_BATCH_SIZE):
        try:
            message = state.danmu_queue.get_nowait()
        except queue.Empty:
            break
        try:
            process_message(message)
        except Exception as exc:
            ui.log_screen(f"【弹幕采集】消息处理失败：{exc}")
    try:
        if ui.root and ui.root.winfo_exists():
            _ui_after_id = ui.root.after(_UI_POLL_MS, _drain_ui_queue)
    except tk.TclError:
        _ui_after_id = None


def initialize_ui_pump():
    """必须从 Tk 主线程调用一次。"""
    global _ui_pump_started, _ui_after_id
    if _ui_pump_started or ui.root is None:
        return
    _ui_pump_started = True
    _ui_after_id = ui.root.after(_UI_POLL_MS, _drain_ui_queue)


def shutdown_ui_pump():
    """退出/重新登录前取消弹幕队列轮询，并允许下一窗口重新初始化。"""
    global _ui_pump_started, _ui_after_id
    after_id = _ui_after_id
    _ui_after_id = None
    _ui_pump_started = False
    if after_id and ui.root is not None:
        try:
            ui.root.after_cancel(after_id)
        except (tk.TclError, ValueError):
            pass


def _collector_worker(options, generation):
    retry_delay = 2.0
    try:
        from danma.main import DanmuBrowserCollector
        while state.danmu_running and state.danmu_generation == generation:
            collector = DanmuBrowserCollector(
                platform=options["platform"],
                url=options["url"],
                headless=options["headless"],
                user_data_dir=options.get("user_data_dir") or None,
                chrome_path=options.get("chrome_path") or None,
                message_callback=enqueue_messages,
                log_fn=lambda msg: enqueue_messages({"type": "SystemMessage", "content": msg}),
            )
            with _lifecycle_lock:
                if state.danmu_generation != generation:
                    return
                state.danmu_collector = collector
            collector.browser_launch()
            with _lifecycle_lock:
                if state.danmu_collector is collector:
                    state.danmu_collector = None
            if not state.danmu_running or state.danmu_generation != generation:
                break
            enqueue_messages({
                "type": "SystemMessage",
                "content": f"采集器意外退出，{retry_delay:.0f} 秒后重连",
            })
            deadline = time.monotonic() + retry_delay
            while (
                state.danmu_running
                and state.danmu_generation == generation
                and time.monotonic() < deadline
            ):
                time.sleep(0.2)
            retry_delay = min(30.0, retry_delay * 2.0)
    except Exception as exc:
        enqueue_messages({"type": "SystemMessage", "content": f"启动失败：{exc}"})
        enqueue_messages({"type": "CollectorStatus", "status": "error", "content": "启动失败"})
    finally:
        with _lifecycle_lock:
            if state.danmu_generation == generation:
                state.danmu_running = False
                state.danmu_collector = None


def _read_options():
    cfg = config.load_config()
    platform_widget = getattr(ui, "cmb_danmu_platform", None)
    url_widget = getattr(ui, "ent_danmu_url", None)
    headless_var = getattr(ui, "var_danmu_headless", None)
    platform = str(
        platform_widget.get() if platform_widget is not None else cfg.get("danmu_platform") or "douyin"
    ).strip().lower()
    urls = cfg.get("danmu_urls") or {}
    ui_url = url_widget.get().strip() if url_widget is not None else ""
    url = str(ui_url or cfg.get("danmu_url") or urls.get(platform) or "").strip().strip("'\"")
    headless = bool(headless_var.get()) if headless_var is not None else bool(cfg.get("danmu_headless", True))
    return {
        "enabled": bool(cfg.get("danmu_enabled", True)),
        "platform": platform,
        "url": url,
        "headless": headless,
        "user_data_dir": str(cfg.get("danmu_user_data_dir") or "").strip(),
        "chrome_path": str(cfg.get("danmu_chrome_path") or "").strip(),
    }


def start_danmu_capture() -> bool:
    """随正式直播启动采集线程；返回是否成功发起。"""
    options = _read_options()
    if not options["enabled"]:
        ui.log_screen("【弹幕采集】配置为关闭，跳过启动。")
        _set_capture_ui("配置已关闭", "#fbbf24", False)
        return False
    if not options["url"]:
        ui.log_screen(f"【弹幕采集】❌ 平台 {options['platform']} 未配置直播间地址。")
        _set_capture_ui("未填写直播间", "#ff6b6b", False)
        return False
    if importlib.util.find_spec("playwright") is None:
        ui.log_screen("【弹幕采集】❌ 未安装 Playwright，请执行 pip install -r requirements.txt。")
        _set_capture_ui("缺少 Playwright", "#ff6b6b", False)
        return False

    initialize_ui_pump()
    with _lifecycle_lock:
        if state.danmu_running:
            return True
        state.danmu_generation += 1
        generation = state.danmu_generation
        state.danmu_running = True
        state.danmu_thread = threading.Thread(
            target=_collector_worker,
            args=(options, generation),
            name="danmu-collector",
            daemon=True,
        )
        state.danmu_thread.start()
    _set_capture_ui("启动中", "#22d3ee", True)
    mode = "无窗口(headless)" if options["headless"] else "可见浏览器"
    ui.log_screen(f"【弹幕采集】▶ {options['platform']}｜{mode}｜{options['url']}")
    return True


def stop_danmu_capture():
    """请求采集线程停止；Playwright 资源由其所属线程关闭。"""
    with _lifecycle_lock:
        collector = state.danmu_collector
        was_running = bool(state.danmu_running or collector is not None)
        if was_running:
            state.danmu_generation += 1
        state.danmu_running = False
    if collector is not None:
        collector.browser_close()
    if was_running:
        ui.log_screen("【弹幕采集】⏹ 已请求停止。")
    _set_capture_ui("已停止", "#9ca3af", False)


def toggle_danmu_capture():
    if state.danmu_running:
        stop_danmu_capture()
    else:
        start_danmu_capture()


# 兼容旧调用名；旧版外部 ws://127.0.0.1:8899 链路已移除。
def ws_danmu_loop():
    return start_danmu_capture()
