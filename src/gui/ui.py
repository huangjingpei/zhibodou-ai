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
btn_save = None
btn_danmu = None
ent_danmu_url = None
cmb_doubao_lang = None
ent_prod_name = None
ent_prod_desc = None
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
    """线程安全追加运行日志，并同步回显到控制台。"""
    if _shutting_down:
        return
    try:
        print(msg)
    except Exception:
        pass
    try:
        def _do():
            txt_screen_log.insert(tk.END, msg + "\n")
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
    global btn_pwd, btn_auth, btn_settings, btn_save, btn_danmu, btn_logout
    global ent_danmu_url, cmb_doubao_lang
    global volume_canvas, lab_vad_state, _volume_poll_started, _volume_after_id, _shutting_down
    global ent_prod_name, ent_prod_desc, ent_r1min, ent_r1max, ent_cmd1
    global ent_r2min, ent_r2max, ent_cmd2, ent_r3min, ent_r3max, ent_cmd3, ent_interval
    global ent_deepseek_key, var_ai_reply, cmb_danmu_mode
    global btn_open_txt1, btn_open_txt2, btn_open_txt3, lab_txt1_info, lab_txt2_info, lab_txt3_info
    global lab_txt1_preview, lab_txt2_preview, lab_txt3_preview
    global btn_close_notepads, lbl_obs_link

    _shutting_down = False
    _volume_poll_started = False
    _volume_after_id = None
    root = tk.Tk()
    root.title("智播豆 · AI 智能直播工作台")
    root.geometry("1280x800")
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
                           font=(theme.FONT_EN, 10, "bold"), tags="header-fg")
        header.create_text(62, 19, text="智播豆  ·  AI 智能直播工作台",
                           fill=theme.TEXT, anchor="w", font=theme.font(13, "bold"), tags="header-fg")
        header.create_text(63, 36, text="ZHIBODOU LIVE OPERATIONS CONSOLE",
                           fill=theme.TEXT_MUTED, anchor="w", font=(theme.FONT_EN, 7), tags="header-fg")
        header.create_text(w - 20, 25, text="DESKTOP  v1.7.0",
                           fill=theme.TEXT_MUTED, anchor="e", font=(theme.FONT_EN, 8, "bold"), tags="header-fg")

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
        fg=theme.GREEN if auth_ok else theme.RED, bold=True, font_size=9,
    )
    lab_auth_status.pack(side=tk.LEFT)
    tk.Frame(auth_frame, bg=theme.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=10)
    lab_auth_detail = theme.label(
        auth_frame, auth_result.display_detail() if auth_ok else "请重新登录",
        muted=True, font_size=9, anchor="w",
    )
    lab_auth_detail.pack(side=tk.LEFT, fill=tk.X, expand=True)

    btn_logout = theme.button(auth_frame, "退出", color=theme.SLATE_BTN,
                              active=theme.SLATE_BTN_HOVER, width=7, font_size=8)
    btn_logout.pack(side=tk.RIGHT, padx=(4, 12), pady=7)
    btn_power = theme.button(auth_frame, "电源", color=theme.RED_DARK,
                             active=theme.RED, width=7, font_size=8)
    btn_power.pack(side=tk.RIGHT, padx=3, pady=7)
    btn_auth = theme.button(auth_frame, "许可证", color=theme.SLATE_BTN,
                            active=theme.SLATE_BTN_HOVER, width=7, font_size=8)
    btn_auth.pack(side=tk.RIGHT, padx=3, pady=7)
    btn_pwd = theme.button(auth_frame, "账户资料", color=theme.SLATE_BTN,
                           active=theme.SLATE_BTN_HOVER, width=8, font_size=8)
    btn_pwd.pack(side=tk.RIGHT, padx=3, pady=7)

    def _open_settings():
        try:
            from gui.settings_dialog import open_settings_dialog
            open_settings_dialog(root)
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("错误", f"打开设置中心失败: {e}")

    btn_settings = theme.button(auth_frame, "设置", color=theme.SLATE_BTN,
                                active=theme.SLATE_BTN_HOVER, width=7, font_size=8,
                                command=_open_settings)
    btn_settings.pack(side=tk.RIGHT, padx=3, pady=7)

    # 预留底栏空间
    footer = tk.Frame(root, bg=theme.BG_ELEVATED, height=24)
    footer.pack(side=tk.BOTTOM, fill=tk.X)
    footer.pack_propagate(False)
    theme.label(footer, "杭州智鑫科技  ·  智播豆 AI 直播管控系统",
                muted=True, font_size=8, bg=theme.BG_ELEVATED).pack(side=tk.LEFT, padx=16, pady=3)
    theme.label(footer, "LOCAL DESKTOP · SECURE SESSION",
                muted=True, font_size=8, bg=theme.BG_ELEVATED).pack(side=tk.RIGHT, padx=16, pady=3)

    main_all = tk.Frame(root, bg=theme.BG)
    main_all.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 6))

    # ---------------- 左侧设备与画面 (ui_left) ----------------
    ui_left = tk.Frame(main_all, bg=theme.BG, width=290)
    ui_left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
    ui_left.pack_propagate(False)

    device_card, device_body = theme.card(ui_left, "设备画面 · 音频链路", accent=theme.PRIMARY)
    device_card.pack(fill=tk.BOTH, expand=True)
    theme.label(device_body, "SCRCPY DEVICE CHANNEL", muted=True,
                font_size=8, anchor="w").pack(fill=tk.X, pady=(0, 5))
    embed_container = tk.Frame(
        device_body, bg="#02070D", bd=0,
        highlightthickness=1, highlightbackground=theme.BORDER,
    )
    embed_container.pack(fill=tk.BOTH, expand=True)

    audio_hint_box = tk.Frame(device_body, bg=theme.SURFACE)
    audio_hint_box.pack(fill=tk.X, pady=(5, 0))
    theme.label(
        audio_hint_box, "音频由 CABLE 路由至 VAD/OBS",
        muted=True, font_size=8, anchor="center",
    ).pack(side=tk.LEFT, expand=True, padx=(2, 2))

    def _open_audio_mix():
        try:
            from screen import scrcpy_embed
            scrcpy_embed.open_app_volume_settings()
        except Exception:
            pass

    btn_audio_pref = theme.button(
        audio_hint_box, "⚙️ 音频分流", color=theme.SLATE_BTN,
        active=theme.SLATE_BTN_HOVER, font_size=8, padx=6, pady=2, command=_open_audio_mix,
    )
    btn_audio_pref.pack(side=tk.RIGHT, padx=(2, 2))

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
                            active=theme.PRIMARY_HOVER, width=9, font_size=9)
    btn_save.grid(row=0, column=4, pady=3, sticky="e")

    # 第 2 行：直播间地址与手动启动弹幕按钮
    _section_label(cfg, "直播间", 1, 0, padx=(0, 6), pady=3, sticky="w")
    ent_danmu_url = theme.entry(cfg)
    ent_danmu_url.grid(row=1, column=1, columnspan=3, padx=(0, 10), pady=3, sticky="ew", ipady=2)

    btn_danmu = theme.button(cfg, "🚀 启动弹幕", color=theme.TEAL,
                             active=theme.CYAN, width=9, font_size=9)
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
                            active=theme.SLATE_BTN_HOVER, width=9, state=tk.DISABLED, font_size=8)
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
        color=theme.SURFACE_SOFT, active=theme.BORDER, font_size=8,
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
        theme.label(scripts, "—", muted=True, font_size=9).grid(row=row, column=2, padx=2)
        end_entry = theme.entry(scripts, width=5)
        end_entry.grid(row=row, column=3, pady=3, sticky="w", ipady=2)
        theme.label(scripts, "人", muted=True, font_size=8).grid(row=row, column=4, padx=(2, 6))

        file_pill = theme.pill(
            scripts, f"{key}.txt", bg=theme.SURFACE_SOFT,
            fg=theme.CYAN, font_size=8, bold=True, padx=5, pady=2,
        )
        file_pill.grid(row=row, column=5, padx=(0, 4), sticky="w")

        lab_info = theme.label(scripts, "(加载中)", muted=True, font_size=8, width=6, anchor="w")
        lab_info.grid(row=row, column=6, padx=(0, 4), sticky="w")

        lab_prev = theme.label(scripts, "...", muted=True, font_size=8, anchor="w", width=1)
        lab_prev.grid(row=row, column=7, padx=(4, 8), sticky="ew")

        btn_open = theme.button(
            scripts, "📄 打开编辑",
            color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER, width=9, font_size=8,
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

    theme.label(top_ctrl, "语言", muted=True, font_size=9).pack(side=tk.LEFT, padx=(0, 4))
    cmb_doubao_lang = ttk.Combobox(
        top_ctrl, style="Zhibodou.TCombobox",
        values=config.DOUBAO_LANGUAGES, width=7, state="readonly",
    )
    cmb_doubao_lang.pack(side=tk.LEFT, padx=(0, 12))

    btn_live_start = theme.button(top_ctrl, "▶ 启动直播", color=theme.GREEN_DARK,
                                  active=theme.GREEN, width=9, state=tk.DISABLED, font_size=9)
    btn_live_start.pack(side=tk.LEFT, padx=(0, 6))

    btn_live_stop = theme.button(top_ctrl, "⏹ 停止直播", color=theme.RED_DARK,
                                 active=theme.RED, width=9, state=tk.DISABLED, font_size=9)
    btn_live_stop.pack(side=tk.LEFT, padx=(0, 10))

    lab_count = theme.label(top_ctrl, "下一轮 · 已就绪", fg=theme.CYAN,
                            bold=True, font_size=9, anchor="e")
    lab_count.pack(side=tk.RIGHT, padx=(4, 0))

    # VAD 音量电平表与快速监控
    meter_row = tk.Frame(controls, bg=theme.SURFACE)
    meter_row.pack(fill=tk.X, pady=(2, 0))

    theme.label(meter_row, "VAD 监听", muted=True, bold=True, font_size=8).pack(side=tk.LEFT, padx=(0, 6))
    volume_canvas = tk.Canvas(meter_row, width=280, height=14, bg=theme.SURFACE_ALT,
                              bd=0, highlightthickness=0)
    volume_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

    lab_vad_state = theme.label(meter_row, "待机 · 等待音频", muted=True,
                                font_size=8, width=20, anchor="w")
    lab_vad_state.pack(side=tk.LEFT, padx=(8, 0))

    root.after_idle(lambda: _draw_meter_fill(0, theme.TEXT_FAINT))
    if not _volume_poll_started:
        _volume_poll_started = True
        _volume_after_id = root.after(50, _poll_volume_meter)

    # ---------------- 4. 底部三栏（实时弹幕 | 运行日志 | 直播状态） ----------------
    bottom = tk.Frame(ui_right, bg=theme.BG)
    bottom.pack(fill=tk.BOTH, expand=True)
    bottom.grid_columnconfigure(0, weight=3, uniform="bottom")
    bottom.grid_columnconfigure(1, weight=2, uniform="bottom")
    bottom.grid_columnconfigure(2, weight=2, uniform="bottom")
    bottom.grid_rowconfigure(0, weight=1)

    # 4.1 实时弹幕
    feed_card, feed = theme.card(bottom, "实时弹幕", accent=theme.PRIMARY)
    feed_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    txt_danmu = scrolledtext.ScrolledText(feed, width=1, height=1, wrap=tk.WORD)
    _configure_text(txt_danmu)
    txt_danmu.pack(fill=tk.BOTH, expand=True)

    # 4.2 运行日志
    log_card, logs = theme.card(bottom, "运行日志", accent=theme.PRIMARY, pady=6)
    log_card.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
    log_bar = tk.Frame(logs, bg=theme.SURFACE)
    log_bar.pack(fill=tk.X, pady=(0, 4))
    lab_cap_status = theme.label(log_bar, "抓屏 · 已停止", fg=theme.AMBER, font_size=8)
    lab_cap_status.pack(side=tk.LEFT)
    btn_cap = theme.button(log_bar, "开启抓屏", color=theme.SLATE_BTN,
                           active=theme.SLATE_BTN_HOVER, width=8, state=tk.DISABLED, font_size=8, pady=2)
    btn_cap.pack(side=tk.RIGHT)
    txt_screen_log = scrolledtext.ScrolledText(logs, width=1, height=1, wrap=tk.WORD)
    _configure_text(txt_screen_log)
    txt_screen_log.pack(fill=tk.BOTH, expand=True)

    # 4.3 直播状态立体监视大屏（彻底激活原 200px 纯黑死区）
    stat_card, stats = theme.card(bottom, "直播状态", accent=theme.PRIMARY, pady=6)
    stat_card.grid(row=0, column=2, sticky="nsew")

    status_line = tk.Frame(stats, bg=theme.SURFACE)
    status_line.pack(fill=tk.X, pady=(0, 5))
    lab_sys_status = theme.label(status_line, "待机 · 等待启动", fg=theme.GREEN,
                                 bold=True, font_size=9, anchor="w")
    lab_sys_status.pack(side=tk.LEFT)
    lab_danmu_status = theme.label(status_line, "弹幕采集 · 未启动", muted=True,
                                   font_size=8, anchor="e")
    lab_danmu_status.pack(side=tk.RIGHT)

    # 核心指标三联卡
    metric_strip = tk.Frame(stats, bg=theme.SURFACE)
    metric_strip.pack(fill=tk.X, pady=(0, 6))

    def _metric(title, initial, color):
        cell = tk.Frame(metric_strip, bg=theme.SURFACE_ALT)
        cell.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        theme.label(cell, title, muted=True, font_size=7, bg=theme.SURFACE_ALT).pack(pady=(4, 0))
        value = theme.label(cell, initial, fg=color, bold=True, font_size=11, bg=theme.SURFACE_ALT)
        value.pack(pady=(0, 4))
        return value

    lab_online = _metric("实时在线", "0 人", theme.CYAN)
    lab_like = _metric("累计点赞", "0", theme.PURPLE)
    lab_gift = _metric("礼物互动", "0", theme.AMBER)

    # 系统链路监视面板（展示核心四大链路状态，消除空洞）
    link_frame = tk.Frame(stats, bg=theme.SURFACE_ALT, padx=8, pady=5)
    link_frame.pack(fill=tk.X, pady=(0, 6))
    theme.label(link_frame, "系统链路监视", bold=True, font_size=8, fg=theme.TEXT_SOFT, bg=theme.SURFACE_ALT).pack(fill=tk.X, pady=(0, 3))

    def _link_row(parent, icon, name, initial_tag, tag_color):
        row_f = tk.Frame(parent, bg=theme.SURFACE_ALT)
        row_f.pack(fill=tk.X, pady=1)
        theme.label(row_f, f"{icon} {name}", muted=True, font_size=8, bg=theme.SURFACE_ALT).pack(side=tk.LEFT)
        tag = theme.pill(row_f, initial_tag, bg=theme.SURFACE_SOFT, fg=tag_color, font_size=7, bold=True)
        tag.pack(side=tk.RIGHT)
        return tag

    _link_row(link_frame, "📱", "手机投屏链路", "等待连接", theme.AMBER)
    _link_row(link_frame, "🎙️", "豆包对话交互", "前台就绪", theme.GREEN)
    _link_row(link_frame, "🤖", "AI 弹幕回复", "智能过滤", theme.CYAN)
    _link_row(link_frame, "🔈", "音频智能避让", "WASAPI 闪避", theme.PURPLE)

    # OBS 音频桥接卡片（提供推流配置提示与一键复制功能）
    obs_box = tk.Frame(stats, bg=theme.SURFACE_ALT, padx=8, pady=5)
    obs_box.pack(fill=tk.X)
    theme.label(obs_box, "OBS 浏览器音频源", bold=True, font_size=8, fg=theme.TEXT_SOFT, bg=theme.SURFACE_ALT).pack(fill=tk.X, pady=(0, 2))
    obs_row = tk.Frame(obs_box, bg=theme.SURFACE_ALT)
    obs_row.pack(fill=tk.X)
    obs_port = config.load_config().get("obs_audio_port", 8554)
    lbl_obs_link = theme.label(obs_row, f"http://127.0.0.1:{obs_port}/danmu_audio", fg=theme.CYAN, font_size=8, bg=theme.SURFACE_ALT)
    lbl_obs_link.pack(side=tk.LEFT)

    def _copy_obs_link():
        try:
            curr_port = config.load_config().get("obs_audio_port", 8554)
            curr_url = f"http://127.0.0.1:{curr_port}/danmu_audio"
            root.clipboard_clear()
            root.clipboard_append(curr_url)
            lbl_obs_link.config(text=curr_url)
            btn_copy_obs.config(text="已复制", fg=theme.GREEN)
            root.after(1500, lambda: btn_copy_obs.config(text="复制", fg=theme.TEXT))
        except Exception:
            pass

    btn_copy_obs = theme.button(obs_row, "复制", color=theme.SURFACE_SOFT,
                                active=theme.BORDER_FOCUS, font_size=7, padx=5, pady=0, command=_copy_obs_link)
    btn_copy_obs.pack(side=tk.RIGHT)

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

