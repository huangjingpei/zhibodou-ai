# ====================== ADB 底层命令封装 ======================
# 所有直接操控手机（不碰电脑鼠标/剪贴板）的 adb 调用统一收敛到这里。
import subprocess
import shlex
from core.paths import ADB_EXE


def run_adb(args, timeout=5, capture=True):
    """执行 `adb <args>`，返回 subprocess.CompletedProcess。"""
    cmd = [ADB_EXE] + list(args)
    return subprocess.run(cmd, capture_output=capture, timeout=timeout)


def adb_shell(*parts, timeout=8):
    """执行 `adb shell <parts>`，返回 (stdout 字符串, 是否成功)。"""
    try:
        r = subprocess.run([ADB_EXE, "shell", *parts],
                           capture_output=True, timeout=timeout)
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
    """把文字写入【手机剪贴板】，完全隔离电脑剪贴板，解决发出代码 bug。
    ⚠️ clipper v1.2.1 只认 -e text extra（实测 textb64 是无效参数，广播会被
    "No text is provided" 拒绝，剪贴板根本没写入！），必须用 text + shell 引号转义"""
    from gui.ui import set_status
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
    # `pm list packages <pkg>` 会列出包含该串的所有包，需精确匹配行尾
    for ln in out.splitlines():
        line = ln.strip()
        if line == "package:" + pkg or line.startswith("package:" + pkg + "."):
            # 精确匹配包名本身（避免 com.larus.nova.test 误中 com.larus.nova）
            return line[len("package:"):] == pkg
    return False


def adb_devices_online():
    """返回在线 adb 设备序列号列表（状态为 device 的行）。

    ⚠️ `adb devices` 不是 shell 子命令，必须用 run_adb(['devices'])，
    不能写成 adb_shell('devices')（会变成 `adb shell devices`，无效）。
    """
    r = run_adb(["devices"])
    out = r.stdout.decode("utf-8", "ignore")
    return [ln.split("\t")[0] for ln in out.splitlines() if ln.endswith("\tdevice")]


def doubao_in_foreground():
    """豆包 APP 是否真正处于前台。

    旧实现只查 `dumpsys window` 里是否含包名——豆包在后台时窗口仍可能留在
    window 列表里，从而误判为前台。这里改为优先按 resumed/top/focused activity
    判定（只有真正在前台的 activity 才会出现），兜底再回退到 window 含包名。
    """
    from core.doubao import DOUBAO_PKG
    out, _ = adb_shell("dumpsys", "activity", "activities")
    for line in out.splitlines():
        if ("mResumedActivity" in line or "mTopResumedActivity" in line
                or "mFocusedApp" in line) and DOUBAO_PKG in line:
            return True
    # 兜底：window 中是否仍有豆包窗口
    out2, _ = adb_shell("dumpsys", "window")
    return DOUBAO_PKG in out2
