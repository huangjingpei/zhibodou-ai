# ====================== scrcpy 自动启动 / 嵌入 / 锁死窗口 ======================
# 把 scrcpy.exe 作为子进程拉起，把它的窗口嵌进 GUI 容器，并循环锁死样式与尺寸。
import os
import subprocess
import threading
import time
import tkinter.messagebox as messagebox
from core import state
from gui import ui
from screen import win_embed
from core.paths import SCRCPY_EXE, SCRCPY_DIR


def start_scrcpy_embed():
    """启动 scrcpy 子进程并尝试把窗口嵌入 embed_container。"""
    if state.scrcpy_process is not None:
        return
    if not os.path.exists(SCRCPY_EXE):
        messagebox.showerror("文件缺失", f"找不到scrcpy.exe\n{SCRCPY_EXE}")
        return

    state.scrcpy_process = subprocess.Popen([
        SCRCPY_EXE,
        "--window-title", "scrcpy",
        "--max-size", "620"
    ], cwd=SCRCPY_DIR)

    def embed_work():
        parent_hwnd = win_embed.get_tk_widget_hwnd(ui.embed_container)
        max_wait_sec = 8
        spent = 0
        state.scrcpy_hwnd = 0
        while spent < max_wait_sec:
            state.scrcpy_hwnd = win_embed.find_scrcpy_main_hwnd()
            if state.scrcpy_hwnd != 0:
                break
            time.sleep(0.35)
            spent += 0.35
        if state.scrcpy_hwnd and parent_hwnd:
            win_embed.real_embed_window(state.scrcpy_hwnd, parent_hwnd, 0, 0, 290, 530)

    threading.Thread(target=embed_work, daemon=True).start()


def lock_scrcpy_loop():
    """持续锁死 scrcpy 窗口样式（去边框/透明）与尺寸，防止被拖动。"""
    parent_hwnd = win_embed.get_tk_widget_hwnd(ui.embed_container)
    while state.system_power and state.scrcpy_hwnd != 0:
        try:
            style = win_embed.user32.GetWindowLongW(state.scrcpy_hwnd, win_embed.GWL_STYLE)
            style = style & (~win_embed.WS_CAPTION) & (~win_embed.WS_THICKFRAME) & (~win_embed.WS_SYSMENU)
            win_embed.user32.SetWindowLongW(state.scrcpy_hwnd, win_embed.GWL_STYLE, style)
            ex_style = win_embed.user32.GetWindowLongW(state.scrcpy_hwnd, win_embed.GWL_EXSTYLE)
            ex_style = ex_style | win_embed.WS_EX_TRANSPARENT
            win_embed.user32.SetWindowLongW(state.scrcpy_hwnd, win_embed.GWL_EXSTYLE, ex_style)
            win_embed.user32.MoveWindow(state.scrcpy_hwnd, 0, 0, 290, 530, True)
        except Exception:
            pass
        time.sleep(0.15)


def stop_scrcpy_embed():
    """终止 scrcpy 子进程并复位状态。"""
    if state.scrcpy_process:
        try:
            state.scrcpy_process.terminate()
        except Exception:
            pass
        state.scrcpy_process = None
    state.scrcpy_hwnd = 0
