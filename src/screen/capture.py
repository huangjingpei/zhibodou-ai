# ====================== 截图抓屏模块 ======================
# 定时截取电脑屏幕（用于核验投屏画面），结果写入消息队列并由 UI 定时刷新。
import threading
import time
import tkinter as tk
import pyautogui
from core import state
from gui import theme, ui
def screen_capture_loop():
    """抓屏循环：每秒截一次，写入消息队列。"""
    while state.screenshot_working and state.system_power:
        try:
            pyautogui.screenshot()
            t = time.strftime("%H:%M:%S")
            state.msg_queue.put(f"[{t}] 抓取画面完成\n")
            time.sleep(1.0)
        except Exception:
            time.sleep(1)


def ui_refresh_msg():
    """从消息队列刷新抓屏日志（由 root.after 周期调用）。"""
    while not state.msg_queue.empty():
        s = state.msg_queue.get()
        ui.txt_screen_log.insert(tk.END, s)
        ui.txt_screen_log.see(tk.END)
    if state.screenshot_working:
        ui.root.after(200, ui_refresh_msg)


def start_capture():
    """开启抓屏。"""
    if not state.system_power:
        tk.messagebox.showwarning("提示", "请先打开总电源！")
        return
    if state.screenshot_working:
        return
    state.screenshot_working = True
    threading.Thread(target=screen_capture_loop, daemon=True).start()
    ui.root.after(100, ui_refresh_msg)
    ui.lab_cap_status.config(text="抓屏 · 运行中", fg=theme.GREEN)


def stop_capture():
    """停止抓屏并清空日志。"""
    state.screenshot_working = False
    ui.lab_cap_status.config(text="抓屏 · 已停止", fg=theme.AMBER)
    ui.txt_screen_log.delete(1.0, tk.END)
