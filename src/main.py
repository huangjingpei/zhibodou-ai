import os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import ui
from core import state
from settings import config, auth
from broadcast import power, live
from screen import capture, scrcpy_embed, danmu
from gui import dialogs

def on_closing():
    try:
        live.cancel_active_vad()
        state.is_broadcasting = False
    except Exception:
        pass
    try:
        danmu.stop_danmu_capture()
    except Exception:
        pass
    try:
        scrcpy_embed.stop_scrcpy_embed()
    except Exception:
        pass
    if ui.root:
        ui.root.destroy()

def main():
    ui.build_ui()
    danmu.initialize_ui_pump()

    # ---- 接线全部核心按钮回调 ----
    ui.btn_power.config(command=power.toggle_power)
    ui.btn_meet.config(command=live.run_pre_meet)
    ui.btn_live_start.config(command=live.start_live)
    ui.btn_live_stop.config(command=live.stop_live)
    ui.btn_audio_mode.config(command=live.toggle_audio_mode)
    ui.btn_cap.config(command=capture.start_capture)
    ui.btn_danmu.config(command=danmu.toggle_danmu_capture)
    ui.btn_save.config(command=config.save_config)
    ui.btn_pwd.config(command=dialogs.dialog_modify_pwd)
    ui.btn_auth.config(command=dialogs.dialog_auth_mgr)

    auth.init_admin_password()
    ui.root.protocol("WM_DELETE_WINDOW", on_closing)
    threading.Thread(target=power.startup_readiness_check, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()
