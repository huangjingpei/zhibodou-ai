"""话术文件与 Windows 记事本管理模块。

管理 01.txt、02.txt、03.txt 三个区间话术文件：
1. 文件在 scripts/ 目录下持久化存储；
2. 支持点击调用系统记事本 notepad.exe 打开查看与修改；
3. 后台监听文件保存事件（mtime 变化），一旦保存成功自动关闭对应记事本窗口；
4. 提供 close_all_script_notepads() 兜底接口，在保存配置或启动直播时关闭所有已打开的记事本。
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Callable, Dict, Optional

from core.paths import SCRIPTS_DIR

SCRIPT_KEYS = ("01", "02", "03")

SCRIPT_FILENAME_MAP: Dict[str, str] = {
    "01": "01.txt",
    "02": "02.txt",
    "03": "03.txt",
}

DEFAULT_SCRIPTS: Dict[str, str] = {
    "01": "留人话术内容填这里，要求500字",
    "02": "产品讲解话术内容填这里，要求500字",
    "03": "逼单促单话术内容填这里，要求500字",
}

# 追踪打开的记事本进程信息：key -> dict
_tracked_notepads: Dict[str, dict] = {}
_track_lock = threading.Lock()
_monitor_thread: Optional[threading.Thread] = None
_monitor_stop_event = threading.Event()


def get_script_path(key: str) -> str:
    """获取指定区间的话术文件绝对路径。key: '01' | '02' | '03' 或完整文件名。"""
    filename = SCRIPT_FILENAME_MAP.get(str(key).strip())
    if not filename:
        raw = str(key).strip()
        if raw.endswith(".txt"):
            filename = raw
        else:
            filename = f"{raw}.txt"
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    return os.path.join(SCRIPTS_DIR, filename)


def ensure_script_files_exist() -> None:
    """确保 01.txt, 02.txt, 03.txt 均已创建；若缺失则从 config 迁移或填入默认模版。"""
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    cfg_cmd_map = {"01": "cmd1", "02": "cmd2", "03": "cmd3"}

    # 尝试从 config.json 读取已有话术内容迁移到 txt
    cfg_data = {}
    try:
        from settings import config
        cfg_data = config.load_config() or {}
    except Exception:
        pass

    for key in SCRIPT_KEYS:
        path = get_script_path(key)
        if not os.path.exists(path):
            cfg_field = cfg_cmd_map.get(key, "")
            init_text = str(cfg_data.get(cfg_field) or "").strip()
            if not init_text:
                init_text = DEFAULT_SCRIPTS.get(key, "")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(init_text)
            except Exception:
                pass


def read_script_content(key: str, default: str = "") -> str:
    """安全读取话术文本，依次兼容 utf-8-sig、utf-8、gb18030、gbk 编码。"""
    path = get_script_path(key) if not os.path.isabs(key) else key
    if not os.path.exists(path):
        return default
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read().strip()
        except UnicodeDecodeError:
            continue
        except Exception:
            break
    return default


def write_script_content(key: str, content: str) -> bool:
    """写入指定话术文件，统一采用 UTF-8 编码。"""
    path = get_script_path(key) if not os.path.isabs(key) else key
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception:
        return False


def get_script_word_count(key: str) -> int:
    """获取指定话术文件的有效字数（剔除首尾空白字符）。"""
    return len(read_script_content(key))


def _monitor_loop() -> None:
    """后台监听器：轮询已打开的记事本，当检测到文件保存（mtime 变化）后自动关闭记事本。"""
    while not _monitor_stop_event.is_set():
        time.sleep(0.4)
        with _track_lock:
            if not _tracked_notepads:
                continue
            to_remove = []
            for key, info in list(_tracked_notepads.items()):
                proc: subprocess.Popen = info.get("proc")
                path: str = info.get("path")
                initial_mtime: float = info.get("mtime", 0.0)
                on_saved: Optional[Callable] = info.get("on_saved")
                log_fn: Callable = info.get("log_fn", print)

                if proc is None:
                    to_remove.append(key)
                    continue

                # 检查进程是否已被人为手动关闭
                if proc.poll() is not None:
                    to_remove.append(key)
                    if on_saved:
                        try:
                            on_saved(key)
                        except Exception:
                            pass
                    continue

                # 检查文件是否被保存（修改时间增加）
                try:
                    curr_mtime = os.path.getmtime(path)
                except Exception:
                    curr_mtime = initial_mtime

                if curr_mtime > initial_mtime:
                    # 延时 0.25s 确保记事本完全写盘
                    time.sleep(0.25)
                    try:
                        proc.terminate()
                        try:
                            proc.wait(timeout=0.8)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    except Exception:
                        pass

                    filename = os.path.basename(path)
                    try:
                        log_fn(f"【话术策略】✅ 检测到 {filename} 已保存，记事本已自动关闭。")
                    except Exception:
                        pass

                    if on_saved:
                        try:
                            on_saved(key)
                        except Exception:
                            pass
                    to_remove.append(key)

            for key in to_remove:
                _tracked_notepads.pop(key, None)


def _ensure_monitor_running() -> None:
    global _monitor_thread
    with _track_lock:
        if _monitor_thread is None or not _monitor_thread.is_alive():
            _monitor_stop_event.clear()
            _monitor_thread = threading.Thread(
                target=_monitor_loop,
                name="script-notepad-monitor",
                daemon=True,
            )
            _monitor_thread.start()


def open_script_notepad(
    key: str,
    on_saved: Optional[Callable[[str], None]] = None,
    log_fn: Callable[[str], None] = print,
) -> bool:
    """调用系统记事本 notepad.exe 打开指定话术 txt 文件并开启保存监听。

    :param key: '01' | '02' | '03'
    :param on_saved: 文件保存或关闭后的回调函数 (接收 key 参数)
    :param log_fn: 日志输出函数
    :return: 是否成功拉起记事本
    """
    ensure_script_files_exist()
    path = get_script_path(key)
    if not os.path.exists(path):
        return False

    with _track_lock:
        # 如果已经打开了同一个记事本且仍在运行，不再重复打开
        existing = _tracked_notepads.get(key)
        if existing and existing.get("proc") and existing["proc"].poll() is None:
            filename = os.path.basename(path)
            log_fn(f"【话术策略】{filename} 记事本已在运行中，请在当前窗口中编辑。")
            return True

        try:
            curr_mtime = os.path.getmtime(path)
        except Exception:
            curr_mtime = time.time()

        try:
            proc = subprocess.Popen(["notepad.exe", path])
        except Exception as exc:
            log_fn(f"【话术策略】❌ 调用系统记事本失败：{exc}")
            return False

        _tracked_notepads[key] = {
            "proc": proc,
            "path": path,
            "mtime": curr_mtime,
            "on_saved": on_saved,
            "log_fn": log_fn,
        }

    _ensure_monitor_running()
    filename = os.path.basename(path)
    log_fn(f"【话术策略】📖 已打开 {filename}，修改后直接按 Ctrl+S 保存将自动关闭记事本。")
    return True


def close_all_script_notepads(log_fn: Optional[Callable[[str], None]] = None) -> int:
    """关闭所有当前通过本软件打开的话术记事本进程。返回关闭的进程数。"""
    closed_count = 0
    with _track_lock:
        for key, info in list(_tracked_notepads.items()):
            proc: subprocess.Popen = info.get("proc")
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.6)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    closed_count += 1
                except Exception:
                    pass
            on_saved = info.get("on_saved")
            if on_saved:
                try:
                    on_saved(key)
                except Exception:
                    pass
        _tracked_notepads.clear()

    if closed_count > 0 and log_fn:
        try:
            log_fn(f"【话术策略】已关闭 {closed_count} 个话术记事本窗口。")
        except Exception:
            pass
    return closed_count


def is_any_notepad_open() -> bool:
    """检查当前是否有话术记事本处于打开状态。"""
    with _track_lock:
        for info in _tracked_notepads.values():
            proc = info.get("proc")
            if proc and proc.poll() is None:
                return True
    return False
