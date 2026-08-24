import os, sys, time, threading
import tkinter as tk
import tkinter.messagebox as messagebox

from core import state
from gui import ui
from device.input_text import send_text_to_doubao
from audio.vad import AudioPlaybackMonitor
from settings import config
from screen import capture

inner_audio_mode = False
can_next_speak = True
live_thread = None

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

    ok, msg = send_text_to_doubao(content, click_send=True)
    if not ok:
        ui.set_status("状态：❌预演下发失败", "#ff6b6b")
        ui.log_screen(f"【开播预演】❌失败: {msg}")
        messagebox.showerror("下发失败", f"话术未能发送到豆包对话：\n\n{msg}\n\n请确保手机已连接并停留在豆包对话界面。")
        return

    ui.set_status("状态：✅预演话术已发送到豆包", "#34d399")
    ui.log_screen("【开播预演】✅发送成功！")
    messagebox.showinfo("完成", "✅预演完成：话术已成功发送到豆包对话界面！")

def toggle_audio_mode():
    global inner_audio_mode
    inner_audio_mode = not inner_audio_mode
    if ui.btn_audio_mode:
        if inner_audio_mode:
            ui.btn_audio_mode.config(text="🔇内录模式(剪贴板)", bg="#333333", fg="white")
        else:
            ui.btn_audio_mode.config(text="🔊外音模式(TTS语音)", bg="#06d6a0", fg="black")

def send_script_content(text: str):
    global can_next_speak
    if not can_next_speak or not getattr(state, 'is_broadcasting', False):
        return

    can_next_speak = False
    ui.log_screen(f"【直播话术】正在发送: {text[:25]}...")
    ok, msg = send_text_to_doubao(text, click_send=True)

    if not ok:
        ui.set_status(f"❌话术发送失败: {msg[:20]}", "#ff6b6b")
        can_next_speak = True
        return

    threading.Thread(target=wait_next_round_worker, daemon=True).start()

def wait_next_round_worker():
    global can_next_speak
    cfg = config.load_config()
    interval_sec = int(cfg.get("script_interval", 15) or 15)

    audio_monitor = AudioPlaybackMonitor(silence_hold_sec=0.8)
    audio_monitor.wait_for_doubao_speech_cycle(max_wait_start_sec=4.0, max_speech_timeout_sec=45.0)

    count = interval_sec
    while count > 0 and getattr(state, 'is_broadcasting', False) and getattr(state, 'system_power', False):
        if ui.lab_count:
            ui.root.after(0, lambda c=count: ui.lab_count.config(text=f"⏱间隔：{c} 秒"))
        time.sleep(1)
        count -= 1

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
        except Exception:
            time.sleep(1)

def start_live():
    global live_thread, can_next_speak
    if not getattr(state, 'system_power', False):
        messagebox.showwarning("提示", "请先打开总电源！")
        return

    state.is_broadcasting = True
    can_next_speak = True

    if ui.btn_live_start:
        ui.btn_live_start.config(state=tk.DISABLED)
    if ui.btn_live_stop:
        ui.btn_live_stop.config(state=tk.NORMAL)

    ui.set_status("状态：直播运行｜顺序循环区间1‑2‑3", "#34d399")
    ui.log_screen("【直播控制】▶ 自动直播循环已启动！")

    capture.start_capture()
    live_thread = threading.Thread(target=auto_live_loop, daemon=True)
    live_thread.start()

def stop_live():
    state.is_broadcasting = False
    capture.stop_capture()

    if ui.btn_live_start:
        ui.btn_live_start.config(state=tk.NORMAL)
    if ui.btn_live_stop:
        ui.btn_live_stop.config(state=tk.DISABLED)

    ui.set_status("状态：待机【测试】✅", "#34d399")
    if ui.lab_count:
        ui.lab_count.config(text="✅可以执行下一轮")
    ui.log_screen("【直播控制】⏹ 自动直播已停止。")