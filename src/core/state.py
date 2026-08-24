import sys

"""
智播豆全局运行状态机与状态变量
兼容原项目的模块级变量直接读取 (例如 state.system_power) 
以及面向对象的 app_state 单例访问
"""

# ==============================================================================
# 模块级全局状态变量 (兼容原项目 broadcast/power.py, gui/ui.py 等直接导入并读写)
# ==============================================================================

system_power = False          # 系统开机/总电源状态
is_broadcasting = False       # 是否正在直播播控循环中
is_paused = False             # 是否处于暂停状态
current_script_index = 0      # 当前播放话术索引
current_script_text = ""      # 当前话术内容
device_serial = None          # 当前连接的 ADB 设备序列号
device_connected = False      # 设备是否已连接
scrcpy_running = False        # 投屏服务是否运行中
auth_passed = True            # 授权认证是否通过

# 统计计数器
broadcast_count = 0           # 累计已播报条数
start_time = None             # 开机/启动时间戳


# ==============================================================================
# 状态机封装类 (面向对象支持)
# ==============================================================================

class AppState:
    def __init__(self):
        self.system_power = False
        self.is_running = False
        self.is_paused = False
        self.current_script_index = 0
        self.device_serial = None
        self.device_connected = False

    def __getattr__(self, name):
        if name in globals():
            return globals()[name]
        return False

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        globals()[name] = value

app_state = AppState()