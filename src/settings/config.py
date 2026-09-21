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

# 旧版外部 WebSocket 中转地址已停用；弹幕数据现在通过进程内队列进入客户端。
WS_SERVER_URL = ""

# 主播语言/方言选项（UI「直播控制与音频活动」行的语言下拉框）。
# 所选项会作为提示词约束注入每次发给豆包的话术（见 broadcast/live.py）。
DOUBAO_LANGUAGES = (
    "普通话",
    # —— 知名地方方言 ——
    "粤语（广东话）", "东北话", "四川话", "河南话", "山东话", "陕西话",
    "上海话", "天津话", "湖南话", "安徽话", "贵州话", "云南话",
    "闽南语", "客家话", "潮汕话", "海南话",
    # —— 主流外语 ——
    "英语", "日语", "韩语", "俄语", "西班牙语", "法语", "德语",
    "葡萄牙语", "泰语", "越南语", "印尼语", "阿拉伯语",
)

# 默认配置（界面初次打开 / 配置损坏时的兜底）
DEFAULT_CFG = {
    "product_name": "日用百货",
    "product_desc": "你就是今天的主播 用中国话直接说话术 不要讲解 日用百货 品类多一一展示 下方小黄车直接拍",
    "pre_meet_text": "你就是今天的主播 用中国话直接说话术 不要讲解 日用百货 品类多一一展示 下方小黄车随便拍",
    # 每次下发给豆包的话术都会自动添加，约束豆包只输出可直接播放的主播口播。
    # 由原角色约束 + 输出格式硬约束（2026-09-21 用户补充）合并去重整理而来。
    "doubao_host_prompt": (
        "你现在是一名正在直播带货的主播。不要与用户对话，不要复述任务，"
        "直接以主播口吻连续输出可直接播放的直播话术，只说主播在直播间会直接说出口的话。\n"
        "只输出话术正文，不输出任何其他内容。禁止输出：建议、总结、备注、解释、说明、"
        "下一步动作、注意事项、变体版本、优化方向、使用场景、提醒、问候、结束语。\n"
        "禁止在话术前添加任何引导语（如“以下是为您生成的话术”“好的”“明白了”），"
        "禁止在话术后添加任何收尾语（如“希望对您有帮助”“您可以根据需要调整”），"
        "禁止添加标题、编号、括号说明、分隔线等任何非话术内容。\n"
        "禁止提问、请求确认或等待补充信息。\n"
        "话术正文结束后立即停止输出。"
    ),
    # 主播播报语言/方言（UI 语言下拉框所选值，见 DOUBAO_LANGUAGES），
    # 会作为语言约束注入每次发给豆包的提示词。
    "doubao_language": "普通话",
    "r1_min": "0", "r1_max": "30", "cmd1": "留人话术内容填这里",
    "r2_min": "30", "r2_max": "100", "cmd2": "产品讲解话术内容填这里",
    "r3_min": "100", "r3_max": "9999", "cmd3": "逼单促单话术内容填这里",
    # 弹幕浏览器采集。正式开播时自动启动，停止直播时自动关闭。
    # 需要登录的创作者后台首次应把 headless 改为 False，扫码/登录成功后再改回 True；
    # 登录状态保存在独立用户目录中，不要提交到版本库。
    "danmu_enabled": True,
    # 已废弃：平台类型改由 danma/platform_detect.py 按 URL 域名自动识别，
    # UI 不再有平台下拉框；此键仅为兼容旧 config.json 保留，运行时不再读取。
    "danmu_platform": "douyin",
    "danmu_url": "",
    # 已废弃：无窗口(headless)模式抓不到弹幕，必须用可见浏览器。此值已写死
    # False，不再读配置与 UI；此键仅为兼容旧 config.json 保留。
    "danmu_headless": False,
    # 仅统计指标模式：true = 打开浏览器只统计 实时在线/累计点赞/礼物互动，
    # 不采集弹幕文本（聊天/进场/关注分享均不下发）；false = 完整弹幕采集。
    "danmu_metrics_only": False,
    "danmu_user_data_dir": "",
    "danmu_chrome_path": "",
    "danmu_urls": {
        "tiktok": "https://www.tiktok.com/@tiktoktititv/live",
        "douyin": "https://live.douyin.com/646454278948",
        "kuaishou": "https://v.kuaishou.com/Ys1j7t",
        "bili": "https://live.bilibili.com/26552905",
        "shipinhao": "https://channels.weixin.qq.com/platform/live/liveBuild",
        "pdd": "https://live.pinduoduo.com/n-creator/live/live-record",
        "facebook": "https://www.facebook.com/littleroom9488/videos/410611252095041",
        "tb": "https://liveplatform.taobao.com/restful/index/live/list",
        "xhs": "https://redlive.xiaohongshu.com/live_center_control",
    },
    # 音频相关（仅 VAD 监听；scrcpy 音视频参数见 screen/scrcpy_embed.py 的 SCRCPY_OPTIMIZED_ARGS）
    # VAD 捕获设备：留空 = 自动（优先回环/混音输入设备，其次退回麦克风）。
    #   选哪种看你机器的音频路由（详见 MODULES.md §4.5 VAD 音频源与 OBS 路由）：
    #     · OBS 用户首选：Windows 启用「立体声混音」后留空即可
    #       —— OBS「桌面音频」自动包含豆包、你也能正常听，零改动；
    #     · 用 VB-Audio Virtual Cable：填 "CABLE Output"；
    #     · 用 Voicemeeter：填 "VoiceMeeter Output"。
    #   也可直接填设备【索引数字】(如 "3") 或设备名包含字(不区分大小写)。
    #   不确定设备名？运行 `python -m src.audio.vad` 会列出全部输入设备与索引。
    # 本项目正式音频链路固定使用 VB-Audio Virtual Cable：scrcpy 输出到
    # CABLE Input，VAD 从 CABLE Output 采集。不得因更换手机而静默改成实体麦克风。
    "vad_input_device": "CABLE Output",
    # VAD 静音跳句时序（单位：秒）—— 话术切换【完全由 VAD 静音时长决定】，不再使用 script_interval 倒计时：
    #   · vad_silence_hold_sec  —— 豆包说完后，连续静音超过此值(默认 4.0s)即判定"说完了"，立即切入下一轮；
    #   · vad_wait_start_sec    —— 【发消息后的思考等待上限】(默认 15.0s)：豆包生成/思考期可能数秒无语音，
    #                               此值要足够大，避免"思考期"被误判为"播报结束"；超时会安全停播，不会切下一句；
    #   · vad_speak_confirm_sec —— 进入"说话"态需连续有语音确认时长(默认 0.3s)：消抖，防单帧提示音/发送杂音误触发 SPEAKING；
    "vad_silence_hold_sec": 4.0,
    "vad_wait_start_sec": 15.0,
    "vad_speak_confirm_sec": 0.3,
    # 能量判定参数。实际开始阈值会取“此下限”和“静音底噪+余量”中的较高值；
    # 结束阈值会再降低 hysteresis，避免临界音量来回抖动。
    "vad_energy_threshold_db": -42.0,
    "vad_noise_margin_db": 6.0,
    "vad_end_hysteresis_db": 3.0,
    "vad_calibration_sec": 0.8,
    # 仅实体麦克风使用；CABLE 数字回环会一直等到真正静音或用户取消。
    "vad_calibration_wait_sec": 6.0,
    # scrcpy 把手机音频送出的【电脑输出设备】。
    # 作用：让 scrcpy 经 SDL2 的 SDL_AUDIO_DEVICE_NAME 把声音定向到虚拟音频线的「输入」端，
    #       与上面 vad_input_device 的「输出」端成对，VAD 才能听到豆包发声。
    #   · 用 VB-Audio Virtual Cable：填 "CABLE Input (VB-Audio Virtual Cable)"（与 vad 的 CABLE Output 成对）；
    #   · 用 Voicemeeter：填 "VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)"（与 vad 的 VoiceMeeter Output 成对）；
    #   · 留空 = scrcpy 走系统默认播放设备（此时需自己把 CABLE Input 设为默认播放设备才接得上）。
    # 注意：SDL 对设备名大小写/空格敏感，填错会静默回退到默认设备；接不上就用 `python -m src.audio.vad` 核对设备全名。
    # "scrcpy_audio_output_device": "CABLE Input (VB-Audio Virtual Cable)"
    # 实验：手机豆包声送真实扬声器外放；本机真实输出设备名为「扬声器 (Realtek(R) Audio)」，
    #      且它正是当前 Windows 默认播放设备，故填 "扬声器" 即可过路由闸门（勿填"电脑扬声器"，那只是输入回环）。
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
                    ent_r3min, ent_r3max, ent_cmd3,
                    ent_danmu_url, cmb_doubao_lang)
    import tkinter.messagebox as messagebox
    try:
        from broadcast.script_files import close_all_script_notepads
        close_all_script_notepads()
    except Exception:
        pass
    try:
        # 在现有配置上更新界面字段。不能重新创建只含界面字段的字典，否则用户手工
        # 调好的 VAD 设备、阈值和 scrcpy 音频路由会在点击“保存”后被静默删除。
        d = load_config()
        d.pop("script_interval", None)
        d.update({
            "product_name": ent_prod_name.get().strip(),
            "product_desc": ent_prod_desc.get().strip(),
            "pre_meet_text": txt_pre_meet.get(1.0, tk.END).strip(),
            "r1_min": ent_r1min.get(), "r1_max": ent_r1max.get(), "cmd1": ent_cmd1.get(),
            "r2_min": ent_r2min.get(), "r2_max": ent_r2max.get(), "cmd2": ent_cmd2.get(),
            "r3_min": ent_r3min.get(), "r3_max": ent_r3max.get(), "cmd3": ent_cmd3.get(),
            # 平台由 danma 按域名识别、headless 已写死 False（无窗口抓不到弹幕），
            # 两者均不再从 UI 采集。
            "danmu_url": ent_danmu_url.get().strip(),
            "doubao_language": cmb_doubao_lang.get().strip() or "普通话",
        })
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        try:
            from gui.ui import refresh_script_labels
            refresh_script_labels()
        except Exception:
            pass
        messagebox.showinfo("成功", "✅配置保存完成")
    except Exception as e:
        messagebox.showerror("错误", f"保存失败：{e}")
