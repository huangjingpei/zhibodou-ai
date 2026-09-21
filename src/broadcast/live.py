import os, sys, time, threading, subprocess
import tkinter as tk
import tkinter.messagebox as messagebox

from core import state
from gui import theme, ui
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

can_next_speak = True
live_thread = None
_live_generation = 0
_vad_stop_event = None
_current_monitor = None
_round_lock = threading.Lock()


def _get_product_context() -> dict:
    """实时读取当前产品名称、产品描述（价格/物流/优惠）与开播背景设定。

    优先从界面控件实时提取（输入即生效，无需手动保存配置），未构建时从配置文件读取。
    """
    cfg = config.load_config()
    prod_name = str(cfg.get("product_name") or "").strip()
    prod_desc = str(cfg.get("product_desc") or "").strip()
    pre_meet = str(cfg.get("pre_meet_text") or "").strip()

    try:
        from gui import ui as _ui
        if getattr(_ui, "ent_prod_name", None) is not None:
            v = str(_ui.ent_prod_name.get() or "").strip()
            if v:
                prod_name = v
        if getattr(_ui, "ent_prod_desc", None) is not None:
            v = str(_ui.ent_prod_desc.get() or "").strip()
            if v:
                prod_desc = v
        if getattr(_ui, "txt_pre_meet", None) is not None:
            import tkinter as _tk
            v = str(_ui.txt_pre_meet.get(1.0, _tk.END) or "").strip()
            if v:
                pre_meet = v
    except Exception:
        pass

    return {
        "product_name": prod_name,
        "product_desc": prod_desc,
        "pre_meet_text": pre_meet,
    }


def build_doubao_host_prompt(content: str, is_pre_meet: bool = False) -> str:
    """给每次豆包请求统一添加主播角色约束、商品背景认知（名称/价格/物流等）以及本次话术要求。

    1. 角色与格式约束：严格主播口吻、只出正文、绝不对话、禁止多余说明；
    2. 语言约束：普通话或指定方言；
    3. 商品与背景信息（Pretrain / 知识告知）：注入产品名称、产品描述（含价格/物流/规格/福利）、开播背景告知；
    4. 本次具体话术要求：区间01留人、区间02讲解、区间03逼单或预演要求。
    """
    content = str(content or "").strip()
    host_prompt = str(
        config.load_config().get("doubao_host_prompt")
        or config.DEFAULT_CFG["doubao_host_prompt"]
    ).strip()

    lang = ""
    try:
        from gui import ui as _ui
        widget = getattr(_ui, "cmb_doubao_lang", None)
        if widget is not None:
            lang = str(widget.get() or "").strip()
    except Exception:
        lang = ""
    if not lang:
        lang = str(config.load_config().get("doubao_language")
                   or config.DEFAULT_CFG.get("doubao_language") or "普通话").strip()

    if lang and lang != "普通话":
        lang_rule = (
            "\n【语言要求】全程使用「%s」进行播报，发音、用词、语气都要符合"
            "该语言/方言的地道表达习惯；如果是方言，请用该方言的口语直接说，"
            "不要中途切回普通话，也不要用文字标注发音。" % lang
        )
    else:
        lang_rule = "\n【语言要求】全程使用标准普通话播报。"

    # 提取实时商品与背景知识
    ctx = _get_product_context()
    prod_name = ctx["product_name"]
    prod_desc = ctx["product_desc"]
    pre_meet = ctx["pre_meet_text"]

    context_lines = []
    if prod_name:
        context_lines.append("- 推广商品名称：%s" % prod_name)
    if prod_desc:
        context_lines.append("- 商品详情/价格/物流与优惠：%s" % prod_desc)
    if pre_meet and not is_pre_meet:
        # 如果是正式直播，把开播预演背景一并作为全局指导注入
        context_lines.append("- 直播间背景与总体指导：%s" % pre_meet)

    if context_lines:
        bg_section = (
            "\n\n【本场直播商品与背景信息（请务必在话术中自然融入商品名称、价格、优惠与物流保障等核心卖点）】\n"
            + "\n".join(context_lines)
        )
    else:
        bg_section = ""

    task_title = "【开播预演试播要求】" if is_pre_meet else "【本次直播话术要求】"
    return "%s%s%s\n\n%s请结合上述商品信息与价格物流细节，直接输出播报正文：%s" % (
        host_prompt,
        lang_rule,
        bg_section,
        task_title,
        content,
    )


def _read_vad_config():
    cfg = config.load_config()
    return {
        "silence_hold": max(1.5, float(cfg.get("vad_silence_hold_sec", 4.0) or 4.0)),
        "wait_start": max(10.0, float(cfg.get("vad_wait_start_sec", 25.0) or 25.0)),
        "speak_confirm": max(0.1, float(cfg.get("vad_speak_confirm_sec", 0.3) or 0.3)),
        "energy_threshold": float(cfg.get("vad_energy_threshold_db", -42.0) or -42.0),
        "noise_margin": max(3.0, float(cfg.get("vad_noise_margin_db", 6.0) or 6.0)),
        "end_hysteresis": max(1.0, float(cfg.get("vad_end_hysteresis_db", 3.0) or 3.0)),
        "calibration": max(0.3, float(cfg.get("vad_calibration_sec", 0.8) or 0.8)),
        "calibration_wait": max(1.0, float(cfg.get("vad_calibration_wait_sec", 3.0) or 3.0)),
    }


def _get_active_script_config():
    """实时读取当前话术与区间配置（优先从界面输入框读取，支持即改即播）。"""
    cfg = config.load_config()
    res = {
        "r1_min": str(cfg.get("r1_min", "0")),
        "r1_max": str(cfg.get("r1_max", "30")),
        "cmd1": str(cfg.get("cmd1", "")),
        "r2_min": str(cfg.get("r2_min", "30")),
        "r2_max": str(cfg.get("r2_max", "100")),
        "cmd2": str(cfg.get("cmd2", "")),
        "r3_min": str(cfg.get("r3_min", "100")),
        "r3_max": str(cfg.get("r3_max", "9999")),
        "cmd3": str(cfg.get("cmd3", "")),
        "interval": str(cfg.get("script_interval", "1")),
    }
    try:
        from gui import ui as _ui
        if getattr(_ui, "ent_r1min", None) is not None:
            r1min_val = str(_ui.ent_r1min.get() or "").strip()
            if r1min_val:
                res["r1_min"] = r1min_val
        if getattr(_ui, "ent_r1max", None) is not None:
            r1max_val = str(_ui.ent_r1max.get() or "").strip()
            if r1max_val:
                res["r1_max"] = r1max_val
        if getattr(_ui, "ent_cmd1", None) is not None:
            cmd1_val = str(_ui.ent_cmd1.get() or "").strip()
            if cmd1_val:
                res["cmd1"] = cmd1_val

        if getattr(_ui, "ent_r2min", None) is not None:
            r2min_val = str(_ui.ent_r2min.get() or "").strip()
            if r2min_val:
                res["r2_min"] = r2min_val
        if getattr(_ui, "ent_r2max", None) is not None:
            r2max_val = str(_ui.ent_r2max.get() or "").strip()
            if r2max_val:
                res["r2_max"] = r2max_val
        if getattr(_ui, "ent_cmd2", None) is not None:
            cmd2_val = str(_ui.ent_cmd2.get() or "").strip()
            if cmd2_val:
                res["cmd2"] = cmd2_val

        if getattr(_ui, "ent_r3min", None) is not None:
            r3min_val = str(_ui.ent_r3min.get() or "").strip()
            if r3min_val:
                res["r3_min"] = r3min_val
        if getattr(_ui, "ent_r3max", None) is not None:
            r3max_val = str(_ui.ent_r3max.get() or "").strip()
            if r3max_val:
                res["r3_max"] = r3max_val
        if getattr(_ui, "ent_cmd3", None) is not None:
            cmd3_val = str(_ui.ent_cmd3.get() or "").strip()
            if cmd3_val:
                res["cmd3"] = cmd3_val

        if getattr(_ui, "ent_interval", None) is not None:
            interval_val = str(_ui.ent_interval.get() or "").strip()
            if interval_val:
                res["interval"] = interval_val
    except Exception:
        pass
    return res


def _safe_range(min_str, max_str, default_min, default_max):
    try:
        min_val = int(float(str(min_str).strip()))
    except Exception:
        min_val = default_min
    try:
        max_val = int(float(str(max_str).strip()))
    except Exception:
        max_val = default_max
    if min_val > max_val:
        min_val, max_val = max_val, min_val
    return min_val, max_val


def select_script_by_online_count():
    """根据当前直播间在线人数 state.online_num 动态匹配区间01、02、03话术。

    返回: (label, text, online_cnt, range_str)
    """
    online_cnt = int(getattr(state, "online_num", 0) or 0)
    cfg = _get_active_script_config()

    r1_min, r1_max = _safe_range(cfg.get("r1_min"), cfg.get("r1_max"), 0, 30)
    r2_min, r2_max = _safe_range(cfg.get("r2_min"), cfg.get("r2_max"), 30, 100)
    r3_min, r3_max = _safe_range(cfg.get("r3_min"), cfg.get("r3_max"), 100, 9999)

    cmd1 = (cfg.get("cmd1") or "").strip()
    cmd2 = (cfg.get("cmd2") or "").strip()
    cmd3 = (cfg.get("cmd3") or "").strip()

    if r1_min <= online_cnt <= r1_max:
        label = "区间01"
        text = cmd1
        range_str = f"{r1_min}–{r1_max}人"
    elif r2_min <= online_cnt <= r2_max:
        label = "区间02"
        text = cmd2
        range_str = f"{r2_min}–{r2_max}人"
    elif r3_min <= online_cnt <= r3_max:
        label = "区间03"
        text = cmd3
        range_str = f"{r3_min}–{r3_max}人"
    elif online_cnt > r3_max:
        label = "区间03"
        text = cmd3
        range_str = f">{r3_max}人"
    else:
        label = "区间01"
        text = cmd1
        range_str = f"<{r1_min}人"

    # 若命中区间的话术内容为空，自动寻找非空话术兜底，保证直播持续轮播不卡住
    if not text:
        for fb_label, fb_text in [("区间01", cmd1), ("区间02", cmd2), ("区间03", cmd3)]:
            if fb_text:
                label = f"{label}(改用{fb_label})"
                text = fb_text
                break

    return label, text, online_cnt, range_str


def silence_phone_playback():
    """向手机发送媒体停止与暂停指令，让豆包立刻闭嘴停止发声。"""
    def _worker():
        try:
            from core.paths import ADB_EXE
        except ImportError:
            ADB_EXE = "adb"
        for cmd in [
            [ADB_EXE, "shell", "input", "keyevent", "86"],  # KEYCODE_MEDIA_STOP
            [ADB_EXE, "shell", "input", "keyevent", "127"], # KEYCODE_MEDIA_PAUSE
            [ADB_EXE, "shell", "cmd", "media_session", "dispatch", "pause"],
            [ADB_EXE, "shell", "cmd", "media_session", "dispatch", "stop"],
        ]:
            try:
                subprocess.run(cmd, capture_output=True, timeout=1.5)
            except Exception:
                pass
    threading.Thread(target=_worker, daemon=True).start()


def cancel_active_vad():
    """供停止直播、关机和关闭窗口调用，立刻中断并释放虚拟声卡采集。"""
    global _live_generation, _vad_stop_event, _current_monitor
    with _round_lock:
        _live_generation += 1
        if _vad_stop_event:
            _vad_stop_event.set()
        if _current_monitor:
            try:
                _current_monitor.close()
            except Exception:
                pass
            _current_monitor = None

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
    ui.log_screen(f"【开播预演】正在下发（已融合商品名称、价格与物流背景）: {content[:30]}...")

    prompt = build_doubao_host_prompt(content, is_pre_meet=True)
    ok, msg = send_text_to_doubao(prompt, click_send=True)
    if not ok:
        ui.set_status("状态：❌预演下发失败", "#ff6b6b")
        ui.log_screen(f"【开播预演】❌失败: {msg}")
        messagebox.showerror("下发失败", f"话术未能发送到豆包对话：\n\n{msg}\n\n请确保手机已连接并停留在豆包对话界面。")
        return

    ui.set_status("状态：✅预演话术已发送到豆包", "#34d399")
    ui.log_screen(
        "【开播预演】✅发送成功！已将商品名称、价格/物流信息与预演设定同步告知豆包。"
        "(预演为单次演练：点「启动直播」后系统将结合在线人数区间持续轮播)"
    )
    if ui.lab_count:
        ui.root.after(0, lambda: ui.lab_count.config(text="✅预演完成(可点启动直播)"))

def send_script_content(text: str, range_label: str = "", is_first_round: bool = False):
    global can_next_speak, _current_monitor
    if not can_next_speak or not getattr(state, 'is_broadcasting', False):
        return

    try:
        vad_cfg = _read_vad_config()
    except (TypeError, ValueError) as exc:
        ui.log_screen("【VAD】⚠ VAD 配置读取异常，采用默认值：%s" % exc)
        vad_cfg = {
            "silence_hold": 4.0,
            "wait_start": 25.0,
            "speak_confirm": 0.3,
            "energy_threshold": -42.0,
            "noise_margin": 6.0,
            "end_hysteresis": 3.0,
            "calibration": 0.8,
            "calibration_wait": 3.0,
        }
    can_next_speak = False
    with _round_lock:
        generation = _live_generation
        stop_event = _vad_stop_event

    # 关键时序：先打开并校准音频，再发送消息。
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

    calibration_wait = min(3.0, max(1.0, float(vad_cfg.get("calibration_wait", 3.0))))
    calibrated = monitor.is_ready and monitor.calibrate_idle(
        vad_cfg["calibration"], stop_event, calibration_wait
    )
    if not calibrated:
        if monitor.is_ready:
            ui.log_screen(
                "【VAD】⚠ 静音基线校准未达完美判定（可能存在残留环境声），"
                "采用基准阈值 (%.1f dB) 保证直播话术持续下发。" % vad_cfg["energy_threshold"]
            )
            monitor.start_threshold_db = vad_cfg["energy_threshold"]
            monitor.end_threshold_db = monitor.start_threshold_db - vad_cfg["end_hysteresis"]
        else:
            ui.log_screen("【VAD】⚠ 音频流未就绪，使用默认配置继续下发。")

    vad_cfg = dict(vad_cfg)
    vad_cfg["silence_hold"] = monitor.active_silence_hold_sec

    tag = f"【直播话术·{range_label}】" if range_label else "【直播话术】"
    ui.log_screen(f"{tag}正在下发豆包: {text[:30]}...")
    ok, msg = send_text_to_doubao(build_doubao_host_prompt(text), click_send=True)

    if not ok:
        monitor.close()
        with _round_lock:
            if _current_monitor is monitor:
                _current_monitor = None
        ui.set_status(f"❌话术发送失败: {msg[:20]}", "#ff6b6b")
        ui.log_screen(f"【直播播控】❌ 话术下发失败: {msg}，将在 3 秒后重试下一轮...")
        time.sleep(3)
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
            max_wait_start_sec=max(25.0, vad_cfg["wait_start"]),
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

    if result == VAD_ENDED:
        ui.log_screen("【VAD】✅ 豆包本轮播报完毕，即将切入下一轮区间话术。")
    elif result == VAD_START_TIMEOUT:
        ui.log_screen("【VAD】⚠ 等待豆包开口超时（未检测到声音），自动继续推进下一轮话术。")
    elif result in (VAD_UNAVAILABLE, VAD_AUDIO_ERROR):
        ui.log_screen("【VAD】⚠ 音频采集读取中断，自动恢复并继续下一轮。")
        time.sleep(1.5)

    # 只要系统仍处于直播状态且电源开着，就允许下一轮播报
    if getattr(state, 'is_broadcasting', False):
        can_next_speak = True
        if ui.lab_count:
            ui.root.after(0, lambda: ui.lab_count.config(text="✅可以执行下一轮"))

def auto_live_loop():
    global can_next_speak
    is_first_round = True
    while getattr(state, 'is_broadcasting', False) and getattr(state, 'system_power', False):
        try:
            if can_next_speak:
                # 1. 动态按当前在线人数匹配区间话术
                label, text, online_cnt, range_str = select_script_by_online_count()

                if text and text.strip():
                    # 2. 更新状态栏与控制台
                    ui.set_status(f"状态：直播运行｜在线 {online_cnt} 人 [{label}]", "#34d399")
                    ui.log_screen(
                        f"【直播播控】当前在线 {online_cnt} 人，落入「{label}」({range_str})，准备下发话术..."
                    )
                    send_script_content(text.strip(), range_label=label, is_first_round=is_first_round)
                    is_first_round = False
                else:
                    ui.log_screen("【直播播控】⚠ 界面区间话术均为空，请在界面填写话术！")
                    time.sleep(2)

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

    ui.set_status("状态：直播运行｜在线人数动态匹配区间", "#34d399")
    ui.log_screen("【直播控制】▶ 自动直播循环已启动！将根据直播间在线人数持续轮询区间话术。")

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

    # 立即向手机发送停止/暂停多媒体指令，确保豆包立即闭嘴停止发声
    silence_phone_playback()

    if ui.btn_live_start:
        ui.btn_live_start.config(state=tk.NORMAL)
    if ui.btn_live_stop:
        ui.btn_live_stop.config(state=tk.DISABLED)

    ui.set_status("状态：待机【测试】✅", "#34d399")
    if ui.lab_count:
        ui.lab_count.config(text="✅可以执行下一轮")
    ui.log_screen("【直播控制】⏹ 自动直播已停止，虚拟声卡与弹幕采集已释放，手机声音已停止播放。")
