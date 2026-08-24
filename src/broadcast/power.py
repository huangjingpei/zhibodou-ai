# ====================== 总电源开关 + 开机自检 ======================
# 打开/关闭系统总电源，开机时做 adb 设备 / 豆包前台 / ADBKeyboard 安装自检。
import threading
import tkinter as tk
import tkinter.messagebox as messagebox
import winsound
from core import state
from gui import ui
from device import adb_utils
from device import input_text
from screen import scrcpy_embed
from screen import capture
from settings import auth
from core.paths import ADBKEYBOARD_APK
from device import doubao_check


def power_on_self_check():
    """开机自检：豆包已安装/就绪(前台+对话界面+无遮挡+可发送) / ADBKeyboard。
    返回问题列表（空=全部通过）。离线(无 adb)时只给手动模式提示，不阻断开机。"""
    problems = []
    # 豆包整体体检（含设备在线 / 是否已装 / 前台 / 对话界面 / 无遮挡 / 可发送）
    _ok, dp, mode = doubao_check.check_doubao_ready()
    problems.extend(dp)
    # ADBKeyboard 输入法：豆包文本直输主通道（Android 10+ 剪贴板方案已失效）
    if mode == "online":
        if not input_text.check_adbkeyboard_installed():
            problems.append("⚠️ 手机未安装 ADBKeyboard：话术将无法输入豆包！\n"
                            "   （Android 10+ 禁止后台写剪贴板，clipper 方案已失效。\n"
                            f"    请用 adb install {ADBKEYBOARD_APK} 安装，程序目录已附带）")
        elif input_text.ADB_IME_ID not in input_text._ime_current():
            problems.append("ℹ️ ADBKeyboard 已安装但不是当前输入法（程序会在发送时自动临时切换）")
    return problems


def startup_readiness_check(log=True):
    """程序启动时一次性体检：豆包是否就绪。返回 (ok, problems, mode)。
    若 log=True，把结果写到屏幕日志并刷新状态栏（线程安全）。
    mode='offline' 时程序仍可运行，仅提示需人工确认并手动操作。"""
    try:
        ok, problems, mode = doubao_check.check_doubao_ready()
    except Exception as e:
        ok, problems, mode = False, ["⚠️ 豆包就绪检测异常：" + str(e)], "offline"
    if log:
        if ok:
            ui.set_status("✅ 豆包就绪：前台/对话界面/无遮挡/可发送", "#34d399")
            ui.log_screen("【启动自检】豆包就绪 ✅ 可正常发送聊天")
        elif mode == "offline":
            ui.set_status("🟡 手动模式（无 adb）：请人工确认豆包状态", "#f59e0b")
            ui.log_screen("【启动自检】未检测到 adb，进入手动模式：")
            for p in problems:
                ui.log_screen("  " + p)
        else:
            ui.set_status("⚠️ 豆包未就绪，请按启动自检提示处理", "#f59e0b")
            ui.log_screen("【启动自检】发现问题：")
            for p in problems:
                ui.log_screen("  " + p)
    return ok, problems, mode


def toggle_power():
    """总电源开关。"""
    if auth.check_cannot_power_on():
        messagebox.showerror("禁止开机", "授权异常，无法启动系统")
        return
    if not state.system_power:
        state.system_power = True
        # 开机自检：设备/豆包前台/clipper，问题当场暴露
        problems = power_on_self_check()
        if problems:
            messagebox.showwarning("开机自检发现问题", "\n\n".join(problems))
        ui.btn_power.config(bg="#00aa44")
        winsound.Beep(1000, 120)
        ui.lab_sys_status.config(text="状态：待机【测试】✅", fg="#34d399")
        ui.btn_meet.config(state=tk.NORMAL)
        ui.btn_live_start.config(state=tk.NORMAL)
        ui.btn_audio_mode.config(state=tk.NORMAL)
        ui.btn_cap.config(state=tk.NORMAL)
        scrcpy_embed.start_scrcpy_embed()
        threading.Thread(target=scrcpy_embed.lock_scrcpy_loop, daemon=True).start()
    else:
        state.system_power = False
        state.live_running = False
        state.screenshot_working = False
        scrcpy_embed.stop_scrcpy_embed()
        capture.stop_capture()
        ui.btn_power.config(bg="#bb2222")
        winsound.Beep(600, 120)
        ui.lab_sys_status.config(text="状态：已关机 ❌", fg="#ef4444")
        ui.btn_meet.config(state=tk.DISABLED)
        ui.btn_live_start.config(state=tk.DISABLED)
        ui.btn_live_stop.config(state=tk.DISABLED)
        ui.btn_audio_mode.config(state=tk.DISABLED)
        ui.btn_cap.config(state=tk.DISABLED)
        ui.txt_danmu.delete(1.0, tk.END)
        ui.txt_screen_log.delete(1.0, tk.END)
