import os, sys, time, threading
import tkinter as tk
import tkinter.messagebox as messagebox

from core import state
from gui import ui
from device.input_text import send_text_to_doubao
from audio.vad import (
    AudioPlaybackMonitor,
    VAD_AUDIO_ERROR,
    VAD_CANCELLED,
    VAD_ENDED,
    VAD_START_TIMEOUT,
    VAD_UNAVAILABLE,
)
from settings import config
from screen import capture, danmu

inner_audio_mode = False
can_next_speak = True
live_thread = None
_live_generation = 0
_vad_stop_event = None
_current_monitor = None
_round_lock = threading.Lock()


def build_doubao_host_prompt(content: str) -> str:
    """给每次豆包请求统一添加主播角色及纯口播约束。"""
    content = str(content or "").strip()
    host_prompt = str(
        config.load_config().get("doubao_host_prompt")
        or config.DEFAULT_CFG["doubao_host_prompt"]
    ).strip()
    return "%s\n\n本次直播话术要求：%s" % (host_prompt, content)


def _read_vad_config():
    cfg = config.load_config()
    return {
        "silence_hold": max(0.5, float(cfg.get("vad_silence_hold_sec", 2.0) or 2.0)),
        "wait_start": max(3.0, float(cfg.get("vad_wait_start_sec", 15.0) or 15.0)),
        "speak_confirm": max(0.1, float(cfg.get("vad_speak_confirm_sec", 0.3) or 0.3)),
        "energy_threshold": float(cfg.get("vad_energy_threshold_db", -42.0) or -42.0),
        "noise_margin": max(3.0, float(cfg.get("vad_noise_margin_db", 6.0) or 6.0)),
        "end_hysteresis": max(1.0, float(cfg.get("vad_end_hysteresis_db", 3.0) or 3.0)),
        "calibration": max(0.3, float(cfg.get("vad_calibration_sec", 0.8) or 0.8)),
        "calibration_wait": max(1.0, float(cfg.get("vad_calibration_wait_sec", 6.0) or 6.0)),
    }


def _halt_live_from_worker(message, status_text="VAD 音频异常"):
    """音频链路失效时安全停播，禁止继续盲发话术。"""
    global can_next_speak
    state.is_broadcasting = False
    can_next_speak = False
    ui.log_screen(message)
    ui.set_status("状态：❌%s，直播已停止" % status_text, "#ff6b6b")

    def _update_controls():
        capture.stop_capture()
        if ui.btn_live_start:
            ui.btn_live_start.config(state=tk.NORMAL)
        if ui.btn_live_stop:
            ui.btn_live_stop.config(state=tk.DISABLED)
        if ui.lab_count:
            ui.lab_count.config(text="❌%s，已停止" % status_text)

    if ui.root:
        ui.root.after(0, _update_controls)


def cancel_active_vad():
    """供停止直播、关机和关闭窗口调用。"""
    global _live_generation, _vad_stop_event
    with _round_lock:
        _live_generation += 1
        if _vad_stop_event:
            _vad_stop_event.set()

def run_pre_meet():
    """【执行开播预演】"""
    if not getattr(state, 'system_power', False):
        messagebox.showwarning("提示", "请先打开总电源（点击右上角红色电源按钮）！")
        return

    content = ""
    if ui.txt_pre_meet:
        content = ui.txt_pre_meet.get(1.0, tk.END).strip()

    if not content:
        messagebox.showwarning("提示", "开播预演文本框不能为空，请输入要预演的话术！")
        return

    ui.set_status("状态：⏳正在向豆包下发预演话术...", "#00e5ff")
    ui.log_screen(f"【开播预演】正在下发: {content[:30]}...")

    ok, msg = send_text_to_doubao(build_doubao_host_prompt(content), click_send=True)
    if not ok:
        ui.set_status("状态：❌预演下发失败", "#ff6b6b")
        ui.log_screen(f"【开播预演】❌失败: {msg}")
        messagebox.showerror("下发失败", f"话术未能发送到豆包对话：\n\n{msg}\n\n请确保手机已连接并停留在豆包对话界面。")
        return

    ui.set_status("状态：✅预演话术已发送到豆包", "#34d399")
    ui.log_screen("【开播预演】✅发送成功！(预演为单次演示：不倒计时、不触发 VAD；点「正式开播」才用 VAD 静音检测切话术)")
    if ui.lab_count:
        ui.root.after(0, lambda: ui.lab_count.config(text="✅预演完成(可点正式开播)"))

def toggle_audio_mode():
    global inner_audio_mode
    inner_audio_mode = not inner_audio_mode
    if ui.btn_audio_mode:
        if inner_audio_mode:
            ui.btn_audio_mode.config(text="🔇内录模式(剪贴板)", bg="#333333", fg="white")
        else:
            ui.btn_audio_mode.config(text="🔊外音模式(TTS语音)", bg="#06d6a0", fg="black")

def send_script_content(text: str):
    global can_next_speak, _current_monitor
    if not can_next_speak or not getattr(state, 'is_broadcasting', False):
        return

    try:
        vad_cfg = _read_vad_config()
    except (TypeError, ValueError) as exc:
        _halt_live_from_worker("【VAD】❌ VAD 配置不是有效数字：%s" % exc)
        return
    can_next_speak = False
    with _round_lock:
        generation = _live_generation
        stop_event = _vad_stop_event

    # 关键时序：先打开并校准音频，再发送消息。这样豆包开口的第一帧不会在
    # PyAudio 初始化或“发送后基线采样”期间被丢掉。
    ui.reset_volume_meter()
    ui.log_screen("【VAD】发送前准备音频设备并测量静音基线...")
    monitor = AudioPlaybackMonitor(
        energy_threshold_db=vad_cfg["energy_threshold"],
        silence_hold_sec=vad_cfg["silence_hold"],
        speak_confirm_sec=vad_cfg["speak_confirm"],
        noise_margin_db=vad_cfg["noise_margin"],
        end_hysteresis_db=vad_cfg["end_hysteresis"],
        log_fn=ui.log_screen,
        on_level=ui.set_volume_meter,
    )
    with _round_lock:
        if generation != _live_generation or (stop_event and stop_event.is_set()):
            monitor.close()
            return
        _current_monitor = monitor
    if not monitor.is_ready or not monitor.calibrate_idle(
        vad_cfg["calibration"], stop_event, vad_cfg["calibration_wait"]
    ):
        monitor.close()
        with _round_lock:
            if _current_monitor is monitor:
                _current_monitor = None
        if stop_event and stop_event.is_set():
            return
        _halt_live_from_worker("【VAD】❌ 音频设备未就绪或静音基线异常，已停止自动直播。")
        return

    # 实体麦克风模式会把结束确认窗口自动提高到至少 8 秒；让工作线程的提示
    # 与状态机实际使用值一致。
    vad_cfg = dict(vad_cfg)
    vad_cfg["silence_hold"] = monitor.active_silence_hold_sec

    ui.log_screen(f"【直播话术】正在发送: {text[:25]}...")
    ok, msg = send_text_to_doubao(build_doubao_host_prompt(text), click_send=True)

    if not ok:
        monitor.close()
        with _round_lock:
            if _current_monitor is monitor:
                _current_monitor = None
        ui.set_status(f"❌话术发送失败: {msg[:20]}", "#ff6b6b")
        can_next_speak = True
        return

    threading.Thread(
        target=wait_next_round_worker,
        args=(monitor, generation, stop_event, vad_cfg),
        daemon=True,
    ).start()

def wait_next_round_worker(audio_monitor, generation, stop_event, vad_cfg):
    global can_next_speak, _current_monitor
    ui.log_screen(
        "【VAD】本轮持续监听：思考等待≤%.0fs；检测到开口后，连续静音 %.1fs 才切换。"
        % (vad_cfg["wait_start"], vad_cfg["silence_hold"])
    )
    try:
        result = audio_monitor.wait_for_doubao_speech_cycle(
            max_wait_start_sec=vad_cfg["wait_start"],
            stop_event=stop_event,
        )
    except Exception as exc:
        audio_monitor.close()
        ui.log_screen("【VAD】❌ 状态机异常：%s" % exc)
        result = VAD_AUDIO_ERROR
    with _round_lock:
        if _current_monitor is audio_monitor:
            _current_monitor = None
        stale = generation != _live_generation
    ui.reset_volume_meter()
    if stale or result == VAD_CANCELLED or (stop_event and stop_event.is_set()):
        return
    if result in (VAD_UNAVAILABLE, VAD_AUDIO_ERROR):
        _halt_live_from_worker(
            "【VAD】❌ 音频采集设备不可用或读取中断，已停止自动直播，未放行下一句。",
            "VAD 音频采集失败",
        )
        return
    if result == VAD_ENDED:
        ui.log_screen("【VAD】✅ 确认豆包已停止播放，切换到下一条话术。")
    elif result == VAD_START_TIMEOUT:
        _halt_live_from_worker(
            "【VAD】❌ 等待开口超时：无法确认豆包是否正在播放，"
            "已停止自动直播并禁止切换下一句。请检查音频采集设备和音量。",
            "等待豆包开口超时",
        )
        return
    can_next_speak = True
    if ui.lab_count:
        ui.root.after(0, lambda: ui.lab_count.config(text="✅可以执行下一轮"))

def auto_live_loop():
    global can_next_speak
    seq_index = 0
    while getattr(state, 'is_broadcasting', False) and getattr(state, 'system_power', False):
        try:
            if can_next_speak:
                cfg = config.load_config()
                if seq_index == 0:
                    text = cfg.get("cmd1", "")
                elif seq_index == 1:
                    text = cfg.get("cmd2", "")
                else:
                    text = cfg.get("cmd3", "")

                if text and text.strip():
                    send_script_content(text.strip())

                seq_index = (seq_index + 1) % 3
            time.sleep(0.5)
        except Exception as exc:
            ui.log_screen("【直播循环】异常：%s" % exc)
            time.sleep(1)

def start_live():
    global live_thread, can_next_speak, _live_generation, _vad_stop_event
    if not getattr(state, 'system_power', False):
        messagebox.showwarning("提示", "请先打开总电源！")
        return

    if getattr(state, 'is_broadcasting', False):
        return
    with _round_lock:
        _live_generation += 1
        _vad_stop_event = threading.Event()
    AudioPlaybackMonitor.reset_session_baseline()
    state.is_broadcasting = True
    state.live_running = True
    can_next_speak = True

    if ui.btn_live_start:
        ui.btn_live_start.config(state=tk.DISABLED)
    if ui.btn_live_stop:
        ui.btn_live_stop.config(state=tk.NORMAL)

    ui.set_status("状态：直播运行｜顺序循环区间1‑2‑3", "#34d399")
    ui.log_screen("【直播控制】▶ 自动直播循环已启动！")

    ui.reset_volume_meter()
    danmu.start_danmu_capture()
    capture.start_capture()
    live_thread = threading.Thread(target=auto_live_loop, daemon=True)
    live_thread.start()

def stop_live():
    cancel_active_vad()
    state.is_broadcasting = False
    state.live_running = False
    danmu.stop_danmu_capture()
    capture.stop_capture()

    if ui.btn_live_start:
        ui.btn_live_start.config(state=tk.NORMAL)
    if ui.btn_live_stop:
        ui.btn_live_stop.config(state=tk.DISABLED)

    ui.set_status("状态：待机【测试】✅", "#34d399")
    if ui.lab_count:
        ui.lab_count.config(text="✅可以执行下一轮")
    ui.log_screen("【直播控制】⏹ 自动直播已停止。")
