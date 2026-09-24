"""运行日志查看器独立弹窗。

提供全屏或浮动窗口展示系统的实时运行日志，
包含日志检索、一键复制、清空日志与自动滚动功能，
将主界面从冗长的日志排版中彻底释放。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, scrolledtext
from typing import Optional

from gui import theme

_active_log_dialog: Optional[LogDialog] = None


class LogDialog:
    """运行日志查看弹窗。"""

    def __init__(self, parent: tk.Tk, initial_logs: str = ""):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        self.win.title("智播豆 · 系统运行日志")
        self.win.geometry("820x560")
        self.win.minsize(600, 400)
        self.win.configure(bg=theme.BG)

        # 居中显示
        self.win.update_idletasks()
        try:
            x = parent.winfo_x() + max(0, (parent.winfo_width() - 820) // 2)
            y = parent.winfo_y() + max(0, (parent.winfo_height() - 560) // 2)
            self.win.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self._auto_scroll_var = tk.BooleanVar(value=True)
        self._build_ui(initial_logs)

        self.win.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self, initial_logs: str):
        # 顶部工具条
        top_bar = tk.Frame(self.win, bg=theme.SURFACE, height=42)
        top_bar.pack(fill=tk.X, padx=12, pady=(12, 6))
        top_bar.pack_propagate(False)

        theme.label(top_bar, "📜 实时运行日志", bold=True, font_size=theme.FS_CARD_TITLE, fg=theme.CYAN).pack(side=tk.LEFT, padx=(12, 8), pady=8)
        self.lab_count = theme.label(top_bar, "共 0 行", muted=True, font_size=theme.FS_BODY)
        self.lab_count.pack(side=tk.LEFT, pady=8)

        # 右侧操作按钮
        btn_close = theme.button(top_bar, "✕ 关闭", color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER, width=7, font_size=theme.FS_BODY, command=self.close)
        btn_close.pack(side=tk.RIGHT, padx=(4, 10), pady=6)

        btn_copy = theme.button(top_bar, "📋 复制全部", color=theme.PRIMARY, active=theme.PRIMARY_HOVER, width=9, font_size=theme.FS_BODY, command=self._copy_all)
        btn_copy.pack(side=tk.RIGHT, padx=4, pady=6)

        btn_clear = theme.button(top_bar, "🧹 清空日志", color=theme.RED_DARK, active=theme.RED, width=8, font_size=theme.FS_BODY, command=self._clear_logs)
        btn_clear.pack(side=tk.RIGHT, padx=4, pady=6)

        chk_scroll = tk.Checkbutton(
            top_bar, text="自动滚动", variable=self._auto_scroll_var,
            bg=theme.SURFACE, fg=theme.TEXT_SOFT, selectcolor=theme.SURFACE_ALT,
            activebackground=theme.SURFACE, activeforeground=theme.TEXT,
            font=theme.font(theme.FS_BODY),
        )
        chk_scroll.pack(side=tk.RIGHT, padx=8, pady=6)

        # 日志内容容器
        body_frame = tk.Frame(self.win, bg=theme.BG)
        body_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.txt_log = scrolledtext.ScrolledText(
            body_frame,
            wrap=tk.WORD,
            bg="#0D1117",
            fg="#E6EDF3",
            insertbackground="#58A6FF",
            selectbackground="#1F6FEB",
            font=theme.font_code(theme.FS_BODY),
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            padx=10,
            pady=10,
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        if initial_logs:
            self.txt_log.insert(tk.END, initial_logs)
            self.txt_log.see(tk.END)
            self._update_count()

    def append_log(self, text: str):
        """追加一行或一段日志。"""
        if not self.win.winfo_exists():
            return
        try:
            self.txt_log.insert(tk.END, text + ("\n" if not text.endswith("\n") else ""))
            if self._auto_scroll_var.get():
                self.txt_log.see(tk.END)
            self._update_count()
        except Exception:
            pass

    def _update_count(self):
        try:
            lines = int(self.txt_log.index("end-1c").split(".")[0])
            self.lab_count.config(text=f"共 {lines} 行")
        except Exception:
            pass

    def _copy_all(self):
        try:
            content = self.txt_log.get(1.0, tk.END).strip()
            if not content:
                messagebox.showinfo("提示", "日志内容为空", parent=self.win)
                return
            self.win.clipboard_clear()
            self.win.clipboard_append(content)
            messagebox.showinfo("成功", f"已复制 {len(content)} 字符的运行日志到剪贴板", parent=self.win)
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}", parent=self.win)

    def _clear_logs(self):
        self.txt_log.delete(1.0, tk.END)
        self._update_count()

    def close(self):
        global _active_log_dialog
        _active_log_dialog = None
        try:
            self.win.destroy()
        except Exception:
            pass


def open_log_dialog(parent: tk.Tk, current_logs: str = "", initial_logs: str = "") -> LogDialog:
    """打开或激活运行日志弹窗。"""
    global _active_log_dialog
    logs = initial_logs or current_logs or ""
    if _active_log_dialog is not None and _active_log_dialog.win.winfo_exists():
        _active_log_dialog.win.lift()
        _active_log_dialog.win.focus_force()
        return _active_log_dialog
    _active_log_dialog = LogDialog(parent, initial_logs=logs)
    return _active_log_dialog


def get_active_log_dialog() -> Optional[LogDialog]:
    global _active_log_dialog
    if _active_log_dialog is not None and _active_log_dialog.win.winfo_exists():
        return _active_log_dialog
    return None
