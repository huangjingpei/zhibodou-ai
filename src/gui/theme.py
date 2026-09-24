"""智播豆桌面端统一视觉系统。

Tkinter 没有 CSS，本模块集中管理颜色、字体和通用控件，避免登录页与主控台
各自维护一套互相冲突的高饱和配色。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


# 高对比深色体系。大面积背景保持中性，只让主操作和状态使用彩色，避免
# 青、紫、绿同时争抢注意力。正文对比度也比上一版提高了一档。
# 高对比、低疲劳的黑曜石演播室控制台深色体系
BG = "#0B101B"
BG_ELEVATED = "#0F1626"
SURFACE = "#131C2D"
SURFACE_ALT = "#182337"
SURFACE_SOFT = "#1E2B42"
BORDER = "#223147"
BORDER_SUBTLE = "#1A2536"
BORDER_FOCUS = "#5874E8"

TEXT = "#FFFFFF"
TEXT_SOFT = "#E2E8F0"
TEXT_MUTED = "#94A3B8"
TEXT_FAINT = "#64748B"

# 主色与功能色：低饱和科技感，清晰区分操作与状态
PRIMARY = "#4F6EF7"
PRIMARY_HOVER = "#6582FF"
PRIMARY_MUTED = "#2D3F75"
CYAN = "#22D3EE"
TEAL = "#14B8A6"
GREEN = "#10B981"
GREEN_DARK = "#0D7B56"
AMBER = "#F59E0B"
RED = "#F43F5E"
RED_DARK = "#BE123C"
PURPLE = "#A855F7"

SLATE_BTN = "#223046"
SLATE_BTN_HOVER = "#2D3E59"

# ---------------- 字体系统规范体系 (Typography System) ----------------
_CN_FONT_CANDIDATES = (
    "Microsoft YaHei UI",   # 首选：微软专为 Windows UI 优化版本，行高紧凑、基线对齐佳
    "微软雅黑",
    "Microsoft YaHei",
    "PingFang SC",          # macOS
    "SimHei",
    "Segoe UI",
    "System",
)
_cn_font_cache: str | None = None


def get_ui_font_family() -> str:
    """自动探测系统可用的最佳 UI 中文字体族（带缓存）。"""
    global _cn_font_cache
    if _cn_font_cache:
        return _cn_font_cache
    try:
        import tkinter.font as tkfont
        avail = set(tkfont.families())
        for name in _CN_FONT_CANDIDATES:
            if name in avail:
                _cn_font_cache = name
                return name
    except Exception:
        pass
    _cn_font_cache = "Microsoft YaHei UI"
    return _cn_font_cache


FONT_UI = "Microsoft YaHei UI"
FONT_EN = "Segoe UI"
FONT_CODE = "Consolas"

# 统一字号阶梯规范 (Typography Scale)
FS_DISPLAY = 13     # 顶栏主品牌标题 / 核心关键数字
FS_TITLE = 12       # 弹窗主标题
FS_CARD_TITLE = 10  # 模块卡片标题 / 分组大标题
FS_BODY = 9         # 主界面正文字号 (输入框、下拉框、标准表单标签、主按钮)
FS_CAPTION = 8      # 辅助提示说明、状态胶囊徽章、次级元数据


def font(size: int = FS_BODY, weight: str = "normal") -> tuple[str, int, str]:
    """统一中西文 UI 字体元组。"""
    return get_ui_font_family(), size, weight


def font_en(size: int = FS_BODY, weight: str = "normal") -> tuple[str, int, str]:
    """英文/数字专用字体元组（适合版本号、代码代号等）。"""
    return FONT_EN, size, weight


def font_code(size: int = FS_BODY, weight: str = "normal") -> tuple[str, int, str]:
    """等宽代码/日志字体元组。"""
    return FONT_CODE, size, weight


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
        fieldbackground=SURFACE_ALT,
        background=SURFACE_SOFT,
        foreground=TEXT,
        arrowcolor=TEXT_MUTED,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(8, 4),
        font=font(FS_BODY),
    )
    style.map(
        "Zhibodou.TCombobox",
        fieldbackground=[("readonly", SURFACE_ALT)],
        foreground=[("readonly", TEXT)],
        selectbackground=[("readonly", SURFACE_ALT)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("focus", BORDER_FOCUS)],
    )
    root.option_add("*TCombobox*Listbox.background", SURFACE_ALT)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", PRIMARY)
    root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
    root.option_add("*TCombobox*Listbox.font", font(FS_BODY))
    return style


def card(parent: tk.Misc, title: str, *, accent: str = PRIMARY,
         padx: int = 10, pady: int = 8) -> tuple[tk.Frame, tk.Frame]:
    """创建带细描边和标题层的卡片，返回 (外框, 内容区)。
    外框附带 .header 属性，调用方可在卡片右上角放置轻量操作控件。"""
    outer = tk.Frame(parent, bg=BORDER, bd=0, highlightthickness=0)
    shell = tk.Frame(outer, bg=SURFACE, bd=0)
    shell.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    header = tk.Frame(shell, bg=SURFACE, height=28)
    header.pack(fill=tk.X, padx=padx, pady=(6, 2))
    header.pack_propagate(False)
    tk.Frame(header, bg=accent, width=3).pack(side=tk.LEFT, fill=tk.Y, pady=5)
    tk.Label(
        header, text=title, bg=SURFACE, fg=TEXT,
        font=font(FS_CARD_TITLE, "bold"), anchor="w",
    ).pack(side=tk.LEFT, padx=(7, 0))

    body = tk.Frame(shell, bg=SURFACE)
    body.pack(fill=tk.BOTH, expand=True, padx=padx, pady=(2, pady))
    
    outer.header = header
    return outer, body


def label(parent: tk.Misc, text: str, *, muted: bool = False,
          font_size: int = FS_BODY, bold: bool = False, **kwargs) -> tk.Label:
    return tk.Label(
        parent, text=text, bg=kwargs.pop("bg", SURFACE),
        fg=kwargs.pop("fg", TEXT_MUTED if muted else TEXT_SOFT),
        font=font(font_size, "bold" if bold else "normal"),
        **kwargs,
    )


def pill(parent: tk.Misc, text: str, *, bg: str = SURFACE_SOFT, fg: str = TEXT_MUTED,
         font_size: int = FS_CAPTION, bold: bool = True, padx: int = 7, pady: int = 2) -> tk.Label:
    """紧凑状态胶囊徽章"""
    return tk.Label(
        parent, text=text, bg=bg, fg=fg,
        font=font(font_size, "bold" if bold else "normal"),
        padx=padx, pady=pady,
    )


def entry(parent: tk.Misc, *, width: int | None = None, font_size: int = FS_BODY) -> tk.Entry:
    widget = tk.Entry(
        parent, bg=SURFACE_ALT, fg=TEXT, insertbackground=CYAN,
        selectbackground=PRIMARY, selectforeground="#FFFFFF",
        relief=tk.FLAT, bd=0, highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=BORDER_FOCUS,
        font=font(font_size),
    )
    if width is not None:
        widget.configure(width=width)
    return widget


def button(parent: tk.Misc, text: str, *, color: str = PRIMARY,
           active: str | None = None, fg: str = "#FFFFFF", width: int | None = None,
           command=None, state=tk.NORMAL, font_size: int = FS_BODY, bold: bool = True,
           padx: int = 8, pady: int = 3) -> tk.Button:
    options = dict(
        text=text, command=command, state=state,
        bg=color, activebackground=active or color,
        fg=fg, activeforeground=fg,
        disabledforeground=TEXT_FAINT,
        relief=tk.FLAT, bd=0, highlightthickness=0,
        cursor="hand2", padx=padx, pady=pady,
        font=font(font_size, "bold" if bold else "normal"),
    )
    if width is not None:
        options["width"] = width
    return tk.Button(parent, **options)


def text_area(parent: tk.Misc, text_widget_cls, font_size: int = FS_BODY, **kwargs):
    return text_widget_cls(
        parent,
        bg=SURFACE_ALT, fg=TEXT_SOFT, insertbackground=CYAN,
        selectbackground=PRIMARY, selectforeground="#FFFFFF",
        relief=tk.FLAT, bd=0, highlightthickness=1,
        highlightbackground=BORDER, highlightcolor=BORDER_FOCUS,
        font=font(font_size), padx=8, pady=6,
        **kwargs,
    )
