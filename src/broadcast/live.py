import os
import sys
import time

# 兼容无论是从根目录还是从 src 目录启动的导入路径
try:
    from src.core.state import app_state
except (ImportError, ModuleNotFoundError, AttributeError):
    try:
        from core.state import app_state
    except (ImportError, ModuleNotFoundError, AttributeError):
        try:
            from core import state
            app_state = getattr(state, 'app_state', state)
        except (ImportError, ModuleNotFoundError, AttributeError):
            class DummyState:
                is_running = True
            app_state = DummyState()

try:
    from src.device.ui_locator import click_doubao_input
    from src.device.input_text import send_text_to_doubao
    from src.audio.vad import AudioPlaybackMonitor
except (ImportError, ModuleNotFoundError):
    try:
        from device.ui_locator import click_doubao_input
        from device.input_text import send_text_to_doubao
        from audio.vad import AudioPlaybackMonitor
    except (ImportError, ModuleNotFoundError):
        from .ui_locator import click_doubao_input
        from .input_text import send_text_to_doubao
        from .vad import AudioPlaybackMonitor

def execute_live_cycle(script_text: str, device_id: str = None) -> bool:
    """
    【全新升级的无人值守无人直播话术播控单轮闭环】
    1. 动态自适应聚焦输入框（跨分辨率、跨机型、跨版本兼容）
    2. 原生系统级 UTF-8 文本直注（零 APK 依赖，毫秒级注入）
    3. 触发发送
    4. 启动音频感知监视器（动态跟随语流，彻底解决打断与冷场）
    """
    print(f"\n======== [智播豆 2.0] 开始执行话术轮播 ========")
    print(f"话术内容: {script_text}")
    
    # 1. 聚焦输入框
    click_doubao_input(device_id)
    time.sleep(0.1)

    # 2. 原生零依赖注入并点击发送
    send_success = send_text_to_doubao(script_text, device_id, click_send=True)
    if not send_success:
        print("[LiveCycle] 话术注入失败")
        return False
    
    print("[LiveCycle] 话术已成功注入并触发发送！")

    # 3. 动态音频感知检测（取代死板的 sleep 15s 倒计时）
    audio_monitor = AudioPlaybackMonitor(device_id=device_id, silence_hold_sec=0.8)
    audio_monitor.wait_for_doubao_speech_cycle(max_wait_start_sec=6.0, max_speech_timeout_sec=60.0)

    print("======== [智播豆 2.0] 本轮话术播报完成，无缝准备下一轮 ========\n")
    return True

def run_continuous_broadcast(script_list: list, device_id: str = None):
    """
    连续不间断自动直播循环
    """
    idx = 0
    while getattr(app_state, 'is_running', True):
        current_script = script_list[idx % len(script_list)]
        execute_live_cycle(current_script, device_id)
        idx += 1
        # 轮次间微小防抖缓冲 (0.5s)
        time.sleep(0.5)
