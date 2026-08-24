# ====================== 全局运行时状态 ======================
# 集中管理原先散落在各函数里的 global 变量，避免「global 满天飞」。
# 其他模块统一通过 `import state` 后读写 `state.xxx`，不再使用 global 关键字。
import queue
import threading

# ---- scrcpy 投屏嵌入 ----
scrcpy_process = None
scrcpy_hwnd = 0

# ---- 系统开关 ----
system_power = False
live_running = False
screenshot_working = False

# ---- 话术发送节流 ----
locker = threading.Lock()          # 保证发送不被并发打断
can_next_speak = True
count_down_sec = 0
seq_index = 0                      # 直播顺序循环 0->区间1, 1->区间2, 2->区间3

# ---- 实时数据计数 ----
online_num = 0
like_cnt = 0
gift_cnt = 0
comment_cnt = 0

# ---- 音频模式 ----
inner_audio_mode = False           # True=内录(剪贴板) / False=外音(TTS 语音)

# ---- 抓屏日志消息队列 ----
msg_queue = queue.Queue(maxsize=100)
