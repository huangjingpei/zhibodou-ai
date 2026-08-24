import os
import sys
import threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ====================== 程序入口 ======================
# 构建 UI、接线各按钮回调、初始化管理员密码、启动主循环。
# 双击 一键启动.bat 或 `python main.py` 即启动。
from gui import ui
from core import state
from settings import config
from settings import auth
from broadcast import power
from broadcast import live
from screen import capture
from screen import scrcpy_embed
from screen import danmu
from gui import dialogs
def on_closing():
    """窗口关闭：先停 scrcpy，再销毁。"""
    scrcpy_embed.stop_scrcpy_embed()
    ui.root.destroy()


def main():
    ui.build_ui()

    # ---- 接线按钮回调 ----
    ui.btn_power.config(command=power.toggle_power)
    # ui.btn_meet.config(command=live.run_pre_meet)
    # ui.btn_live_start.config(command=live.start_live)
    # ui.btn_live_stop.config(command=live.stop_live)
    # ui.btn_audio_mode.config(command=live.toggle_audio_mode)
    ui.btn_cap.config(command=capture.start_capture)
    ui.btn_save.config(command=config.save_config)
    ui.btn_pwd.config(command=dialogs.dialog_modify_pwd)
    ui.btn_auth.config(command=dialogs.dialog_auth_mgr)

    # ---- 初始化 ----
    auth.init_admin_password()
    ui.root.protocol("WM_DELETE_WINDOW", on_closing)
    # 启动自检：后台检测豆包就绪状态，结果写屏幕日志（不阻塞 UI 启动）
    threading.Thread(target=power.startup_readiness_check, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
