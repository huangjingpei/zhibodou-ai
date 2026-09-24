"""智播豆主控台界面。

业务模块通过本文件暴露的模块级控件更新状态；本文件只负责表现层和线程安全的
UI 刷新，不绑定业务 command。视觉规范集中在 :mod:`gui.theme`。
"""

import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from gui import theme
from settings import config


# ---- 控件引用（build_ui 中赋值，供现有业务模块读写） -------------------------
root = None
lab_sys_status = None
lab_online = None
lab_like = None
lab_gift = None
lab_cap_status = None
lab_count = None
lab_danmu_status = None
lab_auth_status = None
lab_auth_detail = None
volume_canvas = None
lab_vad_state = None
embed_container = None
txt_danmu = None
txt_screen_log = None
txt_pre_meet = None
btn_power = None
btn_meet = None
btn_logout = None
btn_live_start = None
btn_live_stop = None
btn_cap = None
btn_pwd = None
btn_auth = None
btn_settings = None
btn_logs = None
btn_save = None
btn_danmu = None
ent_danmu_url = None
cmb_doubao_lang = None
ent_prod_name = None
ent_prod_desc = None

# StreamGet & OBS 串流联动控件引用
ent_stream_input = None
cmb_stream_quality = None
cmb_stream_format = None
ent_stream_url = None
chk_auto_obs = None
var_auto_obs = None
btn_parse_stream = None
btn_sync_obs = None
lab_stream_meta = None
lab_obs_sync_status = None

# 内存日志缓冲区
_log_history: list = []


def get_log_history() -> str:
    """获取系统运行以来的完整日志历史文本。"""
    return "".join(_log_history)


class DanmuTextAdapter:
    """弹幕文本兼容适配器（主界面精简弹幕框后，确保原有调用保持静默安全）。"""
    def insert(self, *a, **k):
        pass
    def see(self, *a, **k):
        pass
    def delete(self, *a, **k):
        pass
    def index(self, *a, **k):
        return "1.0"


class TextLogAdapter:
    """运行日志兼容适配器（同步对接独立运行日志弹窗与内存缓冲区）。"""
    def insert(self, pos, text=""):
        global _log_history
        s = str(text)
        _log_history.append(s)
        if len(_log_history) > 2000:
            del _log_history[:500]
        try:
            from gui.log_dialog import get_active_log_dialog
            dlg = get_active_log_dialog()
            if dlg:
                dlg.append_log(s)
        except Exception:
            pass

    def see(self, *a, **k):
        pass

    def delete(self, *a, **k):
        global _log_history
        _log_history.clear()
        try:
            from gui.log_dialog import get_active_log_dialog
            dlg = get_active_log_dialog()
            if dlg:
                dlg._clear_logs()
        except Exception:
            pass

    def index(self, *a, **k):
        return f"{len(_log_history)}.0"

    def get(self, *a, **k):
        return "".join(_log_history)


class ScriptFileAdapter:
    def __init__(self, key: str):
        self.key = key
    def get(self, *a, **k):
        try:
            from broadcast.script_files import read_script_content
            return read_script_content(self.key)
        except Exception:
            return ""
    def insert(self, *a, **k):
        pass
    def delete(self, *a, **k):
        pass


class DummyEntry:
    def __init__(self, val="0"):
        self.val = str(val)
    def get(self, *a, **k):
        return self.val
    def insert(self, *a, **k):
        pass
    def delete(self, *a, **k):
        pass


ent_r1min = None
ent_r1max = None
ent_cmd1 = ScriptFileAdapter("01")
ent_r2min = None
ent_r2max = None
ent_cmd2 = ScriptFileAdapter("02")
ent_r3min = None
ent_r3max = None
ent_cmd3 = ScriptFileAdapter("03")
ent_interval = DummyEntry("0")

btn_open_txt1 = None
btn_open_txt2 = None
btn_open_txt3 = None
lab_txt1_info = None
lab_txt2_info = None
lab_txt3_info = None
lab_txt1_preview = None
lab_txt2_preview = None
lab_txt3_preview = None
btn_close_notepads = None

cmb_danmu_mode = None
ent_deepseek_key = None
chk_ai_reply = None
var_ai_reply = None
lbl_obs_link = None



# VAD 每秒约 50 帧；工作线程只覆盖最新值，由 Tk 主线程以 20 FPS 合并绘制。
_volume_lock = threading.Lock()
_volume_latest = None
_volume_peak_db = -100.0
_volume_poll_started = False
_volume_after_id = None
_shutting_down = False


def is_shutting_down() -> bool:
    return _shutting_down


def begin_shutdown():
    """停止 UI 调度并取消当前 Tk 根窗口的全部 after/idle 回调。"""
    global _shutting_down, _volume_poll_started, _volume_after_id, _volume_latest
    _shutting_down = True
    _volume_poll_started = False
    _volume_after_id = None
    with _volume_lock:
        _volume_latest = None
    current_root = root
    if current_root is None:
        return
    try:
        pending = current_root.tk.call("after", "info")
        if isinstance(pending, str):
            pending = (pending,)
        for after_id in tuple(pending or ()):
            try:
                current_root.after_cancel(after_id)
            except (tk.TclError, ValueError):
                pass
    except tk.TclError:
        pass


def set_status(msg, color=theme.RED):
    """线程安全更新主界面状态；GUI 未就绪时退化为控制台日志。"""
    if _shutting_down:
        return
    try:
        root.after(0, lambda: lab_sys_status.config(text=msg, fg=color))
    except Exception:
        print("[状态]", msg)


def log_screen(msg):
    """线程安全追加运行日志，并同步回显到控制台与独立日志查看器。"""
    if _shutting_down:
        return
    text = str(msg)
    try:
        print(text)
    except Exception:
        pass
    _log_history.append(text + "\n")
    if len(_log_history) > 2000:
        del _log_history[:500]
    try:
        from gui.log_dialog import get_active_log_dialog
        dlg = get_active_log_dialog()
        if dlg and root is not None:
            root.after(0, lambda: dlg.append_log(text))
    except Exception:
        pass
    if txt_screen_log is not None and root is not None:
        try:
            def _do():
                txt_screen_log.insert(tk.END, text + "\n")
                txt_screen_log.see(tk.END)
            root.after(0, _do)
        except Exception:
            pass


def set_volume_meter(db, avg=None, speaking=False, silence_elapsed=None,
                     silence_hold=None, phase="monitor"):
    """保存最新 VAD 帧；实际绘制在 Tk 主线程完成。"""
    global _volume_latest
    if _shutting_down:
        return
    try:
        payload = {
            "db": float(db),
            "avg": float(avg) if avg is not None else float(db),
            "speaking": bool(speaking),
            "silence_elapsed": silence_elapsed,
            "silence_hold": silence_hold,
            "phase": phase,
        }
        with _volume_lock:
            # CABLE 的有效 PCM 可能只持续一个 20ms 帧，而 UI 每 50ms 刷新一次。
            # 若直接覆盖“最新值”，强音频帧会被紧随其后的 -100dB 空帧抹掉，
            # 状态机已经听到声音但界面仍显示静音。合并刷新周期内的峰值即可避免。
            previous = _volume_latest if isinstance(_volume_latest, dict) else None
            if previous and previous.get("phase") == payload["phase"]:
                payload["db"] = max(previous["db"], payload["db"])
                payload["avg"] = max(previous["avg"], payload["avg"])
                payload["speaking"] = previous["speaking"] or payload["speaking"]
            _volume_latest = payload
    except (TypeError, ValueError):
        return


def _draw_meter_fill(width, color):
    canvas_w = max(1, volume_canvas.winfo_width())
    canvas_h = max(1, volume_canvas.winfo_height())
    volume_canvas.create_rectangle(0, 0, canvas_w, canvas_h,
                                   fill=theme.SURFACE_SOFT, outline="")
    if width > 0:
        volume_canvas.create_rectangle(0, 0, min(width, canvas_w), canvas_h,
                                       fill=color, outline="")
    for ratio in (0.25, 0.5, 0.75):
        x = int(canvas_w * ratio)
        volume_canvas.create_line(x, 3, x, canvas_h - 3, fill=theme.BORDER)


def _poll_volume_meter():
    """合并 VAD 帧，并用峰值缓降让短语音清晰可见。"""
    global _volume_latest, _volume_peak_db, _volume_after_id
    if _shutting_down:
        _volume_after_id = None
        return
    try:
        with _volume_lock:
            payload = _volume_latest
            _volume_latest = None

        if payload == "reset":
            _volume_peak_db = -100.0
            volume_canvas.delete("all")
            _draw_meter_fill(0, theme.TEXT_FAINT)
            lab_vad_state.config(text="待机 · 等待音频", fg=theme.TEXT_MUTED)
        elif payload:
            db = payload["db"]
            avg = payload["avg"]
            target_db = max(db, avg)
            if target_db >= _volume_peak_db:
                _volume_peak_db = target_db
            else:
                _volume_peak_db = max(target_db, _volume_peak_db - 3.0)
            shown_db = max(avg, _volume_peak_db)
            level = max(0.0, min(1.0, (shown_db + 70.0) / 60.0))
            width = int(max(1, volume_canvas.winfo_width()) * level)

            volume_canvas.delete("all")
            if payload["phase"] == "calibrating":
                _draw_meter_fill(width, theme.PURPLE)
                lab_vad_state.config(text="校准底噪  %.0f dB" % shown_db, fg=theme.PURPLE)
            elif payload["phase"] == "speaking":
                if payload["speaking"]:
                    _draw_meter_fill(width, theme.GREEN)
                    lab_vad_state.config(text="豆包播放中  %.0f dB" % shown_db, fg=theme.GREEN)
                elif payload["silence_elapsed"] is not None and payload["silence_hold"] is not None:
                    _draw_meter_fill(width, theme.AMBER)
                    lab_vad_state.config(
                        text="静音确认  %.1f / %.1f s"
                        % (payload["silence_elapsed"], payload["silence_hold"]),
                        fg=theme.AMBER,
                    )
                else:
                    _draw_meter_fill(width, theme.TEXT_FAINT)
                    lab_vad_state.config(text="持续监听中", fg=theme.TEXT_MUTED)
            else:
                _draw_meter_fill(width, theme.CYAN)
                lab_vad_state.config(text="等待豆包开口  %.0f dB" % shown_db, fg=theme.CYAN)
    except (tk.TclError, AttributeError) as exc:
        print("[Client-VAD] 音量表刷新失败:", exc)
    finally:
        try:
            if not _shutting_down and root and root.winfo_exists():
                _volume_after_id = root.after(50, _poll_volume_meter)
        except tk.TclError:
            pass


def reset_volume_meter():
    global _volume_latest
    if _shutting_down:
        return
    with _volume_lock:
        _volume_latest = "reset"


def _section_label(parent, text, row, column, **grid):
    widget = theme.label(parent, text, fg=theme.TEXT_MUTED, font_size=9, bold=True, anchor="w")
    widget.grid(row=row, column=column, **grid)
    return widget


def _configure_text(widget):
    widget.configure(
        bg=theme.SURFACE_ALT, fg=theme.TEXT_SOFT, insertbackground=theme.CYAN,
        selectbackground=theme.PRIMARY, selectforeground="#FFFFFF",
        relief=tk.FLAT, bd=0, highlightthickness=1,
        highlightbackground=theme.BORDER, highlightcolor=theme.BORDER_FOCUS,
        font=theme.font(9), padx=8, pady=6,
    )


def build_ui():
    """构建统一深色品牌主控台，并回填业务配置。"""
    global root, lab_sys_status, lab_online, lab_like, lab_gift, lab_cap_status
    global lab_count, lab_danmu_status, lab_auth_status, lab_auth_detail
    global embed_container, txt_danmu, txt_screen_log, txt_pre_meet
    global btn_power, btn_meet, btn_live_start, btn_live_stop, btn_cap
    global btn_pwd, btn_auth, btn_settings, btn_logs, btn_save, btn_danmu, btn_logout
    global ent_danmu_url, cmb_doubao_lang
    global volume_canvas, lab_vad_state, _volume_poll_started, _volume_after_id, _shutting_down
    global ent_prod_name, ent_prod_desc, ent_r1min, ent_r1max, ent_cmd1
    global ent_r2min, ent_r2max, ent_cmd2, ent_r3min, ent_r3max, ent_cmd3, ent_interval
    global ent_deepseek_key, var_ai_reply, cmb_danmu_mode
    global btn_open_txt1, btn_open_txt2, btn_open_txt3, lab_txt1_info, lab_txt2_info, lab_txt3_info
    global lab_txt1_preview, lab_txt2_preview, lab_txt3_preview
    global btn_close_notepads, lbl_obs_link
    global ent_stream_input, cmb_stream_quality, cmb_stream_format, ent_stream_url
    global chk_auto_obs, var_auto_obs, btn_parse_stream, btn_sync_obs, lab_stream_meta, lab_obs_sync_status

    _shutting_down = False
    _volume_poll_started = False
    _volume_after_id = None
    root = tk.Tk()
    root.title("智播豆 · AI 智能直播工作台")
    root.geometry("1280x820")
    root.minsize(1180, 760)
    root.configure(bg=theme.BG)
    theme.configure_ttk(root)

    # ---------------- 顶部品牌 Header ----------------
    header = tk.Canvas(root, height=52, bg=theme.BG, bd=0, highlightthickness=0)
    header.pack(fill=tk.X)
    header.pack_propagate(False)

    def _paint_header(event):
        w, h = event.width, event.height
        theme.draw_horizontal_gradient(header, w, h, "#10192A", "#14243B")
        header.delete("header-fg")
        header.create_oval(20, 11, 48, 39, outline=theme.CYAN, width=2, tags="header-fg")
        header.create_text(34, 25, text="ZD", fill=theme.TEXT,
                           font=theme.font_en(10, "bold"), tags="header-fg")
        header.create_text(62, 19, text="智播豆  ·  AI 智能直播工作台",
                           fill=theme.TEXT, anchor="w", font=theme.font(theme.FS_DISPLAY, "bold"), tags="header-fg")
        header.create_text(63, 36, text="ZHIBODOU LIVE OPERATIONS CONSOLE",
                           fill=theme.TEXT_MUTED, anchor="w", font=theme.font_en(theme.FS_CAPTION), tags="header-fg")
        header.create_text(w - 20, 25, text="DESKTOP  v1.7.0",
                           fill=theme.TEXT_MUTED, anchor="e", font=theme.font_en(theme.FS_CAPTION, "bold"), tags="header-fg")

    header.bind("<Configure>", _paint_header)

    # ---------------- PDK 授权状态条 ----------------
    auth_outer = tk.Frame(root, bg=theme.BORDER)
    auth_outer.pack(fill=tk.X, padx=14, pady=(6, 4))
    auth_frame = tk.Frame(auth_outer, bg=theme.SURFACE, height=42)
    auth_frame.pack(fill=tk.X, padx=1, pady=1)
    auth_frame.pack_propagate(False)

    try:
        from pdk import auth_service as pdk_auth
        auth_result = pdk_auth.current_auth()
    except Exception:
        auth_result = None
    auth_ok = auth_result is not None

    status_dot = tk.Canvas(auth_frame, width=16, height=16, bg=theme.SURFACE,
                           bd=0, highlightthickness=0)
    status_dot.pack(side=tk.LEFT, padx=(14, 6))
    status_dot.create_oval(3, 3, 13, 13, fill=theme.GREEN if auth_ok else theme.RED, outline="")
    lab_auth_status = theme.label(
        auth_frame, "PDK 授权已验证" if auth_ok else "PDK 未授权",
        fg=theme.GREEN if auth_ok else theme.RED, bold=True, font_size=theme.FS_BODY,
    )
    lab_auth_status.pack(side=tk.LEFT)
    tk.Frame(auth_frame, bg=theme.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=10)
    lab_auth_detail = theme.label(
        auth_frame, auth_result.display_detail() if auth_ok else "请重新登录",
        muted=True, font_size=theme.FS_BODY, anchor="w",
    )
    lab_auth_detail.pack(side=tk.LEFT, fill=tk.X, expand=True)

    btn_logout = theme.button(auth_frame, "退出", color=theme.SLATE_BTN,
                              active=theme.SLATE_BTN_HOVER, width=6, font_size=theme.FS_BODY)
    btn_logout.pack(side=tk.RIGHT, padx=(4, 12), pady=6)
    btn_power = theme.button(auth_frame, "电源", color=theme.RED_DARK,
                             active=theme.RED, width=6, font_size=theme.FS_BODY)
    btn_power.pack(side=tk.RIGHT, padx=3, pady=6)
    btn_auth = theme.button(auth_frame, "许可证", color=theme.SLATE_BTN,
                            active=theme.SLATE_BTN_HOVER, width=7, font_size=theme.FS_BODY)
    btn_auth.pack(side=tk.RIGHT, padx=3, pady=6)
    btn_pwd = theme.button(auth_frame, "账户资料", color=theme.SLATE_BTN,
                           active=theme.SLATE_BTN_HOVER, width=8, font_size=theme.FS_BODY)
    btn_pwd.pack(side=tk.RIGHT, padx=3, pady=6)

    def _open_settings():
        try:
            from gui.settings_dialog import open_settings_dialog
            open_settings_dialog(root)
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"打开设置中心失败: {e}")

    btn_settings = theme.button(auth_frame, "设置", color=theme.SLATE_BTN,
                                active=theme.SLATE_BTN_HOVER, width=6, font_size=theme.FS_BODY,
                                command=_open_settings)
    btn_settings.pack(side=tk.RIGHT, padx=3, pady=6)

    def _open_logs():
        try:
            from gui.log_dialog import open_log_dialog
            open_log_dialog(root, get_log_history())
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"打开运行日志失败: {e}")

    btn_logs = theme.button(auth_frame, "📜 运行日志", color=theme.SLATE_BTN,
                            active=theme.SLATE_BTN_HOVER, width=9, font_size=theme.FS_BODY,
                            command=_open_logs)
    btn_logs.pack(side=tk.RIGHT, padx=3, pady=6)

    # 预留底栏空间
    footer = tk.Frame(root, bg=theme.BG_ELEVATED, height=22)
    footer.pack(side=tk.BOTTOM, fill=tk.X)
    footer.pack_propagate(False)
    theme.label(footer, "杭州智鑫科技  ·  智播豆 AI 直播管控系统",
                muted=True, font_size=theme.FS_CAPTION, bg=theme.BG_ELEVATED).pack(side=tk.LEFT, padx=16, pady=2)
    theme.label(footer, "LOCAL DESKTOP · SECURE SESSION",
                muted=True, font_size=theme.FS_CAPTION, bg=theme.BG_ELEVATED).pack(side=tk.RIGHT, padx=16, pady=2)

    # ---------------- 底部平铺直播状态栏 (平铺全屏最底端) ----------------
    statusbar = tk.Frame(root, bg=theme.SURFACE, height=36)
    statusbar.pack(side=tk.BOTTOM, fill=tk.X)
    statusbar.pack_propagate(False)

    # 左侧：系统运行与弹幕状态
    lab_sys_status = theme.label(statusbar, "🟢 待机 · 等待启动", fg=theme.GREEN,
                                 bold=True, font_size=theme.FS_BODY, anchor="w")
    lab_sys_status.pack(side=tk.LEFT, padx=(14, 8))

    tk.Frame(statusbar, bg=theme.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=8)

    lab_danmu_status = theme.label(statusbar, "💬 弹幕采集 · 未启动", muted=True,
                                   font_size=theme.FS_BODY, anchor="w")
    lab_danmu_status.pack(side=tk.LEFT, padx=6)

    tk.Frame(statusbar, bg=theme.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=8)

    lab_online = theme.label(statusbar, "📶 在线：0 人", fg=theme.CYAN, bold=True, font_size=theme.FS_BODY)
    lab_online.pack(side=tk.LEFT, padx=6)

    lab_like = theme.label(statusbar, "👍 点赞：0", fg=theme.PURPLE, bold=True, font_size=theme.FS_BODY)
    lab_like.pack(side=tk.LEFT, padx=6)

    lab_gift = theme.label(statusbar, "🎁 礼物：0", fg=theme.AMBER, bold=True, font_size=theme.FS_BODY)
    lab_gift.pack(side=tk.LEFT, padx=6)

    tk.Frame(statusbar, bg=theme.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=8)

    # 链路标签
    def _status_pill(name, color):
        pill = theme.pill(statusbar, name, bg=theme.SURFACE_ALT, fg=color, font_size=theme.FS_CAPTION, bold=True)
        pill.pack(side=tk.LEFT, padx=3)
        return pill

    tag_phone = _status_pill("📱 投屏", theme.AMBER)
    tag_doubao = _status_pill("🎙️ 豆包", theme.GREEN)
    tag_ai = _status_pill("🤖 弹幕", theme.CYAN)
    tag_duck = _status_pill("🔈 闪避", theme.PURPLE)

    # 右侧：OBS 音频链接复制与运行日志快捷按钮
    btn_bar_logs = theme.button(statusbar, "📜 运行日志", color=theme.SLATE_BTN,
                                active=theme.SLATE_BTN_HOVER, font_size=theme.FS_CAPTION, padx=7, pady=2,
                                command=_open_logs)
    btn_bar_logs.pack(side=tk.RIGHT, padx=(4, 12), pady=6)

    tk.Frame(statusbar, bg=theme.BORDER, width=1).pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=8)

    obs_audio_port_init = config.load_config().get("obs_audio_port", 8554)
    lbl_obs_link = theme.label(statusbar, f"OBS音频源: :{obs_audio_port_init}", muted=True, font_size=theme.FS_BODY)
    lbl_obs_link.pack(side=tk.RIGHT, padx=4)

    def _copy_obs_link():
        try:
            curr_port = config.load_config().get("obs_audio_port", 8554)
            curr_url = f"http://127.0.0.1:{curr_port}/danmu_audio"
            root.clipboard_clear()
            root.clipboard_append(curr_url)
            btn_copy_obs.config(text="已复制", fg=theme.GREEN)
            root.after(1500, lambda: btn_copy_obs.config(text="复制", fg=theme.TEXT))
        except Exception:
            pass

    btn_copy_obs = theme.button(statusbar, "复制音频源", color=theme.SURFACE_SOFT,
                                active=theme.BORDER_FOCUS, font_size=theme.FS_CAPTION, padx=7, pady=2,
                                command=_copy_obs_link)
    btn_copy_obs.pack(side=tk.RIGHT, padx=4)

    main_all = tk.Frame(root, bg=theme.BG)
    main_all.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 6))

    # ---------------- 左侧设备与画面 (ui_left) ----------------
    ui_left = tk.Frame(main_all, bg=theme.BG, width=290)
    ui_left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
    ui_left.pack_propagate(False)

    device_card, device_body = theme.card(ui_left, "设备画面 · 音频链路", accent=theme.PRIMARY)
    device_card.pack(fill=tk.BOTH, expand=True)
    theme.label(device_body, "SCRCPY DEVICE CHANNEL", muted=True,
                font_size=theme.FS_CAPTION, anchor="w").pack(fill=tk.X, pady=(0, 5))
    embed_container = tk.Frame(
        device_body, bg="#02070D", bd=0,
        highlightthickness=1, highlightbackground=theme.BORDER,
    )
    embed_container.pack(fill=tk.BOTH, expand=True)

    audio_hint_box = tk.Frame(device_body, bg=theme.SURFACE)
    audio_hint_box.pack(fill=tk.X, pady=(5, 0))
    theme.label(
        audio_hint_box, "音频由 CABLE 路由至 VAD/OBS",
        muted=True, font_size=theme.FS_CAPTION, anchor="center",
    ).pack(side=tk.LEFT, expand=True, padx=(2, 2))

    def _open_audio_mix():
        try:
            from screen import scrcpy_embed
            scrcpy_embed.open_app_volume_settings()
        except Exception:
            pass

    btn_audio_pref = theme.button(
        audio_hint_box, "⚙️ 音频分流", color=theme.SLATE_BTN,
        active=theme.SLATE_BTN_HOVER, font_size=theme.FS_CAPTION, padx=6, pady=2, command=_open_audio_mix,
    )
    btn_audio_pref.pack(side=tk.RIGHT, padx=(2, 2))

    # 抓屏控制条（移至左侧设备卡片，与画面紧密联动）
    cap_bar = tk.Frame(device_body, bg=theme.SURFACE, padx=6, pady=4)
    cap_bar.pack(fill=tk.X, pady=(4, 0))
    lab_cap_status = theme.label(cap_bar, "抓屏 · 已停止", fg=theme.AMBER, font_size=theme.FS_BODY, bg=theme.SURFACE)
    lab_cap_status.pack(side=tk.LEFT)
    btn_cap = theme.button(cap_bar, "开启抓屏", color=theme.SLATE_BTN,
                           active=theme.SLATE_BTN_HOVER, width=8, state=tk.DISABLED, font_size=theme.FS_BODY, pady=2)
    btn_cap.pack(side=tk.RIGHT)

    # ---------------- 右侧主控制台 (ui_right) ----------------
    ui_right = tk.Frame(main_all, bg=theme.BG)
    ui_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # 1. 产品与弹幕配置（严格 2 行 5 列对称对齐）
    cfg_card, cfg = theme.card(ui_right, "产品与弹幕配置", accent=theme.PRIMARY, pady=6)
    cfg_card.pack(fill=tk.X, pady=(0, 6))
    cfg.grid_columnconfigure(0, weight=0)
    cfg.grid_columnconfigure(1, weight=1)
    cfg.grid_columnconfigure(2, weight=0)
    cfg.grid_columnconfigure(3, weight=2)
    cfg.grid_columnconfigure(4, weight=0)

    # 第 1 行：产品名称 | 产品描述 | 保存配置
    _section_label(cfg, "产品名称", 0, 0, padx=(0, 6), pady=3, sticky="w")
    ent_prod_name = theme.entry(cfg)
    ent_prod_name.grid(row=0, column=1, padx=(0, 10), pady=3, sticky="ew", ipady=2)

    _section_label(cfg, "产品描述", 0, 2, padx=(0, 6), pady=3, sticky="w")
    ent_prod_desc = theme.entry(cfg)
    ent_prod_desc.grid(row=0, column=3, padx=(0, 10), pady=3, sticky="ew", ipady=2)

    btn_save = theme.button(cfg, "💾 保存配置", color=theme.PRIMARY,
                            active=theme.PRIMARY_HOVER, width=9, font_size=theme.FS_BODY)
    btn_save.grid(row=0, column=4, pady=3, sticky="e")

    # 第 2 行：直播间地址与手动启动弹幕按钮
    _section_label(cfg, "直播间", 1, 0, padx=(0, 6), pady=3, sticky="w")
    ent_danmu_url = theme.entry(cfg)
    ent_danmu_url.grid(row=1, column=1, columnspan=3, padx=(0, 10), pady=3, sticky="ew", ipady=2)

    btn_danmu = theme.button(cfg, "🚀 启动弹幕", color=theme.TEAL,
                             active=theme.CYAN, width=9, font_size=theme.FS_BODY)
    btn_danmu.grid(row=1, column=4, pady=3, sticky="e")

    # 2. 策略与预演并排区
    strategy_row = tk.Frame(ui_right, bg=theme.BG)
    strategy_row.pack(fill=tk.X, pady=(0, 6))
    strategy_row.grid_columnconfigure(0, weight=2, uniform="strategy")
    strategy_row.grid_columnconfigure(1, weight=3, uniform="strategy")

    meet_card, meet = theme.card(strategy_row, "开播预演", accent=theme.PRIMARY, pady=6)
    meet_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    txt_pre_meet = scrolledtext.ScrolledText(meet, height=3, wrap=tk.WORD)
    _configure_text(txt_pre_meet)
    txt_pre_meet.pack(fill=tk.BOTH, expand=True)

    btn_meet = theme.button(meet, "▶ 执行预演", color=theme.SLATE_BTN,
                            active=theme.SLATE_BTN_HOVER, width=9, state=tk.DISABLED, font_size=theme.FS_BODY)
    btn_meet.pack(anchor="e", pady=(5, 0))

    script_card, scripts = theme.card(strategy_row, "区间话术策略", accent=theme.PRIMARY, pady=6)
    script_card.grid(row=0, column=1, sticky="nsew")

    def _open_script_handler(key):
        from broadcast.script_files import open_script_notepad
        def _on_saved(_k):
            if root is not None:
                try:
                    root.after(0, refresh_script_labels)
                except Exception:
                    pass
        open_script_notepad(key, on_saved=_on_saved, log_fn=log_screen)

    def _close_notepads_handler():
        from broadcast.script_files import close_all_script_notepads
        cnt = close_all_script_notepads(log_fn=log_screen)
        refresh_script_labels()
        if cnt == 0:
            log_screen("【话术策略】当前没有打开中的记事本。")

    # 在 script_card 右上角标题栏嵌入“全部关闭”按钮，彻底释放行内空间
    btn_close_notepads = theme.button(
        script_card.header, "✕ 全部关闭",
        color=theme.SURFACE_SOFT, active=theme.BORDER, font_size=theme.FS_CAPTION,
        padx=6, pady=1, command=_close_notepads_handler,
    )
    btn_close_notepads.pack(side=tk.RIGHT, pady=2)

    script_rows_cfg = (
        ("区间 01", "0", "30", "01"),
        ("区间 02", "30", "100", "02"),
        ("区间 03", "100", "9999", "03"),
    )
    range_widgets = []
    txt_btns = []
    txt_labels = []
    txt_previews = []

    scripts.grid_columnconfigure(7, weight=1)

    for row, (title, _start, _end, key) in enumerate(script_rows_cfg):
        _section_label(scripts, title, row, 0, padx=(0, 4), pady=3, sticky="w")
        start_entry = theme.entry(scripts, width=4)
        start_entry.grid(row=row, column=1, pady=3, sticky="w", ipady=2)
        theme.label(scripts, "—", muted=True, font_size=theme.FS_BODY).grid(row=row, column=2, padx=2)
        end_entry = theme.entry(scripts, width=5)
        end_entry.grid(row=row, column=3, pady=3, sticky="w", ipady=2)
        theme.label(scripts, "人", muted=True, font_size=theme.FS_BODY).grid(row=row, column=4, padx=(2, 6))

        file_pill = theme.pill(
            scripts, f"{key}.txt", bg=theme.SURFACE_SOFT,
            fg=theme.CYAN, font_size=theme.FS_CAPTION, bold=True, padx=6, pady=2,
        )
        file_pill.grid(row=row, column=5, padx=(0, 4), sticky="w")

        lab_info = theme.label(scripts, "(加载中)", muted=True, font_size=theme.FS_CAPTION, width=6, anchor="w")
        lab_info.grid(row=row, column=6, padx=(0, 4), sticky="w")

        lab_prev = theme.label(scripts, "...", muted=True, font_size=theme.FS_CAPTION, anchor="w", width=1)
        lab_prev.grid(row=row, column=7, padx=(4, 8), sticky="ew")

        btn_open = theme.button(
            scripts, "📄 打开编辑",
            color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER, width=9, font_size=theme.FS_CAPTION,
            padx=6, pady=2,
            command=lambda k=key: _open_script_handler(k),
        )
        btn_open.grid(row=row, column=8, pady=3, sticky="e")

        range_widgets.append((start_entry, end_entry))
        txt_btns.append(btn_open)
        txt_labels.append(lab_info)
        txt_previews.append(lab_prev)

    (ent_r1min, ent_r1max), (ent_r2min, ent_r2max), (ent_r3min, ent_r3max) = range_widgets
    btn_open_txt1, btn_open_txt2, btn_open_txt3 = txt_btns
    lab_txt1_info, lab_txt2_info, lab_txt3_info = txt_labels
    lab_txt1_preview, lab_txt2_preview, lab_txt3_preview = txt_previews

    # 3. 直播控制与音频活动（清晰分层，主控居中醒目，杜绝挤压）
    ctrl_card, controls = theme.card(ui_right, "直播控制与音频活动", accent=theme.PRIMARY, pady=6)
    ctrl_card.pack(fill=tk.X, pady=(0, 6))

    top_ctrl = tk.Frame(controls, bg=theme.SURFACE)
    top_ctrl.pack(fill=tk.X, pady=(0, 4))

    theme.label(top_ctrl, "语言", muted=True, font_size=theme.FS_BODY).pack(side=tk.LEFT, padx=(0, 4))
    cmb_doubao_lang = ttk.Combobox(
        top_ctrl, style="Zhibodou.TCombobox",
        values=config.DOUBAO_LANGUAGES, width=7, state="readonly",
    )
    cmb_doubao_lang.pack(side=tk.LEFT, padx=(0, 12))

    btn_live_start = theme.button(top_ctrl, "▶ 启动直播", color=theme.GREEN_DARK,
                                  active=theme.GREEN, width=9, state=tk.DISABLED, font_size=theme.FS_BODY)
    btn_live_start.pack(side=tk.LEFT, padx=(0, 6))

    btn_live_stop = theme.button(top_ctrl, "⏹ 停止直播", color=theme.RED_DARK,
                                 active=theme.RED, width=9, state=tk.DISABLED, font_size=theme.FS_BODY)
    btn_live_stop.pack(side=tk.LEFT, padx=(0, 10))

    lab_count = theme.label(top_ctrl, "下一轮 · 已就绪", fg=theme.CYAN,
                            bold=True, font_size=theme.FS_BODY, anchor="e")
    lab_count.pack(side=tk.RIGHT, padx=(4, 0))

    # VAD 音量电平表与快速监控
    meter_row = tk.Frame(controls, bg=theme.SURFACE)
    meter_row.pack(fill=tk.X, pady=(2, 0))

    theme.label(meter_row, "VAD 监听", muted=True, bold=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT, padx=(0, 6))
    volume_canvas = tk.Canvas(meter_row, width=280, height=14, bg=theme.SURFACE_ALT,
                              bd=0, highlightthickness=0)
    volume_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

    lab_vad_state = theme.label(meter_row, "待机 · 等待音频", muted=True,
                                font_size=theme.FS_BODY, width=20, anchor="w")
    lab_vad_state.pack(side=tk.LEFT, padx=(8, 0))

    root.after_idle(lambda: _draw_meter_fill(0, theme.TEXT_FAINT))
    if not _volume_poll_started:
        _volume_poll_started = True
        _volume_after_id = root.after(50, _poll_volume_meter)

    # ---------------- 4. 兼容适配器初始化 (弹幕与运行日志移出主界面) ----------------
    txt_danmu = DanmuTextAdapter()
    txt_screen_log = TextLogAdapter()

    # ---------------- 5. ⚡ 多平台直播流解析 (StreamGet) & OBS 串流联动 ----------------
    stream_card, stream_body = theme.card(ui_right, "⚡ 多平台直播流解析 (StreamGet) & OBS 串流联动", accent=theme.PRIMARY, pady=6)
    stream_card.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

    # 5.1 输入行：直播流地址输入 + 一键复制上面直播间 + 解析按钮 + 清空
    input_row = tk.Frame(stream_body, bg=theme.SURFACE)
    input_row.pack(fill=tk.X, pady=(0, 5))

    theme.label(input_row, "直播流地址", muted=True, font_size=theme.FS_BODY).pack(side=tk.LEFT, padx=(0, 6))
    ent_stream_input = theme.entry(input_row)
    ent_stream_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=2)

    def _sync_from_danmu_url():
        u = ent_danmu_url.get().strip()
        if u:
            ent_stream_input.delete(0, tk.END)
            ent_stream_input.insert(0, u)
        else:
            messagebox.showinfo("提示", "当前产品配置中的直播间地址为空，请先在上方输入或直接在此输入链接", parent=root)

    btn_link_danmu = theme.button(
        input_row, "🔗 同直播间", color=theme.SURFACE_SOFT, active=theme.BORDER_FOCUS,
        font_size=theme.FS_CAPTION, padx=6, pady=2, command=_sync_from_danmu_url,
    )
    btn_link_danmu.pack(side=tk.LEFT, padx=(0, 6))

    btn_parse_stream = theme.button(
        input_row, "🔍 解析流地址", color=theme.PRIMARY, active=theme.PRIMARY_HOVER,
        width=11, font_size=theme.FS_BODY,
    )
    btn_parse_stream.pack(side=tk.LEFT, padx=(0, 6))

    def _clear_stream_fields():
        ent_stream_input.delete(0, tk.END)
        ent_stream_url.delete(0, tk.END)
        lab_stream_meta.config(text="未解析 · 支持解析国内外 40+ 平台（抖音/快手/B站/虎牙/斗鱼/小红书/TikTok/Twitch/YouTube等）", fg=theme.TEXT_MUTED)
        lab_obs_sync_status.config(text="已就绪", fg=theme.TEXT_MUTED)

    btn_clear_stream = theme.button(
        input_row, "🧹 清空", color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER,
        width=6, font_size=theme.FS_CAPTION, padx=6, pady=2, command=_clear_stream_fields,
    )
    btn_clear_stream.pack(side=tk.LEFT)

    # 5.2 平台与主播信息条
    meta_bar = tk.Frame(stream_body, bg=theme.SURFACE_ALT, padx=8, pady=5)
    meta_bar.pack(fill=tk.X, pady=(0, 5))
    lab_stream_meta = theme.label(
        meta_bar, "未解析 · 支持国内外 40+ 平台（抖音/快手/B站/虎牙/斗鱼/小红书/TikTok/Twitch/YouTube等）",
        muted=True, font_size=theme.FS_CAPTION, bg=theme.SURFACE_ALT, anchor="w",
    )
    lab_stream_meta.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # 5.3 清晰度、格式与流地址展示行
    out_row = tk.Frame(stream_body, bg=theme.SURFACE)
    out_row.pack(fill=tk.X, pady=(0, 5))

    theme.label(out_row, "清晰度", muted=True, font_size=theme.FS_BODY).pack(side=tk.LEFT, padx=(0, 4))
    cmb_stream_quality = ttk.Combobox(out_row, style="Zhibodou.TCombobox", width=10, state="readonly")
    cmb_stream_quality.pack(side=tk.LEFT, padx=(0, 8))

    theme.label(out_row, "格式", muted=True, font_size=theme.FS_BODY).pack(side=tk.LEFT, padx=(0, 4))
    cmb_stream_format = ttk.Combobox(out_row, style="Zhibodou.TCombobox", width=6, state="readonly")
    cmb_stream_format.pack(side=tk.LEFT, padx=(0, 8))

    theme.label(out_row, "播放流", muted=True, font_size=theme.FS_BODY).pack(side=tk.LEFT, padx=(0, 4))
    ent_stream_url = theme.entry(out_row)
    ent_stream_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=2)

    def _copy_parsed_stream_url():
        u = ent_stream_url.get().strip()
        if not u:
            messagebox.showinfo("提示", "当前没有可复制的流地址，请先解析直播间", parent=root)
            return
        root.clipboard_clear()
        root.clipboard_append(u)
        btn_copy_stream.config(text="已复制", fg=theme.GREEN)
        root.after(1500, lambda: btn_copy_stream.config(text="📋 复制", fg=theme.TEXT))

    btn_copy_stream = theme.button(
        out_row, "📋 复制", color=theme.SURFACE_SOFT, active=theme.BORDER_FOCUS,
        font_size=theme.FS_CAPTION, padx=6, pady=2, command=_copy_parsed_stream_url,
    )
    btn_copy_stream.pack(side=tk.LEFT, padx=(0, 4))

    def _play_stream_url():
        u = ent_stream_url.get().strip()
        if not u:
            messagebox.showinfo("提示", "当前没有可播放的流地址", parent=root)
            return
        try:
            import webbrowser
            webbrowser.open(u)
        except Exception as e:
            messagebox.showerror("错误", f"调起播放失败: {e}", parent=root)

    btn_play_stream = theme.button(
        out_row, "▶ 播放", color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER,
        font_size=theme.FS_CAPTION, padx=6, pady=2, command=_play_stream_url,
    )
    btn_play_stream.pack(side=tk.LEFT)

    # 5.4 OBS 自动联动控制行
    obs_ctrl_row = tk.Frame(stream_body, bg=theme.SURFACE)
    obs_ctrl_row.pack(fill=tk.X, pady=(2, 0))

    var_auto_obs = tk.BooleanVar(value=bool(config.load_config().get("auto_sync_obs_stream", False)))
    chk_auto_obs = tk.Checkbutton(
        obs_ctrl_row, text="解析后自动添加/同步流媒体源到 OBS",
        variable=var_auto_obs,
        bg=theme.SURFACE, fg=theme.TEXT_SOFT, selectcolor=theme.SURFACE_ALT,
        activebackground=theme.SURFACE, activeforeground=theme.TEXT,
        font=theme.font(theme.FS_BODY),
    )
    chk_auto_obs.pack(side=tk.LEFT, padx=(0, 10))

    obs_ws_port_init = config.load_config().get("obs_websocket_port", 5544)
    theme.label(obs_ctrl_row, f"OBS WS 端口: {obs_ws_port_init}", muted=True, font_size=theme.FS_BODY).pack(side=tk.LEFT, padx=(0, 10))

    btn_sync_obs = theme.button(
        obs_ctrl_row, "🔄 立即同步至 OBS 场景", color=theme.TEAL, active=theme.CYAN,
        font_size=theme.FS_BODY, padx=8, pady=2,
    )
    btn_sync_obs.pack(side=tk.LEFT, padx=(0, 10))

    lab_obs_sync_status = theme.label(
        obs_ctrl_row, "已就绪 · 勾选后解析自动下发", muted=True, font_size=theme.FS_BODY,
    )
    lab_obs_sync_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ---------------- 业务交互回调与事件绑定 ----------------
    _parsed_stream_cache: dict = {}

    def _on_stream_option_change(*args):
        nonlocal _parsed_stream_cache
        if not _parsed_stream_cache:
            return
        streams = _parsed_stream_cache.get("streams", {})
        q_label = cmb_stream_quality.get()
        q_code = "OD"
        from broadcast.stream_parser import QUALITY_NAMES
        for code, label in QUALITY_NAMES.items():
            if label == q_label or code == q_label:
                q_code = code
                break

        fmt = cmb_stream_format.get().lower()  # "flv" 或 "m3u8"
        stream_dict = streams.get(q_code, {})
        url = stream_dict.get(fmt) or stream_dict.get("flv") or stream_dict.get("m3u8") or ""
        ent_stream_url.delete(0, tk.END)
        ent_stream_url.insert(0, url)

    cmb_stream_quality.bind("<<ComboboxSelected>>", _on_stream_option_change)
    cmb_stream_format.bind("<<ComboboxSelected>>", _on_stream_option_change)

    def _do_push_to_obs_worker(stream_url):
        from broadcast.obs_websocket import check_obs_websocket_port, push_stream_to_obs
        cfg = config.load_config()
        obs_port = int(cfg.get("obs_websocket_port", 5544))
        obs_pwd = str(cfg.get("obs_websocket_password", ""))

        # 检查 5544 端口是否开放
        if not check_obs_websocket_port(port=obs_port):
            def _prompt():
                lab_obs_sync_status.config(text=f"⚠️ 未检测到 OBS (端口 {obs_port})，请启动 OBS 并开启服务", fg=theme.AMBER)
                messagebox.showwarning(
                    "OBS WebSocket 未连接",
                    f"未检测到 OBS WebSocket 服务 (端口 {obs_port})！\n\n"
                    f"请按以下步骤开启：\n"
                    f"1. 启动 OBS Studio 客户端；\n"
                    f"2. 点击顶部菜单栏【工具】 -> 【WebSocket 服务器设置】；\n"
                    f"3. 勾选【启用 WebSocket 服务器】；\n"
                    f"4. 确认服务器端口为 {obs_port}（无需设置密码或在设置中配置密码）；\n"
                    f"5. 点击【应用】后重新同步。",
                    parent=root,
                )
            root.after(0, _prompt)
            return

        def _set_syncing():
            lab_obs_sync_status.config(text=f"正在连接 OBS (端口 {obs_port}) 并下发网络流...", fg=theme.CYAN)
        root.after(0, _set_syncing)

        res = push_stream_to_obs(stream_url, port=obs_port, password=obs_pwd)

        def _done():
            if res.get("success"):
                lab_obs_sync_status.config(text=res.get("message"), fg=theme.GREEN)
                messagebox.showinfo("OBS 联动成功", res.get("message"), parent=root)
            else:
                lab_obs_sync_status.config(text=f"❌ 同步失败: {res.get('message')}", fg=theme.RED)
                messagebox.showerror("OBS 同步失败", res.get("message"), parent=root)
        root.after(0, _done)

    def _on_sync_obs_clicked():
        u = ent_stream_url.get().strip()
        if not u:
            messagebox.showwarning("提示", "请先解析直播间获取有效的流媒体播放地址！", parent=root)
            return
        threading.Thread(target=_do_push_to_obs_worker, args=(u,), daemon=True).start()

    btn_sync_obs.config(command=_on_sync_obs_clicked)

    def _on_parse_stream_clicked():
        url = ent_stream_input.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入要解析的直播间网址或分享链接！", parent=root)
            return

        btn_parse_stream.config(state=tk.DISABLED)
        lab_stream_meta.config(text="🔍 正在调取 StreamGet 引擎解析直播间，请稍候...", fg=theme.CYAN)
        lab_obs_sync_status.config(text="等待解析完成...", fg=theme.TEXT_MUTED)

        def _worker():
            from broadcast.stream_parser import parse_stream, QUALITY_NAMES
            res = parse_stream(url)

            def _update_ui():
                nonlocal _parsed_stream_cache
                btn_parse_stream.config(state=tk.NORMAL)
                if not res.get("success"):
                    lab_stream_meta.config(text=f"❌ 解析失败: {res.get('message')}", fg=theme.RED)
                    messagebox.showerror("解析失败", res.get("message"), parent=root)
                    return

                _parsed_stream_cache = res
                plat = res.get("platform", "直播间")
                anchor = res.get("anchor_name", "主播")
                title = res.get("title", "")
                is_live = res.get("is_live", False)
                live_badge = "🟢 直播中" if is_live else "🔴 未开播"

                lab_stream_meta.config(
                    text=f"【{plat}】 {live_badge} · 主播：{anchor} · 标题：{title}",
                    fg=theme.GREEN if is_live else theme.AMBER,
                )

                # 填充清晰度与格式下拉框
                avail_q = res.get("available_qualities", [])
                q_display = [QUALITY_NAMES.get(q, q) for q in avail_q]
                cmb_stream_quality["values"] = q_display
                if q_display:
                    cmb_stream_quality.current(0)

                avail_fmt = res.get("available_formats", ["FLV", "M3U8"])
                cmb_stream_format["values"] = avail_fmt
                if avail_fmt:
                    cmb_stream_format.current(0)

                # 填入默认 URL
                def_url = res.get("default_url", "")
                ent_stream_url.delete(0, tk.END)
                ent_stream_url.insert(0, def_url)

                # 保存到配置
                try:
                    config.save_config({
                        "streamget_url": url,
                        "auto_sync_obs_stream": var_auto_obs.get(),
                    })
                except Exception:
                    pass

                # 若开启了自动同步至 OBS
                if var_auto_obs.get() and def_url:
                    threading.Thread(target=_do_push_to_obs_worker, args=(def_url,), daemon=True).start()

            root.after(0, _update_ui)

        threading.Thread(target=_worker, daemon=True).start()

    btn_parse_stream.config(command=_on_parse_stream_clicked)


    # ---------------- 业务配置回填 ----------------
    cfg_load = config.load_config()
    _fallback_platform = str(cfg_load.get("danmu_platform") or "douyin")
    _danmu_urls = cfg_load.get("danmu_urls") or {}
    danmu_url = str(cfg_load.get("danmu_url") or _danmu_urls.get(_fallback_platform) or "")
    ent_danmu_url.insert(0, danmu_url)

    _lang = str(cfg_load.get("doubao_language") or "普通话")
    if _lang not in config.DOUBAO_LANGUAGES:
        _lang = "普通话"
    cmb_doubao_lang.set(_lang)
    ent_prod_name.insert(0, cfg_load["product_name"])
    ent_prod_desc.insert(0, cfg_load["product_desc"])
    txt_pre_meet.insert(tk.END, cfg_load["pre_meet_text"])
    ent_r1min.insert(0, cfg_load["r1_min"])
    ent_r1max.insert(0, cfg_load["r1_max"])
    ent_r2min.insert(0, cfg_load["r2_min"])
    ent_r2max.insert(0, cfg_load["r2_max"])
    ent_r3min.insert(0, cfg_load["r3_min"])
    ent_r3max.insert(0, cfg_load["r3_max"])

    _saved_streamget_url = str(cfg_load.get("streamget_url") or "")
    if _saved_streamget_url and ent_stream_input is not None:
        ent_stream_input.insert(0, _saved_streamget_url)
    elif danmu_url and ent_stream_input is not None:
        ent_stream_input.insert(0, danmu_url)

    refresh_script_labels()

    # AI 弹幕回复硬件自适应探测
    try:
        from danma.hardware import detect_gpu_tier
        detected = detect_gpu_tier()
        log_screen(f"【硬件探测】{detected['summary']}")
    except Exception:
        pass


def refresh_script_labels():
    """刷新 01.txt, 02.txt, 03.txt 文件的字数与话术内容预览显示。"""
    try:
        from broadcast.script_files import (
            get_script_word_count,
            read_script_content,
            ensure_script_files_exist,
        )
        import tkinter.font as tkfont
        ensure_script_files_exist()

        triplets = (
            ("01", lab_txt1_info, lab_txt1_preview),
            ("02", lab_txt2_info, lab_txt2_preview),
            ("03", lab_txt3_info, lab_txt3_preview),
        )
        for key, lbl, prev_lbl in triplets:
            content = read_script_content(key).strip()
            cnt = len(content)
            if lbl is not None:
                if cnt > 0:
                    lbl.config(text=f"({cnt}字)", fg="#86efac")
                else:
                    lbl.config(text="(空)", fg="#fbbf24")

            if prev_lbl is not None:
                prev_lbl._raw_script = content

                def _render_preview(lbl_widget=prev_lbl):
                    raw = getattr(lbl_widget, "_raw_script", "")
                    cleaned = " ".join(raw.split()).strip()
                    if not cleaned:
                        lbl_widget.config(text="（空内容）...", fg=theme.TEXT_FAINT)
                        return
                    w = lbl_widget.winfo_width()
                    ell = "..."
                    # 若控件尚未在屏幕完成初次布局 (w <= 20)，先按标准 25 字展示
                    if w <= 20:
                        disp = (cleaned[:25] + ell) if len(cleaned) > 25 else (cleaned + ell)
                        lbl_widget.config(text=disp, fg=theme.TEXT_MUTED)
                        return
                    try:
                        f_obj = tkfont.Font(font=lbl_widget["font"])
                        ell_w = f_obj.measure(ell)
                        avail = max(30, w - ell_w - 6)
                        cur = ""
                        for ch in cleaned:
                            if f_obj.measure(cur + ch) > avail:
                                break
                            cur += ch
                        disp = (cur or cleaned[:15]) + ell
                    except Exception:
                        disp = (cleaned[:25] + ell) if len(cleaned) > 25 else (cleaned + ell)
                    lbl_widget.config(text=disp, fg=theme.TEXT_MUTED)

                _render_preview(prev_lbl)
                if not getattr(prev_lbl, "_bound_cfg", False):
                    prev_lbl.bind("<Configure>", lambda e, l=prev_lbl: _render_preview(l))
                    prev_lbl._bound_cfg = True

    except Exception:
        pass

