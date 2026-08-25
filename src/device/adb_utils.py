# ====================== ADB 底层命令封装 ======================
# 所有直接操控手机（不碰电脑鼠标/剪贴板）的 adb 调用统一收敛到这里。
import subprocess
import shlex
import time
from core.paths import ADB_EXE

# 隐藏 adb 子进程黑窗口（仅 Windows）。与 core.paths 的全局补丁互为双保险。
_ADB_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_adb(args, timeout=5, capture=True):
    """执行 `adb <args>`，返回 subprocess.CompletedProcess 或 None。
    主 adb(打包内置)不可用时，自动回退到系统 PATH 中的 adb，提高检测成功率。"""
    cmd = [ADB_EXE] + list(args)
    try:
        return subprocess.run(cmd, capture_output=capture, timeout=timeout,
                              creationflags=_ADB_FLAGS)
    except Exception:
        # 主 adb 路径异常(被杀软拦截/缺失)时，退一步用系统 adb(若存在)
        try:
            return subprocess.run(["adb"] + list(args), capture_output=capture,
                                  timeout=timeout, creationflags=_ADB_FLAGS)
        except Exception:
            return None


def adb_shell(*parts, timeout=8):
    """执行 `adb shell <parts>`，返回 (stdout 字符串, 是否成功)。"""
    try:
        r = subprocess.run([ADB_EXE, "shell", *parts],
                           capture_output=True, timeout=timeout,
                           creationflags=_ADB_FLAGS)
        return r.stdout.decode("utf-8", "ignore"), True
    except Exception:
        try:
            r = subprocess.run(["adb", "shell", *parts],
                               capture_output=True, timeout=timeout,
                               creationflags=_ADB_FLAGS)
            return r.stdout.decode("utf-8", "ignore"), True
        except Exception:
            return "", False


def adb_tap(x, y):
    """adb 模拟手机屏幕点击（手机本机坐标）。"""
    try:
        subprocess.run([ADB_EXE, "shell", "input", "tap", str(x), str(y)],
                       capture_output=True, timeout=3)
    except Exception:
        pass


def adb_set_phone_clipboard(text):
    """把文字写入【手机剪贴板】，完全隔离电脑剪贴板，解决发出代码 bug。"""
    try:
        from gui.ui import set_status
    except Exception:
        def set_status(msg, color): pass
    try:
        cmd = "am broadcast -a clipper.set -e text " + shlex.quote(text)
        out, _ = adb_shell(cmd)
        if "Text is copied" not in out:
            set_status("⚠️clipper写入剪贴板失败：" + out.strip()[-60:], "#ff6b6b")
        import time
        time.sleep(0.25)
    except Exception:
        pass


def adb_phone_paste():
    """手机端执行粘贴 keyevent 279 = PASTE"""
    try:
        subprocess.run([ADB_EXE, "shell", "input", "keyevent", "279"],
                       capture_output=True, timeout=3)
    except Exception:
        pass


def check_clipper_installed():
    """检测手机是否装了 clipper（剪贴板广播接收器）。"""
    out, _ = adb_shell("pm", "list", "packages")
    return "clipper" in out.lower()


def is_app_installed(pkg):
    """检测手机是否安装了指定包名的 App（adb 可用时）。
    返回 True / False / None(adb 不可用或命令失败，无法判断)。"""
    try:
        out, ok = adb_shell("pm", "list", "packages", pkg)
    except Exception:
        return None
    if not ok:
        return None
    for ln in out.splitlines():
        line = ln.strip()
        if line == "package:" + pkg or line.startswith("package:" + pkg + "."):
            return line[len("package:"):] == pkg
    return False


def adb_devices_online(verbose=False):
    """返回在线 adb 设备序列号列表（状态为 device 的行）。
    verbose=True 时把 `adb devices` 原始输出/stderr 打到 stdout，便于打包后排查
    （如 adb 被杀软拦截、server 版本冲突、设备处于 unauthorized 等）。

    健壮性：先 `start-server` 确保守护进程已起；再重试最多 3 次（间隔 1s）。
    原因：首次调用 adb 时它需要启动/接管 5037 端口的 server，且可能与本机已运行
    的其它 adb server 发生版本切换，导致单次 `adb devices` 偶发返回空列表 -> 误判
    离线弹窗。重试可消除该时序竞态。"""
    # 1) 确保 adb server 已启动（首跑常尚未就绪，导致一次性检测误判为离线）
    run_adb(["start-server"], timeout=8)

    online = []
    last_detail = ""
    for attempt in range(3):
        r = run_adb(["devices"])
        if r and r.stdout:
            out = r.stdout.decode("utf-8", "ignore")
            if verbose:
                print("[ADB] `adb devices` 原始输出(第%d次):\n%s" % (attempt + 1, out))
            # 同时收集 unauthorized 等设备，便于诊断"连了但没授权"的情况
            lines = [ln for ln in out.splitlines()
                     if ln.rstrip().endswith("\tdevice") or ln.rstrip().endswith("\tunauthorized")]
            online = [ln.split("\t")[0] for ln in lines if ln.rstrip().endswith("\tdevice")]
            if online:
                return online
            states = [ln.split("\t")[-1] for ln in lines]
            last_detail = ("其它状态=%s（若为 unauthorized 请在手机点允许调试；"
                           "若为空列表说明未连上/未授权）" % states)
        elif r is not None:
            last_detail = "stderr=%s" % (r.stderr.decode("utf-8", "ignore") if r.stderr else "(无)")
        else:
            last_detail = "adb 调用异常/未返回（可能被杀软拦截或未安装）"
        if verbose and attempt < 2:
            print("[ADB] 第%d次未检测到 device：%s" % (attempt + 1, last_detail))
        if attempt < 2:
            time.sleep(1.0)
    if verbose:
        print("[ADB] 最终仍未检测到已授权(device)设备：%s" % last_detail)
    return online


def doubao_in_foreground():
    """豆包 APP 是否真正处于前台。"""
    from core.doubao import DOUBAO_PKG
    out, _ = adb_shell("dumpsys", "activity", "activities")
    for line in out.splitlines():
        if ("mResumedActivity" in line or "mTopResumedActivity" in line
                or "mFocusedApp" in line) and DOUBAO_PKG in line:
            return True
    out2, _ = adb_shell("dumpsys", "window")
    return DOUBAO_PKG in out2
