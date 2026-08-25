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
    "--stay-awake",
]
# 最终兜底：仅保活投屏（无音视频调优）
SCRCPY_FALLBACK_ARGS = [
    SCRCPY_EXE,
    "--window-title", "scrcpy",
    "--max-size", "720",
    "--stay-awake",
]


def start_scrcpy_embed():
    """启动 scrcpy 子进程并尝试把窗口嵌入 embed_container。
    优先使用 SCRCPY_OPTIMIZED_ARGS（视频低码率/低帧率 + 音频低延迟 PCM 直出）；
    若 scrcpy 版本过旧不支持这些参数会立即退出，则自动回退到 SCRCPY_FALLBACK_ARGS，
    保证投屏永远能起来。"""
    if state.scrcpy_process is not None:
        return
    if not os.path.exists(SCRCPY_EXE):
        messagebox.showerror("文件缺失", f"找不到scrcpy.exe\n{SCRCPY_EXE}")
        return

    # scrcpy 经 SDL2 播放音频：用 SDL_AUDIO_DEVICE_NAME 把手机声音单独定向到虚拟音频线输入，
    # 与 config.vad_input_device 的「输出」端成对，VAD 才能听到豆包发声（不影响系统其他声音）。
    scrcpy_out_dev = ""
    try:
        from settings import config as _cfg
        scrcpy_out_dev = (_cfg.load_config().get("scrcpy_audio_output_device") or "").strip()
    except Exception:
        scrcpy_out_dev = ""
    launch_env = None
    if scrcpy_out_dev:
        launch_env = os.environ.copy()
        launch_env["SDL_AUDIO_DEVICE_NAME"] = scrcpy_out_dev
        # 校验该【播放/输出】设备是否真实存在：SDL 对设备名大小写/空格敏感，拼错会静默回退默认设备
        _dev_ok = False
        try:
            import pyaudio
            _pa = pyaudio.PyAudio()
            for _i in range(_pa.get_device_count()):
                _info = _pa.get_device_info_by_index(_i)
                if int(_info.get("maxOutputChannels", 0) or 0) > 0 and \
                        scrcpy_out_dev.lower() in (_info.get("name") or "").lower():
                    _dev_ok = True
                    break
            _pa.terminate()
        except Exception:
            _dev_ok = False
        if _dev_ok:
            ui.log_screen("【投屏】🎯 手机音频流将经 SDL 定向到输出设备【%s】(CABLE Input)，"
                          "再由 CABLE Output 镜像给 VAD / OBS；若 VAD 监听 dB 仍长期为静音，"
                          "说明该名字未被 SDL 认到，请核对设备全名。"
                          "（正式开播后若出现【Client-VAD】✅ 检测到语流开始，即证明 SDL 真正把声音送进了 CABLE）"
                          % scrcpy_out_dev)
        else:
            ui.log_screen("【投屏】⚠ 本机未找到播放设备【%s】，SDL 可能静默回退默认设备；"
                          "请运行 python -m src.audio.vad 核对设备全名，或把该设备设为 Windows 默认播放设备。"
                          % scrcpy_out_dev)

    # 分级尝试启动参数：全量优化 -> 仅视频调优 -> 基础保活。
    # 任一级进程在 3s 内退出(参数不被支持)，自动降到下一级，保证投屏永远能起。
    for level, (level_name, args) in enumerate([
        ("全量优化", SCRCPY_OPTIMIZED_ARGS),
        ("仅视频调优", SCRCPY_VIDEO_ONLY_ARGS),
        ("基础保活", SCRCPY_FALLBACK_ARGS),
    ], start=1):
        state.scrcpy_process = subprocess.Popen(args, cwd=SCRCPY_DIR, env=launch_env)
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
                              "（建议升级 scrcpy ≥ 2.2 以启用低延迟音频/低码率视频）" % level)
            break
        try:
            state.scrcpy_process.terminate()
        except Exception:
            pass
    else:
        # 三轮都异常退出（极端情况），最后再保底拉一次基础模式
        state.scrcpy_process = subprocess.Popen(SCRCPY_FALLBACK_ARGS, cwd=SCRCPY_DIR, env=launch_env)

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
