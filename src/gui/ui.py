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
btn_audio_mode = None
btn_cap = None
btn_pwd = None
btn_auth = None
btn_save = None
btn_danmu = None
cmb_danmu_platform = None
ent_danmu_url = None
var_danmu_headless = None
ent_prod_name = None
ent_prod_desc = None
ent_r1min = None
ent_r1max = None
ent_cmd1 = None
ent_r2min = None
ent_r2max = None
ent_cmd2 = None
ent_r3min = None
ent_r3max = None
ent_cmd3 = None
ent_interval = None


# VAD 每秒约 50 帧；工作线程只覆盖最新值，由 Tk 主线程以 20 FPS 合并绘制。
_volume_lock = threading.Lock()
_volume_latest = None
_volume_peak_db = -100.0
_volume_poll_started = False


def set_status(msg, color=theme.RED):
    """线程安全更新主界面状态；GUI 未就绪时退化为控制台日志。"""
    try:
        root.after(0, lambda: lab_sys_status.config(text=msg, fg=color))
    except Exception:
        print("[状态]", msg)


def log_screen(msg):
    """线程安全追加运行日志，并同步回显到控制台。"""
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
    global _volume_latest, _volume_peak_db
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
            if root and root.winfo_exists():
                root.after(50, _poll_volume_meter)
        except tk.TclError:
            pass


def reset_volume_meter():
    global _volume_latest
    with _volume_lock:
        _volume_latest = "reset"


def _section_label(parent, text, row, column, **grid):
    widget = theme.label(parent, text, fg=theme.TEXT_SOFT, font_size=10, anchor="w")
    widget.grid(row=row, column=column, **grid)
    return widget


def _configure_text(widget):
    widget.configure(
        bg=theme.SURFACE_ALT, fg=theme.TEXT_SOFT, insertbackground=theme.CYAN,
        selectbackground=theme.PRIMARY, selectforeground="#FFFFFF",
        relief=tk.FLAT, bd=0, highlightthickness=1,
        highlightbackground=theme.BORDER, highlightcolor=theme.BORDER_FOCUS,
        font=theme.font(10), padx=8, pady=6,
    )


def build_ui():
    """构建统一深色品牌主控台，并回填业务配置。"""
    global root, lab_sys_status, lab_online, lab_like, lab_gift, lab_cap_status
    global lab_count, lab_danmu_status, lab_auth_status, lab_auth_detail
    global embed_container, txt_danmu, txt_screen_log, txt_pre_meet
    global btn_power, btn_meet, btn_live_start, btn_live_stop, btn_audio_mode, btn_cap
    global btn_pwd, btn_auth, btn_save, btn_danmu, btn_logout
    global cmb_danmu_platform, ent_danmu_url, var_danmu_headless
    global volume_canvas, lab_vad_state, _volume_poll_started
    global ent_prod_name, ent_prod_desc, ent_r1min, ent_r1max, ent_cmd1
    global ent_r2min, ent_r2max, ent_cmd2, ent_r3min, ent_r3max, ent_cmd3, ent_interval

    root = tk.Tk()
    root.title("智播豆 · AI 智能直播工作台")
    root.geometry("1280x800")
    root.minsize(1180, 760)
    root.configure(bg=theme.BG)
    theme.configure_ttk(root)

    header = tk.Canvas(root, height=64, bg=theme.BG, bd=0, highlightthickness=0)
    header.pack(fill=tk.X)
    header.pack_propagate(False)

    def _paint_header(event):
        w, h = event.width, event.height
        theme.draw_horizontal_gradient(header, w, h, "#182443", "#16465B")
        header.delete("header-fg")
        header.create_oval(24, 16, 64, 56, outline=theme.CYAN, width=2, tags="header-fg")
        header.create_text(44, 36, text="ZD", fill=theme.TEXT,
                           font=(theme.FONT_EN, 12, "bold"), tags="header-fg")
        header.create_text(82, 27, text="智播豆  ·  AI 智能直播工作台",
                           fill=theme.TEXT, anchor="w", font=theme.font(18, "bold"), tags="header-fg")
        header.create_text(83, 50, text="ZHIBODOU LIVE OPERATIONS CONSOLE",
                           fill=theme.TEXT_MUTED, anchor="w", font=(theme.FONT_EN, 8), tags="header-fg")
        header.create_text(w - 24, 36, text="DESKTOP  v1.7.0",
                           fill=theme.TEXT_MUTED, anchor="e", font=(theme.FONT_EN, 9, "bold"), tags="header-fg")

    header.bind("<Configure>", _paint_header)

    auth_outer = tk.Frame(root, bg=theme.BORDER)
    auth_outer.pack(fill=tk.X, padx=16, pady=(8, 5))
    auth_frame = tk.Frame(auth_outer, bg=theme.SURFACE, height=50)
    auth_frame.pack(fill=tk.X, padx=1, pady=1)
    auth_frame.pack_propagate(False)

    try:
        from pdk import auth_service as pdk_auth
        auth_result = pdk_auth.current_auth()
    except Exception:
        auth_result = None
    auth_ok = auth_result is not None

    status_dot = tk.Canvas(auth_frame, width=18, height=18, bg=theme.SURFACE,
                           bd=0, highlightthickness=0)
    status_dot.pack(side=tk.LEFT, padx=(16, 8))
    status_dot.create_oval(4, 4, 14, 14, fill=theme.GREEN if auth_ok else theme.RED, outline="")
    lab_auth_status = theme.label(
        auth_frame, "PDK 授权已验证" if auth_ok else "PDK 未授权",
        fg=theme.GREEN if auth_ok else theme.RED, bold=True, font_size=10,
    )
    lab_auth_status.pack(side=tk.LEFT)
    tk.Frame(auth_frame, bg=theme.BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, padx=14, pady=12)
    lab_auth_detail = theme.label(
        auth_frame, auth_result.display_detail() if auth_ok else "请重新登录",
        muted=True, font_size=10, anchor="w",
    )
    lab_auth_detail.pack(side=tk.LEFT, fill=tk.X, expand=True)
    btn_logout = theme.button(auth_frame, "退出", color=theme.SURFACE_SOFT,
                              active=theme.BORDER_FOCUS, width=8)
    btn_logout.pack(side=tk.RIGHT, padx=(6, 14), pady=9)
    btn_power = theme.button(auth_frame, "电源", color=theme.RED_DARK,
                             active=theme.RED, width=8)
    btn_power.pack(side=tk.RIGHT, padx=4, pady=9)
    btn_auth = theme.button(auth_frame, "许可证", color=theme.SURFACE_SOFT,
                            active=theme.BORDER_FOCUS, width=8)
    btn_auth.pack(side=tk.RIGHT, padx=4, pady=9)
    btn_pwd = theme.button(auth_frame, "账户资料", color=theme.SURFACE_SOFT,
                           active=theme.BORDER_FOCUS, width=8)
    btn_pwd.pack(side=tk.RIGHT, padx=4, pady=9)

    # 先预留底栏空间，避免主内容在较矮屏幕上把底栏挤出可视区域。
    footer = tk.Frame(root, bg=theme.BG_ELEVATED, height=28)
    footer.pack(side=tk.BOTTOM, fill=tk.X)
    footer.pack_propagate(False)
    theme.label(footer, "杭州智鑫科技  ·  智播豆 AI 直播管控系统",
                muted=True, font_size=9, bg=theme.BG_ELEVATED).pack(side=tk.LEFT, padx=18, pady=5)
    theme.label(footer, "LOCAL DESKTOP · SECURE SESSION",
                muted=True, font_size=9, bg=theme.BG_ELEVATED).pack(side=tk.RIGHT, padx=18, pady=5)

    main_all = tk.Frame(root, bg=theme.BG)
    main_all.pack(fill=tk.BOTH, expand=True, padx=16, pady=(2, 8))

    ui_left = tk.Frame(main_all, bg=theme.BG, width=300)
    ui_left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
    ui_left.pack_propagate(False)
    device_card, device_body = theme.card(ui_left, "设备画面 · 音频链路", accent=theme.PRIMARY)
    device_card.pack(fill=tk.BOTH, expand=True)
    theme.label(device_body, "SCRCPY DEVICE CHANNEL", muted=True,
                font_size=9, anchor="w").pack(fill=tk.X, pady=(0, 7))
    embed_container = tk.Frame(
        device_body, bg="#02070D", bd=0,
        highlightthickness=1, highlightbackground=theme.BORDER,
    )
    embed_container.pack(fill=tk.BOTH, expand=True)
    theme.label(
        device_body, "设备连接后将在此显示 · 音频由 CABLE 路由至 VAD",
        muted=True, font_size=9, anchor="center",
    ).pack(fill=tk.X, pady=(8, 0))

    ui_right = tk.Frame(main_all, bg=theme.BG)
    ui_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    cfg_card, cfg = theme.card(ui_right, "产品与弹幕配置", accent=theme.PRIMARY, pady=8)
    cfg_card.pack(fill=tk.X, pady=(0, 6))
    cfg.grid_columnconfigure(1, weight=1)
    cfg.grid_columnconfigure(3, weight=2)
    _section_label(cfg, "产品名称", 0, 0, padx=(0, 8), pady=4, sticky="w")
    ent_prod_name = theme.entry(cfg)
    ent_prod_name.grid(row=0, column=1, padx=(0, 12), pady=3, sticky="ew", ipady=3)
    _section_label(cfg, "产品描述", 0, 2, padx=(0, 8), pady=4, sticky="w")
    ent_prod_desc = theme.entry(cfg)
    ent_prod_desc.grid(row=0, column=3, padx=(0, 10), pady=3, sticky="ew", ipady=3)
    btn_save = theme.button(cfg, "保存配置", color=theme.PRIMARY,
                            active=theme.PRIMARY_HOVER, width=9)
    btn_save.grid(row=0, column=4, pady=4, sticky="e")

    _section_label(cfg, "弹幕平台", 1, 0, padx=(0, 8), pady=4, sticky="w")
    cmb_danmu_platform = ttk.Combobox(
        cfg, style="Zhibodou.TCombobox",
        values=("douyin", "kuaishou", "bili", "tiktok", "shipinhao", "xhs", "tb", "pdd", "facebook"),
        width=12, state="readonly",
    )
    cmb_danmu_platform.grid(row=1, column=1, padx=(0, 12), pady=4, sticky="w")
    _section_label(cfg, "直播间", 1, 2, padx=(0, 8), pady=4, sticky="w")
    ent_danmu_url = theme.entry(cfg)
    ent_danmu_url.grid(row=1, column=3, padx=(0, 10), pady=3, sticky="ew", ipady=3)
    actions = tk.Frame(cfg, bg=theme.SURFACE)
    actions.grid(row=1, column=4, pady=4, sticky="e")
    var_danmu_headless = tk.BooleanVar(value=True)
    tk.Checkbutton(
        actions, text="无窗口", variable=var_danmu_headless,
        bg=theme.SURFACE, fg=theme.TEXT_SOFT, selectcolor=theme.SURFACE_ALT,
        activebackground=theme.SURFACE, activeforeground=theme.TEXT,
        highlightthickness=0, bd=0, font=theme.font(10),
    ).pack(side=tk.LEFT, padx=(0, 6))
    btn_danmu = theme.button(actions, "启动弹幕", color=theme.PRIMARY,
                             active=theme.PRIMARY_HOVER, width=9)
    btn_danmu.pack(side=tk.LEFT)

    # 两块策略内容并排，既保留完整信息密度，也让 800px 高度的常见屏幕
    # 能完整看到实时弹幕、运行日志与直播状态。
    strategy_row = tk.Frame(ui_right, bg=theme.BG)
    strategy_row.pack(fill=tk.X, pady=(0, 6))
    strategy_row.grid_columnconfigure(0, weight=2, uniform="strategy")
    strategy_row.grid_columnconfigure(1, weight=3, uniform="strategy")

    meet_card, meet = theme.card(strategy_row, "开播预演", accent=theme.PRIMARY, pady=8)
    meet_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    txt_pre_meet = scrolledtext.ScrolledText(meet, height=2, wrap=tk.WORD)
    _configure_text(txt_pre_meet)
    txt_pre_meet.pack(fill=tk.BOTH, expand=True)
    btn_meet = theme.button(meet, "执行预演", color=theme.PRIMARY, active=theme.PRIMARY_HOVER,
                            width=9, state=tk.DISABLED)
    btn_meet.pack(anchor="e", pady=(8, 0))

    script_card, scripts = theme.card(strategy_row, "区间话术策略", accent=theme.PRIMARY, pady=8)
    script_card.grid(row=0, column=1, sticky="nsew")
    scripts.grid_columnconfigure(4, weight=1)
    script_rows = (("区间 01", "0", "30"), ("区间 02", "30", "100"), ("区间 03", "100", "9999"))
    script_entries = []
    for row, (title, _start, _end) in enumerate(script_rows):
        _section_label(scripts, title, row, 0, padx=(0, 8), pady=2, sticky="w")
        start_entry = theme.entry(scripts, width=5)
        start_entry.grid(row=row, column=1, pady=2, sticky="w", ipady=2)
        theme.label(scripts, "—", muted=True).grid(row=row, column=2, padx=6)
        end_entry = theme.entry(scripts, width=5)
        end_entry.grid(row=row, column=3, pady=2, sticky="w", ipady=2)
        command_entry = theme.entry(scripts)
        command_entry.grid(row=row, column=4, padx=(10, 0), pady=2, sticky="ew", ipady=2)
        script_entries.append((start_entry, end_entry, command_entry))
    (ent_r1min, ent_r1max, ent_cmd1), (ent_r2min, ent_r2max, ent_cmd2), \
        (ent_r3min, ent_r3max, ent_cmd3) = script_entries
    _section_label(scripts, "执行间隔", 3, 0, padx=(0, 8), pady=(3, 0), sticky="w")
    ent_interval = theme.entry(scripts, width=5)
    ent_interval.grid(row=3, column=1, pady=(3, 0), sticky="w", ipady=2)
    theme.label(scripts, "秒 · 下一句仍由 VAD 放行", muted=True, font_size=8).grid(
        row=3, column=2, columnspan=3, padx=6, pady=(3, 0), sticky="w")

    ctrl_card, controls = theme.card(ui_right, "直播控制与音频活动", accent=theme.PRIMARY, pady=8)
    ctrl_card.pack(fill=tk.X, pady=(0, 6))
    btn_audio_mode = theme.button(controls, "外音模式 · TTS", color=theme.SURFACE_SOFT,
                                  active=theme.BORDER_FOCUS, width=15, state=tk.DISABLED)
    btn_audio_mode.grid(row=0, column=0, padx=(0, 8), pady=2)
    btn_live_start = theme.button(controls, "启动直播", color="#16845A",
                                  active=theme.GREEN, width=10, state=tk.DISABLED)
    btn_live_start.grid(row=0, column=1, padx=4, pady=2)
    btn_live_stop = theme.button(controls, "停止直播", color=theme.RED_DARK,
                                 active=theme.RED, width=10, state=tk.DISABLED)
    btn_live_stop.grid(row=0, column=2, padx=4, pady=2)
    lab_count = theme.label(controls, "下一轮 · 已就绪", fg=theme.CYAN,
                            bold=True, font_size=9, anchor="w")
    lab_count.grid(row=0, column=3, padx=(14, 0), sticky="w")
    controls.grid_columnconfigure(3, weight=1)

    meter_row = tk.Frame(controls, bg=theme.SURFACE)
    meter_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 0))
    theme.label(meter_row, "VAD", muted=True, bold=True, font_size=8).pack(side=tk.LEFT, padx=(0, 8))
    volume_canvas = tk.Canvas(meter_row, width=300, height=14, bg=theme.SURFACE_SOFT,
                              bd=0, highlightthickness=0)
    volume_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
    lab_vad_state = theme.label(meter_row, "待机 · 等待音频", muted=True,
                                font_size=9, width=25, anchor="w")
    lab_vad_state.pack(side=tk.LEFT, padx=(10, 0))
    root.after_idle(lambda: _draw_meter_fill(0, theme.TEXT_FAINT))
    if not _volume_poll_started:
        _volume_poll_started = True
        root.after(50, _poll_volume_meter)

    bottom = tk.Frame(ui_right, bg=theme.BG)
    bottom.pack(fill=tk.BOTH, expand=True)
    bottom.grid_columnconfigure(0, weight=3, uniform="bottom")
    bottom.grid_columnconfigure(1, weight=2, uniform="bottom")
    bottom.grid_columnconfigure(2, weight=2, uniform="bottom")
    bottom.grid_rowconfigure(0, weight=1)

    feed_card, feed = theme.card(bottom, "实时弹幕", accent=theme.PRIMARY)
    feed_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    # width=1 阻止 Text 的默认 80 字符请求宽度挤压相邻状态卡。
    txt_danmu = scrolledtext.ScrolledText(feed, width=1, height=1, wrap=tk.WORD)
    _configure_text(txt_danmu)
    txt_danmu.pack(fill=tk.BOTH, expand=True)

    log_card, logs = theme.card(bottom, "运行日志", accent=theme.PRIMARY, pady=8)
    log_card.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
    log_bar = tk.Frame(logs, bg=theme.SURFACE)
    log_bar.pack(fill=tk.X, pady=(0, 5))
    lab_cap_status = theme.label(log_bar, "抓屏 · 已停止", fg=theme.AMBER, font_size=8)
    lab_cap_status.pack(side=tk.LEFT)
    btn_cap = theme.button(log_bar, "开启抓屏", color=theme.SURFACE_SOFT,
                           active=theme.BORDER_FOCUS, width=8, state=tk.DISABLED, font_size=8)
    btn_cap.pack(side=tk.RIGHT)
    txt_screen_log = scrolledtext.ScrolledText(logs, width=1, height=1, wrap=tk.WORD)
    _configure_text(txt_screen_log)
    txt_screen_log.pack(fill=tk.BOTH, expand=True)

    stat_card, stats = theme.card(bottom, "直播状态", accent=theme.PRIMARY, pady=8)
    stat_card.grid(row=0, column=2, sticky="nsew")
    status_line = tk.Frame(stats, bg=theme.SURFACE)
    status_line.pack(fill=tk.X, pady=(0, 6))
    lab_sys_status = theme.label(status_line, "待机 · 等待启动", fg=theme.GREEN,
                                 bold=True, font_size=10, anchor="w")
    lab_sys_status.pack(side=tk.LEFT)
    lab_danmu_status = theme.label(status_line, "弹幕采集 · 未启动", muted=True,
                                   font_size=8, anchor="e")
    lab_danmu_status.pack(side=tk.RIGHT)

    metric_strip = tk.Frame(stats, bg=theme.SURFACE)
    metric_strip.pack(fill=tk.X)

    def _metric(title, initial, color):
        cell = tk.Frame(metric_strip, bg=theme.SURFACE_ALT)
        cell.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        theme.label(cell, title, muted=True, font_size=7, bg=theme.SURFACE_ALT).pack(pady=(3, 0))
        value = theme.label(cell, initial, fg=color, bold=True, font_size=10, bg=theme.SURFACE_ALT)
        value.pack(pady=(0, 3))
        return value

    lab_online = _metric("实时在线", "0 人", theme.CYAN)
    lab_like = _metric("累计点赞", "0", theme.PURPLE)
    lab_gift = _metric("礼物互动", "0", theme.AMBER)

    cfg_load = config.load_config()
    danmu_platform = str(cfg_load.get("danmu_platform") or "douyin")
    danmu_urls = cfg_load.get("danmu_urls") or {}
    danmu_url = str(cfg_load.get("danmu_url") or danmu_urls.get(danmu_platform) or "")
    cmb_danmu_platform.set(danmu_platform)
    ent_danmu_url.insert(0, danmu_url)
    var_danmu_headless.set(bool(cfg_load.get("danmu_headless", True)))

    def _platform_changed(_event=None):
        current = ent_danmu_url.get().strip()
        if not current or current in set(danmu_urls.values()):
            ent_danmu_url.delete(0, tk.END)
            ent_danmu_url.insert(0, danmu_urls.get(cmb_danmu_platform.get(), ""))

    cmb_danmu_platform.bind("<<ComboboxSelected>>", _platform_changed)
    ent_prod_name.insert(0, cfg_load["product_name"])
    ent_prod_desc.insert(0, cfg_load["product_desc"])
    txt_pre_meet.insert(tk.END, cfg_load["pre_meet_text"])
    ent_r1min.insert(0, cfg_load["r1_min"])
    ent_r1max.insert(0, cfg_load["r1_max"])
    ent_cmd1.insert(0, cfg_load["cmd1"])
    ent_r2min.insert(0, cfg_load["r2_min"])
    ent_r2max.insert(0, cfg_load["r2_max"])
    ent_cmd2.insert(0, cfg_load["cmd2"])
    ent_r3min.insert(0, cfg_load["r3_min"])
    ent_r3max.insert(0, cfg_load["r3_max"])
    ent_cmd3.insert(0, cfg_load["cmd3"])
    ent_interval.insert(0, cfg_load["script_interval"])
