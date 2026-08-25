# ====================== UI 界面构建（尺寸/文案完全与原版一致） ======================
# 所有控件作为模块级变量暴露（ui.root / ui.btn_power ...），供其他模块读写。
# 按钮的 command 不在本文件内绑定（避免循环依赖），由 main.py 统一接线。
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
from settings import config
# ---- 控件引用（build_ui 中赋值）----
root = None
lab_sys_status = None
lab_online = None
lab_like = None
lab_gift = None
lab_cap_status = None
lab_count = None
volume_canvas = None
lab_vad_state = None
embed_container = None
txt_danmu = None
txt_screen_log = None
txt_pre_meet = None
btn_power = None
btn_meet = None
btn_live_start = None
btn_live_stop = None
btn_audio_mode = None
btn_cap = None
btn_pwd = None
btn_auth = None
btn_save = None
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


def set_status(msg, color="#ff6b6b"):
    """线程安全地更新主界面状态栏；GUI 未就绪时退化为 print。"""
    try:
        root.after(0, lambda: lab_sys_status.config(text=msg, fg=color))
    except Exception:
        print("[状态]", msg)


def log_screen(msg):
    """线程安全地向屏幕日志文本框追加一行；GUI 未就绪时退化为 print。
    同时回显到控制台(stdout)，便于在 PyCharm / 终端直接观察所有日志
    （含启动 VAD 探针、直播实时 dB），无需切换到软件界面日志面板。"""
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
        pass  # 控制台已回显，GUI 未就绪时无需再打


def set_volume_meter(db, avg=None, speaking=False, silence_elapsed=None, silence_hold=None):
    """线程安全：根据实时分贝刷新音量指示条。
    db            —— 当前帧分贝(dBFS，约 -60~0)
    speaking      —— 是否正在说话(均值>阈值)
    silence_elapsed/silence_hold —— 静音已持续/需持续秒数(用于显示'X/Ys 跳下一句')
    条宽随音量大小变化、说话时绿色闪动；GUI 未就绪时静默跳过。"""
    try:
        # dB 映射到 0~1：约 -60dB→0， -10dB→1
        level = max(0.0, min(1.0, (float(db) + 60.0) / 50.0))
        w = int(240 * level)

        def _do():
            volume_canvas.delete("all")
            if speaking:
                # 说话中：绿色，亮度随音量(闪动感)
                fill = "#10b981" if level > 0.45 else "#34d399"
                volume_canvas.create_rectangle(0, 0, w, 16, fill=fill, outline="")
            else:
                volume_canvas.create_rectangle(0, 0, w, 16, fill="#374151", outline="")
            # 状态文字
            if speaking:
                lab_vad_state.config(text="🔊 说话中 (%.0fdB)" % db, fg="#34d399")
            elif silence_elapsed is not None and silence_hold is not None:
                lab_vad_state.config(text="🔇 静音 %.1f/%.1fs｜满跳下一句" % (silence_elapsed, silence_hold),
                                     fg="#fbbf24")
            else:
                lab_vad_state.config(text="🔇 监听中…", fg="#9ca3af")

        root.after(0, _do)
    except Exception:
        pass


def reset_volume_meter():
    """把音量指示条复位到空闲态。"""
    try:
        def _do():
            volume_canvas.delete("all")
            lab_vad_state.config(text="🔇 待机", fg="#9ca3af")
        root.after(0, _do)
    except Exception:
        pass


def build_ui():
    """构建全部界面，并把配置回填到控件。"""
    global root, lab_sys_status, lab_online, lab_like, lab_gift, lab_cap_status, lab_count
    global embed_container, txt_danmu, txt_screen_log, txt_pre_meet
    global btn_power, btn_meet, btn_live_start, btn_live_stop, btn_audio_mode, btn_cap
    global btn_pwd, btn_auth, btn_save
    global volume_canvas, lab_vad_state
    global ent_prod_name, ent_prod_desc, ent_r1min, ent_r1max, ent_cmd1
    global ent_r2min, ent_r2max, ent_cmd2, ent_r3min, ent_r3max, ent_cmd3, ent_interval

    root = tk.Tk()
    root.title("智播豆 · AI智能直播管控系统")
    root.geometry("1240x800")
    root.resizable(False, False)
    root.configure(bg="#111827")

    head_frame = tk.Frame(root, bg="#1f2937")
    head_frame.pack(fill=tk.X)
    tk.Label(head_frame, text="智播豆 · AI智能直播管控系统", font=("微软雅黑", 22, "bold"),
             bg="#1f2937", fg="#00e5ff").pack(pady=10)

    auth_frame = tk.LabelFrame(root, text=" 🔐系统授权 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    auth_frame.pack(fill=tk.X, padx=15, pady=4)
    auth_frame.grid_columnconfigure(8, weight=1)

    tk.Label(auth_frame, text="✅授权正常【测试版】", bg="#111827", fg="#34d399",
             font=("微软雅黑", 11, "bold")).grid(row=0, column=0, padx=12, pady=6)
    tk.Label(auth_frame, text="授权状态：永久测试", bg="#111827", fg="white").grid(row=0, column=1, padx=8, pady=6)
    btn_pwd = tk.Button(auth_frame, text="密码设置", bg="#374151", fg="white", width=9, command=None)
    btn_pwd.grid(row=0, column=2, padx=4, pady=6)
    btn_auth = tk.Button(auth_frame, text="授权管理", bg="#374151", fg="white", width=9, command=None)
    btn_auth.grid(row=0, column=3, padx=4, pady=6)

    btn_power = tk.Button(auth_frame, text="⏻", bg="#bb2222", fg="white", font=("Webdings", 14),
                          width=2, relief=tk.RAISED, command=None)
    btn_power.grid(row=0, column=8, sticky="e", padx=12, pady=6)

    main_all = tk.Frame(root, bg="#111827")
    main_all.pack(fill=tk.BOTH, expand=True, padx=15, pady=4)

    ui_left = tk.Frame(main_all, bg="#111827", width=310)
    ui_left.pack(side=tk.LEFT, fill=tk.Y)

    embed_gb = tk.LabelFrame(ui_left, text=" 📱手机投屏内嵌容器 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    embed_gb.pack(fill=tk.Y)

    embed_container = tk.Frame(embed_gb, bg="#000000", width=290, height=530)
    embed_container.pack(padx=5, pady=5)

    ui_right = tk.Frame(main_all, bg="#111827")
    ui_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)

    cfg_gb = tk.LabelFrame(ui_right, text=" 📦产品配置 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    cfg_gb.pack(fill=tk.X, pady=3)
    tk.Label(cfg_gb, text="产品名称", bg="#111827", fg="white").grid(row=0, column=0, padx=5, pady=4)
    ent_prod_name = tk.Entry(cfg_gb, bg="#1f2937", fg="white")
    ent_prod_name.grid(row=0, column=1, padx=4, pady=4)
    tk.Label(cfg_gb, text="产品描述", bg="#111827", fg="white").grid(row=0, column=2, padx=5, pady=4)
    ent_prod_desc = tk.Entry(cfg_gb, bg="#1f2937", fg="white")
    ent_prod_desc.grid(row=0, column=3, padx=4, pady=4)
    btn_save = tk.Button(cfg_gb, text="💾保存配置", bg="#374151", fg="white", command=None)
    btn_save.grid(row=0, column=4, padx=8, pady=4)

    meet_gb = tk.LabelFrame(ui_right, text=" 🎤开播预演 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    meet_gb.pack(fill=tk.X, pady=3)
    txt_pre_meet = scrolledtext.ScrolledText(meet_gb, height=3, bg="#1f2937", fg="white")
    txt_pre_meet.pack(fill=tk.X, padx=4, pady=3)
    btn_meet = tk.Button(meet_gb, text="💬执行开播预演", bg="#374151", fg="white",
                         state=tk.DISABLED, command=None)
    btn_meet.pack(pady=2)

    script_gb = tk.LabelFrame(ui_right, text=" 📜区间话术设置 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    script_gb.pack(fill=tk.X, pady=3)

    tk.Label(script_gb, text="区间1(0~30)", bg="#111827", fg="white").grid(row=0, column=0, padx=3, pady=2)
    ent_r1min = tk.Entry(script_gb, width=4, bg="#1f2937", fg="white"); ent_r1min.grid(row=0, column=1, padx=2, pady=2)
    tk.Label(script_gb, text="~", bg="#111827", fg="white").grid(row=0, column=2)
    ent_r1max = tk.Entry(script_gb, width=4, bg="#1f2937", fg="white"); ent_r1max.grid(row=0, column=3, padx=2, pady=2)
    ent_cmd1 = tk.Entry(script_gb, width=40, bg="#1f2937", fg="white"); ent_cmd1.grid(row=0, column=4, padx=4, pady=2)

    tk.Label(script_gb, text="区间2(30~100)", bg="#111827", fg="white").grid(row=1, column=0, padx=3, pady=2)
    ent_r2min = tk.Entry(script_gb, width=4, bg="#1f2937", fg="white"); ent_r2min.grid(row=1, column=1, padx=2, pady=2)
    tk.Label(script_gb, text="~", bg="#111827", fg="white").grid(row=1, column=2)
    ent_r2max = tk.Entry(script_gb, width=4, bg="#1f2937", fg="white"); ent_r2max.grid(row=1, column=3, padx=2, pady=2)
    ent_cmd2 = tk.Entry(script_gb, width=40, bg="#1f2937", fg="white"); ent_cmd2.grid(row=1, column=4, padx=4, pady=2)

    tk.Label(script_gb, text="区间3(100+)", bg="#111827", fg="white").grid(row=2, column=0, padx=3, pady=2)
    ent_r3min = tk.Entry(script_gb, width=4, bg="#1f2937", fg="white"); ent_r3min.grid(row=2, column=1, padx=2, pady=2)
    tk.Label(script_gb, text="~", bg="#111827", fg="white").grid(row=2, column=2)
    ent_r3max = tk.Entry(script_gb, width=4, bg="#1f2937", fg="white"); ent_r3max.grid(row=2, column=3, padx=2, pady=2)
    ent_cmd3 = tk.Entry(script_gb, width=40, bg="#1f2937", fg="white"); ent_cmd3.grid(row=2, column=4, padx=4, pady=2)

    tk.Label(script_gb, text="执行间隔(秒)", bg="#111827", fg="white").grid(row=3, column=0, padx=3, pady=2)
    ent_interval = tk.Entry(script_gb, width=6, bg="#1f2937", fg="white"); ent_interval.grid(row=3, column=1, padx=2, pady=2)

    ctrl_gb = tk.LabelFrame(ui_right, text=" 🎮直播控制 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    ctrl_gb.pack(fill=tk.X, pady=3)
    btn_audio_mode = tk.Button(ctrl_gb, text="🔊外音模式(TTS语音)", bg="#06d6a0", fg="black", width=18,
                               state=tk.DISABLED, command=None)
    btn_audio_mode.grid(row=0, column=0, padx=4, pady=4)
    btn_live_start = tk.Button(ctrl_gb, text="▶启动直播", bg="#10b981", fg="black", width=12,
                               state=tk.DISABLED, command=None)
    btn_live_start.grid(row=0, column=1, padx=4, pady=4)
    btn_live_stop = tk.Button(ctrl_gb, text="⏹停止直播", bg="#ef4444", fg="white", width=12,
                              state=tk.DISABLED, command=None)
    btn_live_stop.grid(row=0, column=2, padx=4, pady=4)
    lab_count = tk.Label(ctrl_gb, text="✅可以执行下一轮", bg="#111827", fg="#00e5ff")
    lab_count.grid(row=0, column=3, padx=10, pady=4)

    # 实时音量指示条：随豆包音量大小闪动；静音时显示"X/Ys 跳下一句"
    vol_frame = tk.Frame(ctrl_gb, bg="#111827")
    vol_frame.grid(row=1, column=0, columnspan=4, sticky="we", padx=4, pady=(2, 6))
    tk.Label(vol_frame, text="🔊音量", bg="#111827", fg="#9ca3af", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=2)
    volume_canvas = tk.Canvas(vol_frame, width=240, height=16, bg="#1f2937", highlightthickness=0)
    volume_canvas.pack(side=tk.LEFT, padx=4)
    lab_vad_state = tk.Label(vol_frame, text="🔇 待机", bg="#111827", fg="#9ca3af",
                             font=("微软雅黑", 9), width=26, anchor="w")
    lab_vad_state.pack(side=tk.LEFT, padx=4)

    bottom_container = tk.Frame(ui_right, bg="#111827")
    bottom_container.pack(fill=tk.BOTH, expand=True)
    bot_left = tk.Frame(bottom_container, bg="#111827")
    bot_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    bot_right = tk.Frame(bottom_container, bg="#111827", width=270)
    bot_right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=5)

    stat_gb = tk.LabelFrame(bot_right, text=" 📊实时数据 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    stat_gb.pack(fill=tk.BOTH, expand=True)
    lab_sys_status = tk.Label(stat_gb, text="状态：待机【测试】✅", bg="#111827", fg="#34d399", font=("微软雅黑", 11, "bold"))
    lab_sys_status.pack(pady=4)
    lab_online = tk.Label(stat_gb, text="📶 在线：0 人", bg="#111827", fg="white"); lab_online.pack(pady=2)
    lab_like = tk.Label(stat_gb, text="👍 点赞：0", bg="#111827", fg="white"); lab_like.pack(pady=2)
    lab_gift = tk.Label(stat_gb, text="🎁礼物：0", bg="#111827", fg="white"); lab_gift.pack(pady=2)

    danmu_gb = tk.LabelFrame(bot_left, text=" 💬弹幕消息 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    danmu_gb.pack(fill=tk.BOTH, expand=True, pady=2)
    txt_danmu = scrolledtext.ScrolledText(danmu_gb, bg="#1f2937", fg="white")
    txt_danmu.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

    cap_gb = tk.LabelFrame(bot_left, text=" 📸抓屏日志 ", bg="#111827", fg="#00e5ff", font=("微软雅黑", 10))
    cap_gb.pack(fill=tk.X, pady=2)
    cap_bar = tk.Frame(cap_gb, bg="#111827")
    cap_bar.pack(fill=tk.X)
    lab_cap_status = tk.Label(cap_bar, text="抓屏：已停止 ⏸️", bg="#111827", fg="#fbbf24")
    lab_cap_status.pack(side=tk.LEFT, padx=5)
    btn_cap = tk.Button(cap_bar, text="开启抓屏", bg="#374151", fg="white", width=8,
                        state=tk.DISABLED, command=None)
    btn_cap.pack(side=tk.RIGHT, padx=5)
    txt_screen_log = scrolledtext.ScrolledText(cap_gb, height=4, bg="#1f2937", fg="white")
    txt_screen_log.pack(fill=tk.X, padx=3, pady=3)

    foot = tk.Frame(root, bg="#1f2937")
    foot.pack(fill=tk.X)
    tk.Label(foot, text="杭州智鑫科技 ©智播豆AI直播管控系统", bg="#1f2937", fg="#9ca3af").pack(pady=6)

    # 加载配置回填 UI
    cfg_load = config.load_config()
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
