# ====================== 全局业务配置 ======================
# 负责：pyautogui 初始化、WebSocket 地址、默认话术配置、配置读写。
import json
import os
import tkinter as tk
import pyautogui
from core.paths import CONFIG_JSON

# pyautogui 安全设置（程序自己控制鼠标，关闭 FAILSAFE 与放慢）
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# 弹幕 WebSocket 服务地址
WS_SERVER_URL = "ws://127.0.0.1:8899"

# 默认配置（界面初次打开 / 配置损坏时的兜底）
DEFAULT_CFG = {
    "product_name": "日用百货",
    "product_desc": "你就是今天的主播 用中国话直接说话术 不要讲解 日用百货 品类多一一展示 下方小黄车直接拍",
    "pre_meet_text": "你就是今天的主播 用中国话直接说话术 不要讲解 日用百货 品类多一一展示 下方小黄车随便拍",
    "r1_min": "0", "r1_max": "30", "cmd1": "留人话术内容填这里",
    "r2_min": "30", "r2_max": "100", "cmd2": "产品讲解话术内容填这里",
    "r3_min": "100", "r3_max": "9999", "cmd3": "逼单促单话术内容填这里",
    # 注：script_interval 已不再作为切话术依据（切话术改由 VAD 静音时长驱动），保留仅为兼容界面配置，可忽略。
    "script_interval": 25,
    # 音频相关（仅 VAD 监听；scrcpy 音视频参数见 screen/scrcpy_embed.py 的 SCRCPY_OPTIMIZED_ARGS）
    # VAD 捕获设备：留空 = 自动（优先回环/混音输入设备，其次退回麦克风）。
    #   选哪种看你机器的音频路由（详见 MODULES.md §4.5 VAD 音频源与 OBS 路由）：
    #     · OBS 用户首选：Windows 启用「立体声混音」后留空即可
    #       —— OBS「桌面音频」自动包含豆包、你也能正常听，零改动；
    #     · 用 VB-Audio Virtual Cable：填 "CABLE Output"；
    #     · 用 Voicemeeter：填 "VoiceMeeter Output"。
    #   也可直接填设备【索引数字】(如 "3") 或设备名包含字(不区分大小写)。
    #   不确定设备名？运行 `python -m src.audio.vad` 会列出全部输入设备与索引。
    #   本机已装 VB-Audio Virtual Cable，且其「CABLE Output」是可捕获豆包声音的回环设备，故默认指向它。
    #   （若改用 Voicemeeter，把值改成 "VoiceMeeter Output" 即可；留空仅在不支持立体声混音的旧机器上会退回麦克风）
    "vad_input_device": "CABLE Output",
    # VAD 静音跳句时序（单位：秒）—— 话术切换【完全由 VAD 静音时长决定】，不再使用 script_interval 倒计时：
    #   · vad_silence_hold_sec  —— 豆包说完后，连续静音超过此值(默认 2.0s)即判定"说完了"，立即切入下一轮；
    #   · vad_wait_start_sec    —— 【发消息后的思考等待上限】(默认 15.0s)：豆包生成/思考期可能数秒无语音，
    #                               此值要足够大，避免"思考期"被误判为"播报结束"而切走；超时视作豆包无语音回答、直接进下一句；
    #   · vad_speak_confirm_sec —— 进入"说话"态需连续有语音确认时长(默认 0.3s)：消抖，防单帧提示音/发送杂音误触发 SPEAKING；
    #   · vad_max_speech_sec    —— 单句监听硬上限(默认 45.0s)，到时强制结束（防卡死）。
    "vad_silence_hold_sec": 2.0,
    "vad_wait_start_sec": 15.0,
    "vad_speak_confirm_sec": 0.3,
    "vad_max_speech_sec": 45.0,
    # 能量判定参数。实际开始阈值会取“此下限”和“静音底噪+余量”中的较高值；
    # 结束阈值会再降低 hysteresis，避免临界音量来回抖动。
    "vad_energy_threshold_db": -42.0,
    "vad_noise_margin_db": 6.0,
    "vad_end_hysteresis_db": 3.0,
    "vad_calibration_sec": 0.8,
    "vad_calibration_wait_sec": 6.0,
    # scrcpy 把手机音频送出的【电脑输出设备】。
    # 作用：让 scrcpy 经 SDL2 的 SDL_AUDIO_DEVICE_NAME 把声音定向到虚拟音频线的「输入」端，
    #       与上面 vad_input_device 的「输出」端成对，VAD 才能听到豆包发声。
    #   · 用 VB-Audio Virtual Cable：填 "CABLE Input (VB-Audio Virtual Cable)"（与 vad 的 CABLE Output 成对）；
    #   · 用 Voicemeeter：填 "VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)"（与 vad 的 VoiceMeeter Output 成对）；
    #   · 留空 = scrcpy 走系统默认播放设备（此时需自己把 CABLE Input 设为默认播放设备才接得上）。
    # 注意：SDL 对设备名大小写/空格敏感，填错会静默回退到默认设备；接不上就用 `python -m src.audio.vad` 核对设备全名。
    "scrcpy_audio_output_device": "CABLE Input (VB-Audio Virtual Cable)"
}


def load_config():
    """读取 zhibodou_config.json，与默认配置合并。文件缺失/损坏时返回默认配置副本。"""
    if os.path.exists(CONFIG_JSON):
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                d = json.load(f)
            return {**DEFAULT_CFG, **d}
        except Exception:
            pass
    return DEFAULT_CFG.copy()


def save_config():
    """从界面控件采集配置并写入 zhibodou_config.json。
    延迟导入 ui 以读取控件，避免与 ui 模块形成循环依赖。"""
    from gui.ui import (ent_prod_name, ent_prod_desc, txt_pre_meet,
                    ent_r1min, ent_r1max, ent_cmd1,
                    ent_r2min, ent_r2max, ent_cmd2,
                    ent_r3min, ent_r3max, ent_cmd3, ent_interval)
    import tkinter.messagebox as messagebox
    try:
        # 在现有配置上更新界面字段。不能重新创建只含界面字段的字典，否则用户手工
        # 调好的 VAD 设备、阈值和 scrcpy 音频路由会在点击“保存”后被静默删除。
        d = load_config()
        d.update({
            "product_name": ent_prod_name.get().strip(),
            "product_desc": ent_prod_desc.get().strip(),
            "pre_meet_text": txt_pre_meet.get(1.0, tk.END).strip(),
            "r1_min": ent_r1min.get(), "r1_max": ent_r1max.get(), "cmd1": ent_cmd1.get(),
            "r2_min": ent_r2min.get(), "r2_max": ent_r2max.get(), "cmd2": ent_cmd2.get(),
            "r3_min": ent_r3min.get(), "r3_max": ent_r3max.get(), "cmd3": ent_cmd3.get(),
            "script_interval": ent_interval.get()
        })
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("成功", "✅配置保存完成")
    except Exception as e:
        messagebox.showerror("错误", f"保存失败：{e}")
