# ====================== TTS 语音播报 ======================
# 外音模式下用 pyttsx3 朗读话术（内录模式 inner_audio_mode 时跳过）。
import pyttsx3
from core import state
def speak_text(text):
    """朗读文本。内录模式(剪贴板)下不发声。"""
    if state.inner_audio_mode:
        return
    try:
        eng = pyttsx3.init()
        eng.setProperty("rate", 138)
        eng.setProperty("volume", 0.95)
        eng.say(text)
        eng.runAndWait()
        eng.stop()
    except Exception:
        pass
