# ====================== 直播控制 / 开播预演 / 话术发送 ======================
# 开播预演、区间话术循环发送、音频模式切换、倒计时节流、直播启停。
import threading
import time
import tkinter as tk
from core import state
from gui import ui
from settings import config
from device import input_text
from screen import danmu
from screen import capture
from core.paths import ADBKEYBOARD_APK


def run_pre_meet():
    """执行开播预演：内容完全取自界面开播预演文本框，不会发送电脑复制的代码。"""
    if not state.system_power:
        tk.messagebox.showwarning("提示", "请先打开总电源！")
        return
    content = ui.txt_pre_meet.get(1.0, tk.END).strip()
    if not content:
        tk.messagebox.showwarning("提示", "开播预演文本框不能为空！")
        return
    if state.scrcpy_hwnd == 0:
        tk.messagebox.showerror("错误", "scrcpy投屏窗口句柄无效，请确认投屏已经嵌入成功！")
        return

    ok, err = input_text.send_text_to_doubao(content)
    if not ok:
        ui.lab_sys_status.config(text="状态：❌预演下发失败", fg="#ff6b6b")
        tk.messagebox.showerror("下发失败",
                                f"话术未能发送到豆包对话：\n\n{err}\n\n"
                                f"提示：手机需安装 {ADBKEYBOARD_APK}（已在程序目录），\n"
                                "且豆包需停留在前台对话页。")
        return

    ui.lab_sys_status.config(text="状态：✅预演话术已发送（经发送验证）", fg="#34d399")
    tk.messagebox.showinfo("完成", "✅预演完成：话术已确认发送到豆包对话界面！")


def send_script_content(text):
    """直播话术发送（带节流锁）。"""
    with state.locker:
        if not state.can_next_speak:
            return
        state.can_next_speak = False
        if state.scrcpy_hwnd == 0:
            return
        ok, err = input_text.send_text_to_doubao(text)
        if not ok:
            ui.set_status("❌话术发送失败: " + err[:36], "#ff6b6b")
            state.can_next_speak = True
            return
        threading.Thread(target=count_down_work, daemon=True).start()


def toggle_audio_mode():
    """切换内录(剪贴板)/外音(TTS语音)模式。"""
    state.inner_audio_mode = not state.inner_audio_mode
    if state.inner_audio_mode:
        ui.btn_audio_mode.config(text="🔇内录模式(剪贴板)", bg="#333333", fg="white")
    else:
        ui.btn_audio_mode.config(text="🔊外音模式(TTS语音)", bg="#06d6a0", fg="black")


def count_down_work():
    """发送后倒计时，结束后解除发送节流。"""
    cfg = config.load_config()
    state.count_down_sec = int(cfg["script_interval"])
    while state.count_down_sec > 0 and state.live_running and state.system_power:
        ui.root.after(0, lambda t=state.count_down_sec: ui.lab_count.config(text=f"⏱间隔：{t} 秒"))
        time.sleep(1)
        state.count_down_sec -= 1
    state.can_next_speak = True
    ui.root.after(0, lambda: ui.lab_count.config(text="✅可以执行下一轮"))


def auto_live_loop():
    """自动直播循环：顺序读取区间1→2→3 内容发送。"""
    state.seq_index = 0
    while state.live_running and state.system_power:
        try:
            if state.can_next_speak:
                cfg = config.load_config()
                if state.seq_index == 0:
                    text = cfg["cmd1"]
                elif state.seq_index == 1:
                    text = cfg["cmd2"]
                else:
                    text = cfg["cmd3"]

                if text.strip():
                    send_script_content(text)

                state.seq_index = (state.seq_index + 1) % 3
            time.sleep(0.5)
        except Exception:
            pass


def start_live():
    """启动直播：开弹幕 WS、开话术循环、开抓屏。"""
    if not state.system_power:
        tk.messagebox.showwarning("提示", "请先打开总电源")
        return
    state.live_running = True
    state.seq_index = 0
    ui.btn_live_start.config(state=tk.DISABLED)
    ui.btn_live_stop.config(state=tk.NORMAL)
    ui.lab_sys_status.config(text="状态：直播运行｜顺序循环区间1‑2‑3", fg="#34d399")
    threading.Thread(target=danmu.ws_danmu_loop, daemon=True).start()
    threading.Thread(target=auto_live_loop, daemon=True).start()
    capture.start_capture()


def stop_live():
    """停止直播。"""
    state.live_running = False
    capture.stop_capture()
    ui.btn_live_start.config(state=tk.NORMAL)
    ui.btn_live_stop.config(state=tk.DISABLED)
    ui.lab_sys_status.config(text="状态：待机【测试】✅", fg="#34d399")
    ui.lab_count.config(text="✅可以执行下一轮")
