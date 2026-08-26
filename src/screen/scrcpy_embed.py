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
from core.paths import SCRCPY_EXE, SCRCPY_DIR, LOCAL_ADB


# ====================== scrcpy 优化启动参数 ======================
# 设计取向：视频只用来在软件里显示豆包界面，无需高码率；音频走低延迟 PCM 直出。
# 注意：--audio-codec/--video-buffer/--max-fps/--audio-buffer 需要 scrcpy ≥ 2.2，
#       老版本 scrcpy 会因不识别参数直接退出，见下方 SCRCPY_FALLBACK_ARGS 自动回退。
# 警告：scrcpy 没有 --no-downplay 这个参数（曾误加，导致整组参数被拒、回退基础模式）。
#       若担心嵌入窗口失焦后系统音频被"压低"(ducking)，属 Windows 音频策略，非 scrcpy 参数可控。
SCRCPY_OPTIMIZED_ARGS = [
    SCRCPY_EXE,
    "--window-title", "scrcpy",
    "--max-size", "720",             # 控制画面分辨率，大幅降低 GPU 编码压力
    "--video-bit-rate", "4M",        # 4Mbps 足够话术直播高清显示
    "--max-fps", "30",               # 直播话术画面 30 帧足够，降低发热与延迟
    "--audio-codec", "raw",          # 采用 PCM Raw 编码，省去手机端 AAC 压缩编码耗时
    "--audio-source", "output",       # 明确捕获手机完整输出，而不是麦克风
    "--require-audio",                # 音频失败必须退出，禁止“有画面但 VAD 永久静音”
    "--audio-buffer", "20",          # 音频缓冲 20ms（默认 50ms），极致低延迟；无线连接若卡顿可调大
    "--video-buffer", "0",           # 视频缓冲 0ms，杜绝画面排队卡顿
    "--stay-awake",                  # 会话期间保持手机唤醒，避免灭屏后音频被节流
]

# 老版本 scrcpy 不支持音频参数时的分级回退（保证投屏能起，尽量保住视频调优）
# 仅保留视频调优，去掉所有音频专属参数（音频参数出现最晚、最易不兼容）
SCRCPY_VIDEO_ONLY_ARGS = [
    SCRCPY_EXE,
    "--window-title", "scrcpy",
    "--max-size", "720",
    "--video-bit-rate", "4M",
    "--max-fps", "30",
    "--video-buffer", "0",
    "--audio-source", "output",
    "--require-audio",
    "--stay-awake",
]
# 最终兜底：仅保活投屏（无音视频调优）
SCRCPY_FALLBACK_ARGS = [
    SCRCPY_EXE,
    "--window-title", "scrcpy",
    "--max-size", "720",
    "--audio-source", "output",
    "--require-audio",
    "--stay-awake",
]

# Android 10 及以下不支持 scrcpy 音频转发。此模式只投屏画面，手机声音
# 保留在手机扬声器播放，再由实体麦克风 VAD 监听。
SCRCPY_LEGACY_VIDEO_ARGS = [
    SCRCPY_EXE,
    "--window-title", "scrcpy",
    "--max-size", "720",
    "--video-bit-rate", "4M",
    "--max-fps", "30",
    "--video-buffer", "0",
    "--no-audio",
    "--stay-awake",
]


def _get_android_sdk():
    try:
        result = subprocess.run(
            [LOCAL_ADB, "shell", "getprop", "ro.build.version.sdk"],
            capture_output=True, text=True, timeout=3,
        )
        value = (result.stdout or "").strip()
        return int(value) if value.isdigit() else None
    except Exception:
        return None


def _is_virtual_audio_route(output_name: str, input_name: str) -> bool:
    names = (str(output_name or "") + " " + str(input_name or "")).lower()
    return any(
        keyword in names
        for keyword in ("cable", "voicemeeter", "loopback", "立体声混音")
    )


def start_scrcpy_embed():
    """启动 scrcpy 子进程并尝试把窗口嵌入 embed_container。
    优先使用 SCRCPY_OPTIMIZED_ARGS（视频低码率/低帧率 + 音频低延迟 PCM 直出）；
    若优化参数不兼容则分级回退；但音频不可用时必须失败，禁止启动“只有画面”的假 VAD。"""
    if state.scrcpy_process is not None:
        if state.scrcpy_process.poll() is None:
            return True
        state.scrcpy_process = None
    if not os.path.exists(SCRCPY_EXE):
        messagebox.showerror("文件缺失", f"找不到scrcpy.exe\n{SCRCPY_EXE}")
        return False

    # 内置 scrcpy 4.1 经 SDL3 的默认播放端点输出音频。配置名用于核对 Windows 默认
    # 播放设备；使用数字回环时应与 vad_input_device 成对，使用实体麦克风时
    # 则由麦克风监听该播放设备发出的外放声音。
    scrcpy_out_dev = ""
    vad_input_dev = ""
    try:
        from settings import config as _cfg
        _audio_cfg = _cfg.load_config()
        scrcpy_out_dev = (_audio_cfg.get("scrcpy_audio_output_device") or "").strip()
        vad_input_dev = (_audio_cfg.get("vad_input_device") or "").strip()
    except Exception:
        scrcpy_out_dev = ""
        vad_input_dev = ""
    android_sdk = _get_android_sdk()
    legacy_phone_audio = android_sdk is not None and android_sdk < 30
    virtual_audio_route = _is_virtual_audio_route(scrcpy_out_dev, vad_input_dev)
    if legacy_phone_audio:
        if virtual_audio_route:
            ui.log_screen(
                "【投屏】❌ 当前手机 Android API=%d，不支持 scrcpy 音频转发；"
                "CABLE/VoiceMeeter 数字回环无法使用。请改用 Android 11+ 手机，"
                "或把 VAD 输入改为实体麦克风。" % android_sdk
            )
            return False
        ui.log_screen(
            "【投屏】⚠ 当前手机为 Android API=%d（低于 30），scrcpy 不支持转发音频；"
            "已切换为仅画面投屏，声音从手机扬声器播放，由实体麦克风 VAD 监听。"
            % android_sdk
        )
    launch_env = None
    if scrcpy_out_dev and not legacy_phone_audio:
        launch_env = os.environ.copy()
        launch_env["SDL_AUDIO_DEVICE_NAME"] = scrcpy_out_dev
        # 校验该【播放/输出】设备是否真实存在：SDL 对设备名大小写/空格敏感，拼错会静默回退默认设备
        _dev_ok = False
        _default_out_name = ""
        try:
            import pyaudio
            _pa = pyaudio.PyAudio()
            try:
                _default_out_name = (_pa.get_default_output_device_info().get("name") or "")
            except Exception:
                _default_out_name = ""
            for _i in range(_pa.get_device_count()):
                _info = _pa.get_device_info_by_index(_i)
                if int(_info.get("maxOutputChannels", 0) or 0) > 0 and \
                        scrcpy_out_dev.lower() in (_info.get("name") or "").lower():
                    _dev_ok = True
                    break
            _pa.terminate()
        except Exception:
            _dev_ok = False
            _default_out_name = ""
        if _dev_ok:
            # 内置 scrcpy 4.1 使用 SDL 默认播放端点。环境变量保留作兼容提示，但不能把
            # “设备存在”误当成“scrcpy 已定向成功”；必须校验 Windows 默认播放设备。
            _family = scrcpy_out_dev.split("(", 1)[0].strip().lower()
            if not _default_out_name or _family not in _default_out_name.lower():
                ui.log_screen("【投屏】❌ Windows 默认播放设备为【%s】，不是配置的【%s】。"
                              "scrcpy 4.1 会打开默认播放端点，VAD 将收不到手机声音；"
                              "请先把配置的播放设备设为 Windows 默认播放设备。"
                              % (_default_out_name or "未知", scrcpy_out_dev))
                messagebox.showerror(
                    "音频路由未就绪",
                    "scrcpy 需要从配置的 Windows 默认播放设备输出手机声音。\n\n"
                    f"当前默认播放设备：{_default_out_name or '未知'}\n"
                    f"要求的播放设备：{scrcpy_out_dev}\n\n"
                    f"请在 Windows 声音设置中把 {scrcpy_out_dev} 设为默认播放设备后重试。",
                )
                return False
            ui.log_screen("【投屏】✅ 默认播放设备【%s】与配置匹配；"
                          "scrcpy 手机音频将从该设备播放。" % _default_out_name)
            if virtual_audio_route:
                ui.log_screen("【投屏】VAD 使用数字回环输入【%s】。" % (vad_input_dev or "自动选择"))
            else:
                ui.log_screen(
                    "【投屏】⚠ VAD 使用实体麦克风【%s】监听扬声器，已启用相对底噪自适应；"
                    "环境噪声或系统音量过低仍可能影响识别。" % (vad_input_dev or "系统默认")
                )
        else:
            ui.log_screen("【投屏】❌ 本机未找到播放设备【%s】，拒绝启动无音频投屏。"
                          "请运行 python -m src.audio.vad 核对设备全名。"
                          % scrcpy_out_dev)
            return False

    # Android 10 及以下走手机扬声器 + 实体麦克风；新系统才尝试 scrcpy 音频转发。
    launch_modes = (
        [("Android 10 画面投屏", SCRCPY_LEGACY_VIDEO_ARGS)]
        if legacy_phone_audio
        else [
            ("全量优化", SCRCPY_OPTIMIZED_ARGS),
            ("仅视频调优", SCRCPY_VIDEO_ONLY_ARGS),
            ("基础保活", SCRCPY_FALLBACK_ARGS),
        ]
    )
    for level, (level_name, args) in enumerate(launch_modes, start=1):
        try:
            state.scrcpy_process = subprocess.Popen(args, cwd=SCRCPY_DIR, env=launch_env)
        except Exception as exc:
            ui.log_screen("【投屏】启动 scrcpy 失败：%s" % exc)
            state.scrcpy_process = None
            return False
        deadline = time.time() + 3.0
        exited_early = False
        while time.time() < deadline:
            rc = state.scrcpy_process.poll()
            if rc is not None:
                exited_early = True
                break
            time.sleep(0.2)
        if not exited_early:
            if level > 1:
                ui.log_screen("【投屏】当前 scrcpy 版本不支持部分优化参数，已回退到「%s」模式"
                              "（建议升级 scrcpy ≥ 2.2 以启用低延迟音频/低码率视频）" % level_name)
            break
        try:
            state.scrcpy_process.terminate()
        except Exception:
            pass
    else:
        # 三轮都退出时通常是 --require-audio 检测到手机音频不可用；不能再以
        # “只有画面”的模式假装启动成功，否则 VAD 会永久收不到语音。
        state.scrcpy_process = None
        if legacy_phone_audio:
            ui.log_screen("【投屏】❌ Android 10 仅画面投屏仍启动失败，请检查 USB 调试和设备授权。")
        else:
            ui.log_screen("【投屏】❌ scrcpy 各启动模式均退出，手机音频捕获不可用。")
        return False

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
    return True


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
