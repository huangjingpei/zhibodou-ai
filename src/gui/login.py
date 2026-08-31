# ====================== PDK 登录 / 设备激活窗口 ======================
# 布局：左侧 380 蓝色渐变 banner + 右侧 540 操作区（登录、激活 + 版本号）。
# 风格：参考运营截图蓝白配色，圆角输入框 / 圆角按钮通过 Canvas 绘制。
# 业务：PDK 公共配置 → 业务发现 → 登录 → 会话校验 → 资料/设备许可证。
import os
import threading
import tkinter as tk
from tkinter import messagebox
from gui import theme
from pdk import auth_service as pdk_auth
from pdk.pdk_client import PdkClientError

# ====================== 字体层级系统（Typography Scale） ======================
# 目标：靠「字号 + 字重 + 颜色」三重梯度建立视觉层次，而不是各处随手写死数值。
# 从强到弱共 7 级，每级都有明确用途，改一处即可全局生效。
FS_DISPLAY = 28   # banner 项目名 —— 全窗口最强视觉焦点
FS_H1      = 22   # 右侧主标题「欢迎使用智播豆」
FS_H2      = 14   # tab 标签
FS_BODY    = 13   # 输入框正文（中文可读性下限，不要再小）
FS_CAPTION = 12   # 副标题 / 辅助说明
FS_SMALL   = 11   # checkbox / 链接 / 版本号
FS_TINY    = 9    # 版权等最弱信息


_CN_FONT_CANDIDATES = (
    "Microsoft YaHei UI",   # 首选：微软为 UI 优化的版本，行高更小、字距更紧
    "微软雅黑",
    "Microsoft YaHei",
    "PingFang SC",          # macOS
    "SimHei",
    "System",               # Windows 保底
)
_cn_font_cache = None


def _get_cn_font():
    """挑选系统里真实存在的中文字体（带缓存）。

    ⚠️ 必须惰性调用：`tkfont.families()` 需要先存在 Tk root 实例，而本模块
    通常在 `tk.Tk()` 之前就被 import（main.py 顶部 import）。若在模块级求值，
    会因拿不到字体列表而静默退化成 System —— 真机上明明有雅黑却用不上。
    """
    global _cn_font_cache
    if _cn_font_cache:
        return _cn_font_cache
    try:
        import tkinter.font as tkfont
        avail = set(tkfont.families())
    except Exception:
        avail = set()
    if not avail:
        # Tk root 尚未建立（模块导入期常见）。此时【绝不能缓存】兜底值，
        # 否则会把 System 永久固化，后面即使 root 就绪也用不上真正的雅黑。
        return "System"
    for name in _CN_FONT_CANDIDATES:
        if name in avail:
            _cn_font_cache = name
            return name
    return "System"


FONT_EN = "Segoe UI"        # 英文/数字（logo 字母、版本号）


def f(size, weight="normal"):
    """构造中文字体元组，统一入口，避免散落的字号魔法数字。"""
    return (_get_cn_font(), size, weight)


def f_en(size, weight="normal"):
    return (FONT_EN, size, weight)


# 与主控台统一的深海蓝视觉系统。
CLR_BG          = theme.BG
CLR_TEXT        = theme.TEXT
CLR_TEXT_SUB    = theme.TEXT_MUTED
CLR_TEXT_HINT   = theme.TEXT_MUTED
CLR_TEXT_FAINT  = theme.TEXT_FAINT
CLR_INPUT_BG    = theme.SURFACE_SOFT
CLR_INPUT_BORDER = theme.BORDER
CLR_INPUT_FOCUS = theme.BORDER_FOCUS
CLR_TAB_ACTIVE  = theme.PRIMARY_HOVER
CLR_TAB_INACTIVE = theme.TEXT_MUTED

CLR_ICON        = CLR_TEXT_HINT   # 输入框图标默认色
CLR_ICON_FOCUS  = CLR_INPUT_FOCUS # 输入框图标聚焦色（跟随边框变蓝）

CLR_BTN_LOGIN   = theme.PRIMARY
CLR_BTN_ACTIVE  = theme.PRIMARY
CLR_BANNER_DARK = "#27346F"
CLR_BANNER_MID  = "#315DC7"
CLR_BANNER_LIGHT = "#176F9C"
# banner 上的文字：白 → 淡蓝 → 更淡蓝，三级层次
CLR_BANNER_TEXT  = "#ffffff"
CLR_BANNER_SUB   = "#D7E8FF"
CLR_BANNER_FAINT = "#9ECFE0"

CURRENT_VERSION = "1.7.0"


class LoginWindow:
    """登录窗口控制器。挂在任意父 Tk/Toplevel root 上即生效。

    用法：
        root = tk.Tk()
        login = LoginWindow(root, on_success=lambda: print("跳主窗口"))
        root.mainloop()
    """

    def __init__(self, parent_root, on_success=None, on_close=None):
        self.parent = parent_root
        self.on_success = on_success or (lambda: None)
        self.on_close   = on_close   or (lambda: None)

        # 控件引用（被 self._draw_* 填充）
        self.tabs = {}               # tab_key -> {btn, frame}
        self.active_key = "login"
        self._underline_pos = None      # 下划线上次位置，用于防抖去重
        self._remember_hint_var = tk.StringVar(value="登录状态仅保留在本次运行中")
        self._auth_busy = False
        # 每个 tab 的字段引用：{account_entry, password_entry, ...}
        self._login_fields  = {}
        self._active_fields = {}

        self._set_window_meta()
        self._build()
        # 关闭 = 退出整个程序（基于 parent 通常是主 root）
        self.parent.protocol("WM_DELETE_WINDOW", self._on_window_close)

    # ------------------------ 顶层窗口元信息 ------------------------
    def _set_window_meta(self):
        try:
            self.parent.title("智播豆 · 登录")
        except Exception:
            pass
        try:
            self.parent.geometry("980x640")
            self.parent.resizable(False, False)
            self.parent.configure(bg=CLR_BG)
        except Exception:
            pass

    # ------------------------ 主布局 ------------------------
    def _build(self):
        # 顶层容器（在 root 上铺满）
        self._root_frame = tk.Frame(self.parent, bg=CLR_BG)
        self._root_frame.place(x=0, y=0, relwidth=1, relheight=1)

        self._build_left_banner(self._root_frame)
        self._build_right_panel(self._root_frame)

    # ------------------------ 左侧 Banner ------------------------
    def _build_left_banner(self, parent):
        left = tk.Frame(parent, bg=CLR_BANNER_MID, width=400, height=640)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        # 用 Canvas 画渐变背景与装饰
        self._banner_canvas = tk.Canvas(left, bd=0, highlightthickness=0,
                                        bg=CLR_BANNER_MID, width=380, height=620)
        self._banner_canvas.pack(fill=tk.BOTH, expand=True)
        self._banner_canvas.bind("<Configure>", self._on_banner_resize)

    def _on_banner_resize(self, event):
        c = self._banner_canvas
        w, h = event.width, event.height
        c.delete("bg")
        if w <= 1 or h <= 1:
            return
        # 靛青到青绿的品牌渐变，与主控台顶部渐变保持同一视觉语言。
        steps = max(40, w // 4)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            x0 = int(i * w / steps)
            x1 = int((i + 1) * w / steps)
            c.create_rectangle(x0, 0, x1, h, outline="",
                                fill=theme.mix_hex(CLR_BANNER_DARK, CLR_BANNER_LIGHT, t), tags="bg")
        # 角落装饰：两枚淡蓝白实心点 + 一枚描边圆环，层次感更强、不挡 logo。
        # 全部退到四角，避开中央 logo 区与底部版权文字。
        c.delete("deco")
        # ① 实心点（极淡的蓝白，与渐变底色自然融合）
        for (cx, cy, rr, color) in [
            (w * 0.10, h * 0.09, 13, "#93c5fd"),
            (w * 0.90, h * 0.93, 20, "#bfdbfe"),
            (w * 0.95, h * 0.07,  9, "#dbeafe"),
        ]:
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                          outline="", fill=color, tags="deco")
        # ② 描边圆环（空心，带一点科技感）
        for (cx, cy, rr, color, lw) in [
            (w * 0.10, h * 0.09, 26, "#bfdbfe", 2),
            (w * 0.90, h * 0.93, 34, "#93c5fd", 2),
        ]:
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                          outline=color, width=lw, fill="", tags="deco")

        # 极淡网格只提供空间层次，不与品牌文字争夺注意力。
        for x in range(0, w, 80):
            c.create_line(x, 0, x, h, fill="#83A9D2", stipple="gray12", tags="deco")
        for y in range(0, h, 80):
            c.create_line(0, y, w, y, fill="#83A9D2", stipple="gray12", tags="deco")

        # 中心 logo + 文字（四级层次：logo字母 > 项目名 > 副标题 > 版本/版权）
        c.delete("fg")
        cx, cy = w / 2, h * 0.34
        rr = 56
        # L0 logo 圆环 + 字母
        c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                      outline=CLR_BANNER_TEXT, width=2, fill="", tags="fg")
        c.create_text(cx, cy, text="ZD",
                      fill=CLR_BANNER_TEXT, font=f_en(24, "bold"), tags="fg")
        c.create_text(cx, 42, text="AI LIVE OPERATIONS",
                      fill=CLR_BANNER_SUB, font=f_en(9, "bold"), tags="fg")
        # L1 项目名（最大号 + bold + 纯白）
        c.create_text(cx, cy + rr + 38, text="智播豆",
                      fill=CLR_BANNER_TEXT, font=f(FS_DISPLAY, "bold"), tags="fg")
        # L2 副标题（小号 + 淡蓝，弱化）
        c.create_text(cx, cy + rr + 76,
                      text="AI 智能直播管控系统",
                      fill=CLR_BANNER_SUB, font=f(FS_CAPTION), tags="fg")
        # L3 版本 / 版权（最弱，退到更淡的蓝）
        c.create_text(cx, h - 56, text="v %s" % CURRENT_VERSION,
                      fill=CLR_BANNER_FAINT, font=f_en(FS_SMALL), tags="fg")
        c.create_text(cx, h - 30,
                      text="© 杭州智鑫科技 · 智播豆",
                      fill=CLR_BANNER_FAINT, font=f(FS_TINY), tags="fg")

    # ------------------------ 右侧面板 ------------------------
    def _build_right_panel(self, parent):
        right = tk.Frame(parent, bg=CLR_BG, width=580, height=640)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        right.pack_propagate(False)

        # ----- 顶部欢迎语 -----
        head = tk.Frame(right, bg=CLR_BG, height=108)
        head.pack(fill=tk.X, padx=48, pady=(28, 0))
        head.pack_propagate(False)
        tk.Label(head, text="PDK SECURE ACCESS", bg=CLR_BG, fg=CLR_TAB_ACTIVE,
                 font=f_en(9, "bold"), anchor="w").pack(fill=tk.X, pady=(0, 7))
        # L1 主标题：最大号 + bold + 最深色
        tk.Label(head, text="欢迎使用智播豆", bg=CLR_BG, fg=CLR_TEXT,
                 font=f(FS_H1, "bold"), anchor="w").pack(fill=tk.X)
        # L2 副标题：小号 + 次级灰，拉开层次
        tk.Label(head, text="登录 AI 直播工作台，继续你的自动化直播流程", bg=CLR_BG, fg=CLR_TEXT_SUB,
                 font=f(FS_CAPTION), anchor="w").pack(fill=tk.X, pady=(8, 0))

        # ----- tab 行 -----
        tab_bar = tk.Frame(right, bg=CLR_BG, height=46)
        tab_bar.pack(fill=tk.X, padx=48, pady=(8, 0))
        tab_bar.pack_propagate(False)

        tab_defs = [
            ("login",   "登录"),
            ("active",  "激活"),
        ]
        for key, label in tab_defs:
            btn = tk.Label(tab_bar, text=label, bg=CLR_BG,
                           fg=CLR_TAB_INACTIVE, font=f(FS_H2),
                           padx=18, pady=10, cursor="hand2")
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda _e, k=key: self._switch_tab(k))
            self.tabs[key] = {"btn": btn}

        # 激活 tab 的下划线：绝对定位到当前 tab 正下方，切换时跟随移动
        self._tab_bar = tab_bar
        self._tab_underline = tk.Frame(tab_bar, bg=CLR_TAB_ACTIVE, height=3)
        # 容器尺寸变化（DPI 缩放 / 字体回退导致 tab 变宽）时重新贴合
        tab_bar.bind("<Configure>",
                     lambda _e: self._place_underline(self.active_key))

        # tab 下方分隔线
        self._tab_divider = tk.Frame(right, bg=CLR_INPUT_BORDER, height=1)
        self._tab_divider.pack(fill=tk.X, padx=48, pady=(0, 0))

        # ----- 内容区 -----
        self._content = tk.Frame(right, bg=CLR_BG)
        self._content.pack(fill=tk.BOTH, expand=True, padx=48, pady=(20, 0))

        for key, label in tab_defs:
            tab_frame = tk.Frame(self._content, bg=CLR_BG)
            self.tabs[key]["frame"] = tab_frame
            if key == "login":
                self._build_login_tab(tab_frame)
            else:
                self._build_active_tab(tab_frame)

        # ----- 版本号 -----
        foot = tk.Frame(right, bg=CLR_BG, height=44)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        foot.pack_propagate(False)
        tk.Label(foot, text="当前版本：%s" % CURRENT_VERSION,
                 bg=CLR_BG, fg=CLR_TEXT_FAINT,
                 font=f(FS_SMALL)).pack(pady=10)

        # 默认激活第一个 tab
        self._switch_tab("login")

    # ------------------------ tab 切换 ------------------------
    def _switch_tab(self, key):
        if key not in self.tabs:
            return
        self.active_key = key
        for k, slot in self.tabs.items():
            slot["frame"].pack_forget()
            # 未激活：次级灰 + 常规字重
            slot["btn"].config(fg=CLR_TAB_INACTIVE, font=f(FS_H2))
        self.tabs[key]["frame"].pack(fill=tk.BOTH, expand=True)
        # 激活：主蓝 + 加粗 —— 颜色之外再叠一层字重差，层次更明确
        self.tabs[key]["btn"].config(fg=CLR_TAB_ACTIVE, font=f(FS_H2, "bold"))
        self._place_underline(key)

    def _place_underline(self, key):
        """把下划线 place 到激活 tab 的正下方（宽度 = tab 文字宽度）。

        坑：构造期首帧 Tk 还没完成布局，btn.winfo_width() 返回 1；此时若直接
        return，下划线就永远定位不上（表现为"启动时默认 tab 没有下划线，切一次
        tab 才出现"）。所以宽度不足时要用 after 重试，而不是放弃。
        """
        def _do(attempt=0):
            try:
                btn = self.tabs[key]["btn"]
                bar_h = self._tab_bar.winfo_height() or 46
                x = btn.winfo_x()
                w = btn.winfo_width()
                if w <= 1:
                    # 布局未稳定 —— 最多重试约 2 秒，避免无限循环
                    # （慢机器上首次字体度量可能要几百毫秒，实测沙箱约 600ms 收敛）
                    if attempt < 100:
                        self.parent.after(20, lambda: _do(attempt + 1))
                    return
                y = bar_h - 3
                # ⚠️ 位置没变就跳过 place：tab_bar 的 <Configure> 回调和 place()
                # 会互相触发（place 改变子控件几何 → 再触发 Configure → 再 place），
                # 形成 idle 任务死循环，让 update_idletasks() 永远返回不了。
                if self._underline_pos == (key, x, w, y):
                    return
                self._underline_pos = (key, x, w, y)
                self._tab_underline.place(x=x, y=y, width=w, height=3)
                self._tab_underline.lift()
            except Exception:
                pass
        self.parent.after_idle(lambda: _do(0))

    # ------------------------ 输入框构造助手 ------------------------
    def _set_field_value(self, entry, value):
        """清掉 placeholder 后写入真实值，并把文字色回到主色。"""
        entry.delete(0, tk.END)
        entry.insert(0, value)
        entry.config(fg=CLR_TEXT)

    def _build_input_field(self, parent, icon_key, placeholder,
                           show=None, width_px=None):
        """构造"自绘图标 + placeholder + focus 高亮边框"的输入行。

        icon_key: 'user' / 'lock' / 'key' / 'card'（见 ICON_PAINTERS）
        返回 (外层 frame, entry)。
        """
        wrap = tk.Frame(parent, bg=CLR_INPUT_BG,
                        highlightbackground=CLR_INPUT_BORDER,
                        highlightcolor=CLR_INPUT_FOCUS,
                        highlightthickness=1, bd=0)
        wrap.configure(height=50)
        wrap.pack(fill=tk.X, pady=7)
        wrap.pack_propagate(False)

        # 图标：Canvas 自绘单色，聚焦时随边框一起变蓝（颜色联动强化焦点反馈）
        icon_canvas = tk.Canvas(wrap, width=ICON_SIZE, height=ICON_SIZE,
                                bg=CLR_INPUT_BG, bd=0, highlightthickness=0)
        icon_canvas.pack(side=tk.LEFT, padx=(12, 6))
        painter = ICON_PAINTERS.get(icon_key)

        def _paint_icon(color):
            icon_canvas.delete("all")
            if painter:
                painter(icon_canvas, ICON_SIZE, color)

        entry = tk.Entry(wrap, bd=0, bg=CLR_INPUT_BG, fg=CLR_TEXT_HINT,
                         font=f(FS_BODY),
                         insertbackground=CLR_TEXT,
                         relief="flat", highlightthickness=0)
        if width_px:
            entry.configure(width=width_px)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12), pady=12)
        entry.insert(0, placeholder)
        if not show:
            entry.config(show="")

        def _on_focus_in(_e=None):
            wrap.config(highlightbackground=CLR_INPUT_FOCUS,
                        highlightcolor=CLR_INPUT_FOCUS)
            _paint_icon(CLR_ICON_FOCUS)
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(fg=CLR_TEXT, show=show or "")

        def _on_focus_out(_e=None):
            wrap.config(highlightbackground=CLR_INPUT_BORDER)
            _paint_icon(CLR_ICON)
            if not entry.get():
                entry.insert(0, placeholder)
                entry.config(fg=CLR_TEXT_HINT, show="")

        entry.bind("<FocusIn>", _on_focus_in)
        entry.bind("<FocusOut>", _on_focus_out)
        _paint_icon(CLR_ICON)   # 初始为灰色
        return wrap, entry

    def _build_rounded_button(self, parent, text, fill, cmd,
                              height=48, font_size=14, radius=12):
        """圆角按钮：Canvas 精确拼合（4 个 90° CHORD 弧 + 3 个矩形）。

        ⚠️ 不要用 create_polygon(..., smooth=True) 画圆角：Tk 8.6 的 smooth 会把
        多边形当成 B 样条控制点做插值，矩形会被扭曲成不可控形状（曾渲染成横贯
        整行的粗长条）。这里用「弧 + 矩形」拼合，圆角半径可控、跨平台一致。

        附带 hover 高亮（把底色提亮 12%）与按下反馈。
        """
        c = tk.Canvas(parent, height=height, bg=CLR_BG,
                      bd=0, highlightthickness=0, cursor="hand2")
        c.pack(fill=tk.X, pady=(12, 0))

        state = {"hover": False, "pressed": False}

        def _paint(_e=None):
            c.delete("all")
            w = c.winfo_width()
            h = c.winfo_height()
            if w <= 1 or h <= 1:
                return  # 布局未完成，等下一个 <Configure>
            color = fill
            if state["pressed"]:
                color = _shade(fill, 0.88)      # 按下：压暗
            elif state["hover"]:
                color = _shade(fill, 1.12)      # 悬停：提亮
            _draw_rounded_rect(c, 1, 1, w - 1, h - 1, radius,
                               fill=color, outline="")
            c.create_text(w / 2, h / 2, text=text, fill="#ffffff",
                          font=f(font_size, "bold"))

        def _on_enter(_e=None):
            state["hover"] = True
            _paint()

        def _on_leave(_e=None):
            state["hover"] = False
            state["pressed"] = False
            _paint()

        def _on_press(_e=None):
            state["pressed"] = True
            _paint()

        def _on_release(_e=None):
            was_pressed = state["pressed"]
            state["pressed"] = False
            _paint()
            if was_pressed:
                try:
                    cmd()
                except Exception:
                    import traceback
                    traceback.print_exc()

        c.bind("<Configure>", _paint)
        c.bind("<Enter>", _on_enter)
        c.bind("<Leave>", _on_leave)
        c.bind("<ButtonPress-1>", _on_press)
        c.bind("<ButtonRelease-1>", _on_release)
        return c

    # ------------------------ 登录 tab ------------------------
    def _build_login_tab(self, parent):
        # 变量名用 tab 而非 f —— 后者会遮蔽模块级的字体构造函数 f()
        tab = tk.Frame(parent, bg=CLR_BG)
        tab.pack(fill=tk.BOTH, expand=True)
        _, account = self._build_input_field(tab, "user", "请输入手机号")
        _, password = self._build_input_field(tab, "lock", "请输入密码", show="*")
        if os.getenv("PDK_PHONE"):
            self._set_field_value(account, os.getenv("PDK_PHONE", ""))
        if os.getenv("PDK_PASSWORD"):
            self._set_field_value(password, os.getenv("PDK_PASSWORD", ""))
        self._login_fields = {"account": account, "password": password}

        # 记住登录状态 + 换绑设备 行
        opt_row = tk.Frame(tab, bg=CLR_BG)
        opt_row.pack(fill=tk.X, pady=(4, 0))
        cb = tk.Label(opt_row, text=self._remember_hint_var.get(),
                      bg=CLR_BG, fg=CLR_TEXT_SUB, font=f(FS_SMALL))
        cb.pack(side=tk.LEFT)
        self._remember_hint_var.trace_add("write",
            lambda *_: cb.config(text=self._remember_hint_var.get()))

        rebind = tk.Label(opt_row, text="设备换绑请联系管理员", bg=CLR_BG,
                          fg=CLR_TAB_ACTIVE, font=f(FS_SMALL, "underline"),
                          cursor="hand2")
        rebind.pack(side=tk.RIGHT)
        rebind.bind("<Button-1>",
                    lambda _e: self._notice("请联系管理员解绑原设备许可证后再登录"))

        self._build_rounded_button(
            tab, "登录", CLR_BTN_LOGIN, cmd=self._do_login, font_size=FS_BODY + 1)

    def _do_login(self):
        account = self._login_fields["account"].get().strip()
        password = self._login_fields["password"].get()
        if not account or account == "请输入手机号":
            self._notice("请输入手机号", error=True)
            return
        if not password or password == "请输入密码":
            self._notice("请输入密码", error=True)
            return
        # 与 pdk_client.py::_demo 一致：若环境变量配置了卡密，普通登录也携带它。
        self._start_pdk_auth(account, password, os.getenv("PDK_CARD_KEY", "").strip())

    # ------------------------ 激活 tab ------------------------
    def _build_active_tab(self, parent):
        tab = tk.Frame(parent, bg=CLR_BG)
        tab.pack(fill=tk.BOTH, expand=True)
        _, account = self._build_input_field(tab, "user", "请输入手机号")
        _, password = self._build_input_field(tab, "lock", "请输入密码", show="*")
        _, license_key = self._build_input_field(tab, "card", "请输入卡密")
        if os.getenv("PDK_PHONE"):
            self._set_field_value(account, os.getenv("PDK_PHONE", ""))
        if os.getenv("PDK_PASSWORD"):
            self._set_field_value(password, os.getenv("PDK_PASSWORD", ""))
        if os.getenv("PDK_CARD_KEY"):
            self._set_field_value(license_key, os.getenv("PDK_CARD_KEY", ""))
        self._active_fields = {"account": account, "password": password, "license": license_key}
        self._build_rounded_button(
            tab, "立即兑换", CLR_BTN_ACTIVE, cmd=self._do_activate,
            font_size=FS_BODY + 1)

    def _do_activate(self):
        account = self._active_fields["account"].get().strip()
        password = self._active_fields["password"].get()
        key = self._active_fields["license"].get().strip()
        if not account or account == "请输入手机号":
            self._notice("请输入手机号", error=True)
            return
        if not password or password == "请输入密码":
            self._notice("请输入密码", error=True)
            return
        if not key or key == "请输入卡密":
            self._notice("请输入卡密", error=True)
            return
        self._start_pdk_auth(account, password, key)

    def _start_pdk_auth(self, phone, password, card_key=""):
        """后台执行 PDK 网络认证，所有 Tk 操作仍回到主线程。"""
        if self._auth_busy:
            return
        self._auth_busy = True
        self._remember_hint_var.set("正在连接 PDK 授权服务器…")

        def _worker():
            try:
                result = pdk_auth.authenticate(phone, password, card_key)
            except Exception as exc:
                try:
                    self.parent.after(0, lambda e=exc: self._auth_failed(e, phone, password))
                except tk.TclError:
                    pass
                return
            try:
                self.parent.after(0, lambda r=result: self._auth_succeeded(r))
            except tk.TclError:
                pass

        threading.Thread(target=_worker, name="pdk-login", daemon=True).start()

    def _auth_failed(self, exc, phone, password):
        self._auth_busy = False
        self._remember_hint_var.set("登录状态仅保留在本次运行中")
        self._notice("PDK 登录失败\n\n" + pdk_auth.format_error(exc), error=True)
        if isinstance(exc, PdkClientError) and exc.code == 40380:
            self._switch_tab("active")
            self._set_field_value(self._active_fields["account"], phone)
            self._set_field_value(self._active_fields["password"], password)

    def _auth_succeeded(self, result):
        self._auth_busy = False
        self._remember_hint_var.set("PDK 会话已验证")
        self._notice("登录成功\n%s\n正在进入主控台…" % result.display_detail())
        self.parent.after(150, self.on_success)

    # ------------------------ 消息提示 ------------------------
    def _notice(self, msg, error=False):
        """统一弹提示：error=True 用 showerror，否则 showinfo。
        注意：必须在主线程调用；若被业务线程调用，要先 .after 到主线程。"""
        if error:
            messagebox.showerror("提示", msg, parent=self.parent)
        else:
            messagebox.showinfo("提示", msg, parent=self.parent)

    def _on_window_close(self):
        try:
            self.on_close()
        finally:
            try:
                self.parent.destroy()
            except Exception:
                pass


# ====================== 自绘单色图标 ======================
# 不用彩色 emoji：它在灰白界面里颜色不可控、不同系统字形还不一致，会破坏
# 层次感。这里用 Canvas 画 16px 线性图标，单色、可跟随聚焦变色、跨平台一致。
ICON_SIZE = 18


def _draw_user_icon(canvas, size, color):
    """用户：头部圆 + 肩部弧。"""
    s, cx = size, size / 2
    hr = s * 0.17
    canvas.create_oval(cx - hr, s * 0.24 - hr, cx + hr, s * 0.24 + hr,
                       outline=color, width=1.6)
    canvas.create_arc(cx - s * 0.27, s * 0.42, cx + s * 0.27, s * 1.0,
                      start=0, extent=180, style=tk.ARC, outline=color, width=1.6)


def _draw_lock_icon(canvas, size, color):
    """锁：上半弧（锁梁）+ 圆角矩形（锁体）。"""
    s, cx = size, size / 2
    canvas.create_arc(cx - s * 0.17, s * 0.20, cx + s * 0.17, s * 0.62,
                      start=0, extent=180, style=tk.ARC, outline=color, width=1.6)
    _draw_rounded_rect(canvas, cx - s * 0.27, s * 0.54, cx + s * 0.27, s * 0.88,
                       s * 0.06, fill=color, outline="")


def _draw_key_icon(canvas, size, color):
    """钥匙：圆环 + 斜杆 + 两道齿。"""
    s = size
    r = s * 0.15
    cx, cy = s * 0.34, s * 0.36
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                       outline=color, width=1.6)
    canvas.create_line(cx + r * 0.7, cy + r * 0.7, s * 0.84, s * 0.80,
                       fill=color, width=1.6)
    canvas.create_line(s * 0.70, s * 0.63, s * 0.79, s * 0.54, fill=color, width=1.6)
    canvas.create_line(s * 0.78, s * 0.71, s * 0.87, s * 0.62, fill=color, width=1.6)


def _draw_card_icon(canvas, size, color):
    """卡密：圆角卡片 + 一条横线。"""
    s = size
    canvas.create_rectangle(s * 0.12, s * 0.24, s * 0.88, s * 0.78,
                            outline=color, width=1.5)
    canvas.create_line(s * 0.12, s * 0.42, s * 0.88, s * 0.42,
                       fill=color, width=1.5)
    canvas.create_line(s * 0.24, s * 0.60, s * 0.60, s * 0.60,
                       fill=color, width=1.5)


ICON_PAINTERS = {
    "user": _draw_user_icon,
    "lock": _draw_lock_icon,
    "key":  _draw_key_icon,
    "card": _draw_card_icon,
}


def _shade(hex_color, factor):
    """把 #rrggbb 按 factor 缩放亮度（>1 变亮，<1 变暗），用于 hover / 按下反馈。"""
    s = hex_color.lstrip("#")
    r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return "#%02x%02x%02x" % (r, g, b)


def _draw_rounded_rect(canvas, x1, y1, x2, y2, radius, **kwargs):
    """用四个实心圆和两个矩形拼出稳定、无缺角的圆角矩形。"""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    d = radius * 2
    canvas.create_oval(x1, y1, x1 + d, y1 + d, **kwargs)
    canvas.create_oval(x2 - d, y1, x2, y1 + d, **kwargs)
    canvas.create_oval(x2 - d, y2 - d, x2, y2, **kwargs)
    canvas.create_oval(x1, y2 - d, x1 + d, y2, **kwargs)
    canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, **kwargs)
    canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, **kwargs)
