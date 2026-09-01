# ====================== 主启动入口 ======================
# 流程：登录窗口（LoginWindow）→ 校验成功 → 进入主窗口（ui.build_ui）。
#       主窗口上"退出登录"按钮会清理后台资源并回到登录窗口。
# 业务模块(broadcast / screen / power / scrcpy_embed 等)依赖 cv2 / OBS / audio
# 等重型库，登录窗口本身完全不需要它们，因此延后到登录成功回调里再导入；
# 这样即使桌面环境没有这些依赖，也能先把登录 UI 跑起来定位问题。
import os
import sys
import tkinter as tk
import threading

# 让 src/ 与 src/* 包都能被解析（与原 main.py 同语义）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 早期只导入登录所需最小依赖
from pdk import auth_service as pdk_auth
from gui import login as login_ui

APP_VERSION = "1.7.0"
_logout_in_progress = False


def _cancel_tk_callbacks(tk_root):
    """在 destroy 前移除 Tcl after/idle 脚本，避免退出后执行失效命令。"""
    if tk_root is None:
        return
    try:
        pending = tk_root.tk.call("after", "info")
        if isinstance(pending, str):
            pending = (pending,)
        for after_id in tuple(pending or ()):
            try:
                tk_root.after_cancel(after_id)
            except (tk.TclError, ValueError):
                pass
    except tk.TclError:
        pass


def _enter_main(login_root):
    """登录成功后销毁登录窗口、构建并展示主窗口；在这里才 import 重型业务模块。"""
    try:
        _cancel_tk_callbacks(login_root)
        login_root.destroy()
    except Exception:
        pass

    # ----- 业务模块（延后导入；任一缺失不影响登录界面） -----
    from gui import ui, dialogs
    from core import state
    from settings import config
    from broadcast import power, live
    from screen import capture, scrcpy_embed, danmu

    state.auth_passed = pdk_auth.is_authenticated()
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
    ui.btn_pwd.config(command=dialogs.dialog_pdk_profile)
    ui.btn_auth.config(command=dialogs.dialog_pdk_license)
    ui.btn_logout.config(command=lambda: _do_logout(exit_on_close=False))

    # 关闭主窗口 = 退出登录回到登录界面（与原版直接关闭程序行为对齐，
    # 至少先清理后台资源，避免 scrcpy / VAD 残留）
    def _on_main_close():
        _do_logout(exit_on_close=True)

    ui.root.protocol("WM_DELETE_WINDOW", _on_main_close)

    threading.Thread(target=power.startup_readiness_check, daemon=True).start()
    ui.root.mainloop()


def _do_logout(exit_on_close=False):
    """退出登录（或关闭窗口）：清理后台线程 / 资源 → 销毁主窗口 → 重启登录。"""
    global _logout_in_progress
    if _logout_in_progress:
        return
    _logout_in_progress = True

    try:
        from gui import ui
        # 第一时间阻止后台线程继续投递 Tk 回调，并取消已排队的 after 脚本。
        ui.begin_shutdown()
    except Exception:
        ui = None

    # 清理后台资源（容忍失败）
    try:
        from core import state
        state.is_broadcasting = False
        state.system_power = False
        state.screenshot_working = False
    except Exception:
        pass
    try:
        from broadcast import live
        live.cancel_active_vad()
    except Exception:
        pass
    try:
        from screen import capture
        capture.shutdown_ui_refresh()
    except Exception:
        pass
    try:
        from screen import danmu
        danmu.stop_danmu_capture()
        danmu.shutdown_ui_pump()
    except Exception:
        pass
    try:
        from screen import scrcpy_embed
        scrcpy_embed.stop_scrcpy_embed()
    except Exception:
        pass
    try:
        pdk_auth.logout()
    except Exception as exc:
        # 本地会话由 auth_service 无条件清理；网络注销失败不阻止程序退出。
        print("[PDK] 注销请求失败：%s" % pdk_auth.format_error(exc))
    try:
        from core import state
        state.auth_passed = False
    except Exception:
        pass

    # 销毁主窗口
    try:
        if ui is not None and ui.root:
            # 后台清理期间可能又有模块尝试安排回调，销毁前再兜底取消一次。
            ui.begin_shutdown()
            ui.root.destroy()
    except Exception:
        pass

    if exit_on_close:
        # 用户主动关掉主窗口 → 整个进程退出，不再回登录
        _logout_in_progress = False
        return

    # 回到登录界面
    _logout_in_progress = False
    main()


def main():
    """阶段 1：展示登录窗口。登录成功会在 on_success 回调里进入 _enter_main。"""
    login_root = tk.Tk()
    login_root.title("智播豆 · 登录 v%s" % APP_VERSION)
    login_root.geometry("980x640")
    login_root.resizable(False, False)
    login_root.configure(bg="#ffffff")

    def _on_login_close():
        # 用户直接关闭登录窗口：整个进程退出
        try:
            _cancel_tk_callbacks(login_root)
            login_root.destroy()
        finally:
            sys.exit(0)

    login_ui.LoginWindow(
        login_root,
        on_success=lambda: _enter_main(login_root),
        on_close=_on_login_close,
    )
    login_root.mainloop()


if __name__ == "__main__":
    main()
