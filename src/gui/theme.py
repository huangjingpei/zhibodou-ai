"""智播豆桌面端统一视觉系统。

Tkinter 没有 CSS，本模块集中管理颜色、字体和通用控件，避免登录页与主控台
各自维护一套互相冲突的高饱和配色。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


# 高对比深色体系。大面积背景保持中性，只让主操作和状态使用彩色，避免
# 青、紫、绿同时争抢注意力。正文对比度也比上一版提高了一档。
BG = "#080F1C"
BG_ELEVATED = "#0B1422"
SURFACE = "#111C2B"
SURFACE_ALT = "#162538"
SURFACE_SOFT = "#1B2D43"
BORDER = "#34485F"
BORDER_FOCUS = "#7F98FF"

TEXT = "#FFFFFF"
TEXT_SOFT = "#E7EDF5"
TEXT_MUTED = "#AFBED0"
TEXT_FAINT = "#7F91A6"

PRIMARY = "#6D86F7"
PRIMARY_HOVER = "#8299FF"
CYAN = "#43C7D8"
TEAL = "#36C5A3"
GREEN = "#42D392"
AMBER = "#F4BC68"
RED = "#F16A78"
RED_DARK = "#CF4F61"
PURPLE = "#AA91F6"

FONT_UI = "Microsoft YaHei UI"
FONT_EN = "Segoe UI"


def font(size: int, weight: str = "normal") -> tuple[str, int, str]:
    return FONT_UI, size, weight


def mix_hex(start: str, end: str, t: float) -> str:
    a = tuple(int(start[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(end[i:i + 2], 16) for i in (1, 3, 5))
    rgb = tuple(round(x + (y - x) * t) for x, y in zip(a, b))
    return "#%02x%02x%02x" % rgb


def draw_horizontal_gradient(canvas: tk.Canvas, width: int, height: int,
                             start: str, end: str, *, tag: str = "gradient") -> None:
    canvas.delete(tag)
    steps = max(48, width // 5)
    for i in range(steps):
        x0 = int(i * width / steps)
        x1 = int((i + 1) * width / steps) + 1
        canvas.create_rectangle(
            x0, 0, x1, height,
            fill=mix_hex(start, end, i / max(steps - 1, 1)),
            outline="", tags=tag,
        )
    canvas.tag_lower(tag)


def configure_ttk(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Zhibodou.TCombobox",
        fieldbackground=SURFACE_SOFT,
        background=SURFACE_SOFT,
        foreground=TEXT,
        arrowcolor=TEXT_MUTED,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(9, 6),
        font=font(10),
    )
    style.map(
        "Zhibodou.TCombobox",
        fieldbackground=[("readonly", SURFACE_SOFT)],
        foreground=[("readonly", TEXT)],
        selectbackground=[("readonly", SURFACE_SOFT)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("focus", BORDER_FOCUS)],
    )
    root.option_add("*TCombobox*Listbox.background", SURFACE_SOFT)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", PRIMARY)
    root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
    return style


def card(parent: tk.Misc, title: str, *, accent: str = CYAN,
         padx: int = 12, pady: int = 10) -> tuple[tk.Frame, tk.Frame]:
    """创建带细描边和标题层的卡片，返回 (外框, 内容区)。"""
    outer = tk.Frame(parent, bg=BORDER, bd=0, highlightthickness=0)
    shell = tk.Frame(outer, bg=SURFACE, bd=0)
    shell.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    header = tk.Frame(shell, bg=SURFACE, height=30)
    header.pack(fill=tk.X, padx=padx, pady=(7, 0))
    header.pack_propagate(False)
    tk.Frame(header, bg=accent, width=3).pack(side=tk.LEFT, fill=tk.Y, pady=6)
    tk.Label(
        header, text=title, bg=SURFACE, fg=TEXT,
        font=font(11, "bold"), anchor="w",
    ).pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

    body = tk.Frame(shell, bg=SURFACE)
    body.pack(fill=tk.BOTH, expand=True, padx=padx, pady=(4, pady))
    return outer, body


def label(parent: tk.Misc, text: str, *, muted: bool = False,
          font_size: int = 10, bold: bool = False, **kwargs) -> tk.Label:
    return tk.Label(
        parent, text=text, bg=kwargs.pop("bg", SURFACE),
        fg=kwargs.pop("fg", TEXT_MUTED if muted else TEXT_SOFT),
        font=font(font_size, "bold" if bold else "normal"),
        **kwargs,
    )


def entry(parent: tk.Misc, *, width: int | None = None) -> tk.Entry:
    widget = tk.Entry(
        parent, bg=SURFACE_SOFT, fg=TEXT, insertbackground=CYAN,
        selectbackground=PRIMARY, selectforeground="#FFFFFF",
        relief=tk.FLAT, bd=0, highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=BORDER_FOCUS,
        font=font(10),
    )
    if width is not None:
        widget.configure(width=width)
    return widget


def button(parent: tk.Misc, text: str, *, color: str = PRIMARY,
           active: str | None = None, fg: str = "#FFFFFF", width: int | None = None,
           command=None, state=tk.NORMAL, font_size: int = 10) -> tk.Button:
    options = dict(
        text=text, command=command, state=state,
        bg=color, activebackground=active or color,
        fg=fg, activeforeground=fg,
        disabledforeground=TEXT_MUTED,
        relief=tk.FLAT, bd=0, highlightthickness=0,
        cursor="hand2", padx=12, pady=7,
        font=font(font_size, "bold"),
    )
    if width is not None:
        options["width"] = width
    return tk.Button(parent, **options)


def text_area(parent: tk.Misc, text_widget_cls, **kwargs):
    return text_widget_cls(
        parent,
        bg=SURFACE_ALT, fg=TEXT_SOFT, insertbackground=CYAN,
        selectbackground=PRIMARY, selectforeground="#FFFFFF",
        relief=tk.FLAT, bd=0, highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=BORDER_FOCUS,
        font=font(10), padx=8, pady=6,
        **kwargs,
    )
