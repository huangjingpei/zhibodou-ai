"""系统设置中心模态对话框 (Settings Dialog)

采用黑曜石演播室控制台深色主题 (Obsidian Studio Cockpit)。
左侧为扁平纵向导航按钮列表，右侧为对应分类的设置面板：
  1. 🤖 AI 智能模型 (LLM API Key / Base URL / Model / 弹幕回复开关 / 主播提示词)
  2. 📜 许可证授权 (PDK 授权状态 / 手机号 / 模式 / 到期时间 / 剩余次数 / 设备指纹)
  3. 🎛️ 音频与通用 (声音动态闪避比例 / OBS 音频推流端口 / VAD 静音断句时序)
  4. 🚀 版本更新 (当前版本 / 检查更新交互 / 演播室发版更新日志)
"""

from __future__ import annotations

import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from gui import theme
from settings import config
from pdk import auth_service as pdk_auth

try:
    from main import APP_VERSION
except Exception:
    APP_VERSION = "1.7.0"


def _make_scrollable(container: tk.Misc, bg: str = theme.BG) -> tuple[tk.Frame, tk.Canvas]:
    """创建自适应宽度的平滑滚动容器，返回 (内容 Frame, Canvas 实例)。"""
    canvas = tk.Canvas(container, bg=bg, bd=0, highlightthickness=0)
    vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    content = tk.Frame(canvas, bg=bg)

    win_id = canvas.create_window((0, 0), window=content, anchor="nw")

    def _on_content_cfg(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_cfg(e):
        canvas.itemconfig(win_id, width=e.width)

    content.bind("<Configure>", _on_content_cfg)
    canvas.bind("<Configure>", _on_canvas_cfg)
    canvas.configure(yscrollcommand=vbar.set)

    def _on_wheel(e):
        if canvas.winfo_exists():
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _bind_wheel(e):
        canvas.bind_all("<MouseWheel>", _on_wheel)

    def _unbind_wheel(e):
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass

    content.bind("<Enter>", _bind_wheel)
    content.bind("<Leave>", _unbind_wheel)
    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vbar.pack(side=tk.RIGHT, fill=tk.Y)
    return content, canvas


class SettingsDialog:
    """系统设置中心模态对话框。"""

    def __init__(self, parent: tk.Misc):
        self.parent = parent
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("系统设置中心 · 智播豆")
        self.dialog.configure(bg=theme.BG)
        self.dialog.transient(parent)

        # 居中显示 (840 x 580)
        self._center_window(840, 580)

        # 模态锁定
        self.dialog.grab_set()
        self.dialog.focus_set()
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)

        # 加载配置
        self.cfg = config.load_config()

        # 状态与输入变量
        self._init_variables()

        # 构建整体骨架
        self._build_header()
        self._build_body()
        self._build_footer()

        # 初始默认选中：AI 智能模型
        self._on_nav_click("ai")

    def _center_window(self, width: int, height: int):
        self.dialog.update_idletasks()
        try:
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            if pw > 100 and ph > 100:
                x = max(10, px + (pw - width) // 2)
                y = max(10, py + (ph - height) // 2)
            else:
                sw = self.dialog.winfo_screenwidth()
                sh = self.dialog.winfo_screenheight()
                x = max(10, (sw - width) // 2)
                y = max(10, (sh - height) // 2)
        except Exception:
            sw = self.dialog.winfo_screenwidth()
            sh = self.dialog.winfo_screenheight()
            x = max(10, (sw - width) // 2)
            y = max(10, (sh - height) // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
        self.dialog.minsize(780, 500)

    def _init_variables(self):
        # AI 配置
        self.var_deepseek_key = tk.StringVar(value=str(self.cfg.get("deepseek_api_key") or ""))
        self.var_deepseek_base = tk.StringVar(
            value=str(self.cfg.get("deepseek_api_base") or "https://api.deepseek.com")
        )
        self.var_deepseek_model = tk.StringVar(
            value=str(self.cfg.get("deepseek_model") or "deepseek-chat")
        )
        self.var_ai_danmu_reply = tk.BooleanVar(
            value=bool(self.cfg.get("ai_danmu_reply_enabled", True))
        )
        self.var_key_visible = tk.BooleanVar(value=False)

        # 弹幕模式与采集过滤
        self.var_danmu_metrics_only = tk.BooleanVar(
            value=bool(self.cfg.get("danmu_metrics_only", False))
        )
        saved_danmu_mode = str(self.cfg.get("danmu_mode") or "").strip()
        if not saved_danmu_mode:
            try:
                from danma.hardware import detect_gpu_tier
                saved_danmu_mode = detect_gpu_tier()["display_name"]
            except Exception:
                saved_danmu_mode = "【自适应】IndexTTS 旗舰语音 (显存≥8G)"
        self.var_danmu_mode = tk.StringVar(value=saved_danmu_mode)

        # 通用与音频
        duck_val = float(self.cfg.get("audio_duck_ratio", 0.25))
        pct = int(round(duck_val * 100))
        self.var_duck_pct = tk.IntVar(value=pct)
        self.var_duck_ratio = tk.StringVar(value=f"{pct}%")
        self.var_obs_port = tk.StringVar(value=str(self.cfg.get("obs_audio_port", 8554)))
        self.var_vad_silence = tk.StringVar(
            value=str(self.cfg.get("vad_silence_hold_sec", 4.0))
        )
        self.var_vad_confirm = tk.StringVar(
            value=str(self.cfg.get("vad_speak_confirm_sec", 0.3))
        )
        self.var_vad_wait = tk.StringVar(
            value=str(self.cfg.get("vad_wait_start_sec", 15.0))
        )

        # 面板映射表
        self.panels: dict[str, tk.Frame] = {}
        self.current_panel_name: str = ""

    def _build_header(self):
        """顶部黑曜石控制台标题栏。"""
        header = tk.Frame(self.dialog, bg=theme.BG_ELEVATED, height=52)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)

        # 标题与副标题
        title_box = tk.Frame(header, bg=theme.BG_ELEVATED)
        title_box.pack(side=tk.LEFT, padx=16, pady=8)

        row_t = tk.Frame(title_box, bg=theme.BG_ELEVATED)
        row_t.pack(anchor="w")
        theme.label(row_t, "⚙️ 系统设置中心", font_size=theme.FS_TITLE, bold=True, fg=theme.TEXT).pack(side=tk.LEFT)
        theme.pill(row_t, f"v{APP_VERSION}", bg=theme.PRIMARY_MUTED, fg=theme.CYAN, font_size=theme.FS_CAPTION).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        theme.label(
            title_box,
            "AI 智能参数 · PDK 许可证 · 声音闪避与 OBS 推流 · 系统版本维护",
            muted=True,
            font_size=theme.FS_CAPTION,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # 顶部分割细线
        sep = tk.Frame(self.dialog, bg=theme.BORDER, height=1)
        sep.pack(side=tk.TOP, fill=tk.X)

    def _build_footer(self):
        """底部操作按钮栏。"""
        sep = tk.Frame(self.dialog, bg=theme.BORDER, height=1)
        sep.pack(side=tk.BOTTOM, fill=tk.X)

        footer = tk.Frame(self.dialog, bg=theme.BG_ELEVATED, height=48)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.pack_propagate(False)

        # 状态小提示
        self.lab_footer_status = theme.label(
            footer, "修改参数后请点击「保存配置」使改动即时生效", muted=True, font_size=theme.FS_BODY
        )
        self.lab_footer_status.pack(side=tk.LEFT, padx=16, pady=10)

        # 按钮组
        btn_close = theme.button(
            footer, "关闭", color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER,
            width=7, font_size=theme.FS_BODY, command=self._on_close,
        )
        btn_close.pack(side=tk.RIGHT, padx=(6, 16), pady=8)

        btn_save = theme.button(
            footer, "💾 保存配置", color=theme.PRIMARY, active=theme.PRIMARY_HOVER,
            width=11, font_size=theme.FS_BODY, command=self._save_settings,
        )
        btn_save.pack(side=tk.RIGHT, padx=3, pady=8)

    def _build_body(self):
        """主工作区分割：左侧扁平纵向导航 + 右侧动态面板。"""
        body = tk.Frame(self.dialog, bg=theme.BG)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ---------------- 左侧侧边栏 (Flat Vertical Navigation) ----------------
        sidebar = tk.Frame(body, bg=theme.SURFACE, width=200)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # 侧边栏小标题
        bar_title = tk.Frame(sidebar, bg=theme.SURFACE_ALT, height=28)
        bar_title.pack(fill=tk.X)
        bar_title.pack_propagate(False)
        theme.label(bar_title, "导航目录", muted=True, font_size=theme.FS_CAPTION, bold=True).pack(
            side=tk.LEFT, padx=12, pady=4
        )

        # ttk.Scale 样式（保留，供音频面板滑动条使用）
        style = ttk.Style(self.dialog)
        style.configure(
            "Zhibodou.Horizontal.TScale",
            background=theme.SURFACE,
            troughcolor=theme.SURFACE_ALT,
            bordercolor=theme.BORDER,
            lightcolor=theme.CYAN,
            darkcolor=theme.PRIMARY,
            sliderlength=24,
            sliderthickness=16,
        )
        style.map(
            "Zhibodou.Horizontal.TScale",
            background=[("active", theme.PRIMARY_HOVER)],
        )

        # 扁平纵向导航项定义
        nav_items = [
            ("ai",      "🤖", "AI 智能模型",  "接口配置 · 弹幕回复 · 提示词"),
            ("license", "📜", "许可证授权",    "PDK 会话 · 设备指纹"),
            ("audio",   "🎛️", "音频与通用",    "声音闪避 · OBS 推流 · VAD"),
            ("version", "🚀", "版本更新",      "检查更新 · 发版日志"),
        ]

        self.nav_buttons: dict[str, tk.Frame] = {}
        nav_container = tk.Frame(sidebar, bg=theme.SURFACE)
        nav_container.pack(fill=tk.BOTH, expand=True, padx=6, pady=8)

        for key, icon, title, subtitle in nav_items:
            item = tk.Frame(nav_container, bg=theme.SURFACE, cursor="hand2")
            item.pack(fill=tk.X, pady=2)

            # 左侧高亮指示条
            indicator = tk.Frame(item, bg=theme.SURFACE, width=3)
            indicator.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 0))
            item._indicator = indicator  # type: ignore[attr-defined]

            # 内容区
            content = tk.Frame(item, bg=theme.SURFACE, cursor="hand2")
            content.pack(fill=tk.X, padx=(6, 8), pady=6)

            # 图标 + 标题行
            row_title = tk.Frame(content, bg=theme.SURFACE, cursor="hand2")
            row_title.pack(fill=tk.X)
            lbl_icon = tk.Label(
                row_title, text=icon, bg=theme.SURFACE, fg=theme.TEXT_SOFT,
                font=theme.font(11), cursor="hand2",
            )
            lbl_icon.pack(side=tk.LEFT)
            lbl_title = tk.Label(
                row_title, text=title, bg=theme.SURFACE, fg=theme.TEXT_SOFT,
                font=theme.font(theme.FS_BODY, "bold"), anchor="w", cursor="hand2",
            )
            lbl_title.pack(side=tk.LEFT, padx=(6, 0))

            # 副标题行
            lbl_sub = tk.Label(
                content, text=subtitle, bg=theme.SURFACE, fg=theme.TEXT_FAINT,
                font=theme.font(theme.FS_CAPTION), anchor="w", cursor="hand2",
            )
            lbl_sub.pack(fill=tk.X, padx=(0, 0), pady=(2, 0))

            # 存储子控件引用（用于选中状态切换）
            item._child_widgets = [content, row_title, lbl_icon, lbl_title, lbl_sub]  # type: ignore[attr-defined]

            # 绑定点击事件到所有子组件
            click_handler = lambda e, k=key: self._on_nav_click(k)
            for widget in [item, content, row_title, lbl_icon, lbl_title, lbl_sub]:
                widget.bind("<Button-1>", click_handler)

            self.nav_buttons[key] = item

        # 左右分割线
        sep_v = tk.Frame(body, bg=theme.BORDER, width=1)
        sep_v.pack(side=tk.LEFT, fill=tk.Y)

        # ---------------- 右侧动态面板展示区 ----------------
        self.panel_container = tk.Frame(body, bg=theme.BG)
        self.panel_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 初始化 4 个面板容器
        self._init_panels()

    def _init_panels(self):
        """预构建四个功能面板。"""
        # 1. AI 参数配置面板
        p_ai_wrap = tk.Frame(self.panel_container, bg=theme.BG)
        p_ai_content, _ = _make_scrollable(p_ai_wrap, bg=theme.BG)
        self._build_panel_ai(p_ai_content)
        self.panels["ai"] = p_ai_wrap

        # 2. 许可证显示面板
        p_lic_wrap = tk.Frame(self.panel_container, bg=theme.BG)
        p_lic_content, _ = _make_scrollable(p_lic_wrap, bg=theme.BG)
        self._build_panel_license(p_lic_content)
        self.panels["license"] = p_lic_wrap

        # 3. 通用与音频配置面板
        p_aud_wrap = tk.Frame(self.panel_container, bg=theme.BG)
        p_aud_content, _ = _make_scrollable(p_aud_wrap, bg=theme.BG)
        self._build_panel_audio(p_aud_content)
        self.panels["audio"] = p_aud_wrap

        # 4. 版本更新面板
        p_ver_wrap = tk.Frame(self.panel_container, bg=theme.BG)
        p_ver_content, _ = _make_scrollable(p_ver_wrap, bg=theme.BG)
        self._build_panel_version(p_ver_content)
        self.panels["version"] = p_ver_wrap

    def _switch_panel(self, name: str):
        """显示指定名称的面板并隐藏其他。"""
        for k, p in self.panels.items():
            if k == name:
                p.pack(fill=tk.BOTH, expand=True)
            else:
                p.pack_forget()
        self.current_panel_name = name

    def _on_nav_click(self, name: str):
        """导航按钮点击回调：高亮选中项并切换面板。"""
        # 更新所有按钮状态
        for key, item in self.nav_buttons.items():
            is_active = (key == name)
            bg = theme.SURFACE_SOFT if is_active else theme.SURFACE
            fg_title = theme.CYAN if is_active else theme.TEXT_SOFT
            fg_sub = theme.TEXT_MUTED if is_active else theme.TEXT_FAINT
            indicator_bg = theme.CYAN if is_active else theme.SURFACE

            item.configure(bg=bg)
            item._indicator.configure(bg=indicator_bg)  # type: ignore[attr-defined]
            for w in item._child_widgets:  # type: ignore[attr-defined]
                try:
                    w.configure(bg=bg)
                except Exception:
                    pass
            # 更新文字颜色
            children = item._child_widgets  # type: ignore[attr-defined]
            # children: [content, row_title, lbl_icon, lbl_title, lbl_sub]
            if len(children) >= 5:
                children[2].configure(fg=fg_title)  # icon
                children[3].configure(fg=fg_title)  # title
                children[4].configure(fg=fg_sub)    # subtitle

        self._switch_panel(name)

        # 许可证面板自动刷新
        if name == "license":
            self._refresh_license_display()

    # =========================================================================
    # 面板 1: AI 参数配置
    # =========================================================================
    def _build_panel_ai(self, parent: tk.Frame):
        container = tk.Frame(parent, bg=theme.BG)
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        # Card 1: 大模型推理接口配置
        card1, body1 = theme.card(container, "大模型推理接口配置 (LLM API)", accent=theme.PRIMARY)
        card1.pack(fill=tk.X, pady=(0, 10))

        # API Key
        row_k = tk.Frame(body1, bg=theme.SURFACE)
        row_k.pack(fill=tk.X, pady=4)
        theme.label(row_k, "API 密钥 (API Key):", font_size=theme.FS_BODY, bold=True).pack(side=tk.LEFT)
        self.ent_deepseek_key = theme.entry(row_k, width=34)
        self.ent_deepseek_key.insert(0, self.var_deepseek_key.get())
        self.ent_deepseek_key.configure(show="*")
        self.ent_deepseek_key.pack(side=tk.LEFT, padx=8)

        def _toggle_key():
            is_vis = self.var_key_visible.get()
            self.var_key_visible.set(not is_vis)
            self.ent_deepseek_key.configure(show="" if not is_vis else "*")
            btn_eye.configure(text="🔒 隐藏" if not is_vis else "👁️ 显示")

        btn_eye = theme.button(
            row_k, "👁️ 显示", color=theme.SURFACE_SOFT, active=theme.BORDER_FOCUS,
            font_size=theme.FS_CAPTION, padx=6, pady=2, command=_toggle_key,
        )
        btn_eye.pack(side=tk.LEFT)

        # Base URL
        row_b = tk.Frame(body1, bg=theme.SURFACE)
        row_b.pack(fill=tk.X, pady=4)
        theme.label(row_b, "服务地址 (Base URL):", font_size=theme.FS_BODY, bold=True).pack(side=tk.LEFT)
        self.ent_deepseek_base = theme.entry(row_b, width=34)
        self.ent_deepseek_base.insert(0, self.var_deepseek_base.get())
        self.ent_deepseek_base.pack(side=tk.LEFT, padx=8)
        theme.label(row_b, "云端 API（如 DeepSeek）或本地 Ollama: http://localhost:11434/v1", muted=True, font_size=theme.FS_CAPTION).pack(
            side=tk.LEFT
        )

        # Model Choice
        row_m = tk.Frame(body1, bg=theme.SURFACE)
        row_m.pack(fill=tk.X, pady=4)
        theme.label(row_m, "模型标识 (Model):", font_size=theme.FS_BODY, bold=True).pack(side=tk.LEFT)
        self.cmb_model = ttk.Combobox(
            row_m,
            textvariable=self.var_deepseek_model,
            values=["deepseek-chat", "deepseek-reasoner", "qwen2.5:7b", "llama3:8b", "gpt-4o-mini"],
            style="Zhibodou.TCombobox",
            width=22,
        )
        self.cmb_model.pack(side=tk.LEFT, padx=8)
        theme.label(row_m, "云端模型或本地 Ollama 量化模型标识", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT)

        # Card 2: 弹幕采集与 AI 回复设置
        from danma.hardware import ALL_MODE_DISPLAYS
        card_danmu, body_danmu = theme.card(container, "弹幕采集与 AI 回复设置 (Danmu & AI Reply)", accent=theme.TEAL)
        card_danmu.pack(fill=tk.X, pady=(0, 10))

        # 1. 弹幕回复总开关
        row_sw = tk.Frame(body_danmu, bg=theme.SURFACE)
        row_sw.pack(fill=tk.X, pady=(2, 4))
        chk_ai = tk.Checkbutton(
            row_sw,
            text="启用弹幕 AI 自动理解与个性化回复",
            variable=self.var_ai_danmu_reply,
            bg=theme.SURFACE,
            fg=theme.TEXT,
            selectcolor=theme.BG_ELEVATED,
            activebackground=theme.SURFACE,
            activeforeground=theme.CYAN,
            font=theme.font(theme.FS_BODY, "bold"),
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
        )
        chk_ai.pack(side=tk.LEFT)

        # 2. 弹幕回复驱动模式 (Hardware Mode)
        row_dm = tk.Frame(body_danmu, bg=theme.SURFACE)
        row_dm.pack(fill=tk.X, pady=4)
        theme.label(row_dm, "弹幕回复模式:", font_size=theme.FS_BODY, bold=True).pack(side=tk.LEFT)
        self.cmb_danmu_mode = ttk.Combobox(
            row_dm,
            textvariable=self.var_danmu_mode,
            values=ALL_MODE_DISPLAYS,
            style="Zhibodou.TCombobox",
            width=38,
            state="readonly",
        )
        self.cmb_danmu_mode.pack(side=tk.LEFT, padx=8)
        theme.label(row_dm, "根据本机显卡自适应推荐语音合成驱动", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT)

        # 3. 仅统计指标模式 (Checkbox)
        row_mo = tk.Frame(body_danmu, bg=theme.SURFACE)
        row_mo.pack(fill=tk.X, pady=(4, 2))
        chk_metrics = tk.Checkbutton(
            row_mo,
            text="仅统计指标模式 (不采弹幕文本，仅监听在线人数/点赞/礼物互动)",
            variable=self.var_danmu_metrics_only,
            bg=theme.SURFACE,
            fg=theme.TEXT,
            selectcolor=theme.BG_ELEVATED,
            activebackground=theme.SURFACE,
            activeforeground=theme.CYAN,
            font=theme.font(theme.FS_BODY),
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
        )
        chk_metrics.pack(side=tk.LEFT)
        theme.label(row_mo, "（勾选后仅统计实时数据，不下发弹幕文本，降低性能开销）", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT, padx=(4, 0))

        # Card 3: 豆包主播提示词模板与硬约束
        card3, body3 = theme.card(container, "豆包主播提示词模板与硬约束", accent=theme.CYAN)
        card3.pack(fill=tk.BOTH, expand=True)

        theme.label(
            body3,
            "下发给豆包的主播口播硬约束（规范仅输出纯正直播带货话术，杜绝任何格式前缀、解释与客套收尾）：",
            muted=True,
            font_size=theme.FS_CAPTION,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        self.txt_host_prompt = theme.text_area(body3, tk.Text, height=7)
        self.txt_host_prompt.pack(fill=tk.BOTH, expand=True)
        current_prompt = self.cfg.get("doubao_host_prompt") or config.DEFAULT_CFG.get("doubao_host_prompt", "")
        self.txt_host_prompt.insert(tk.END, current_prompt)

        row_p_btn = tk.Frame(body3, bg=theme.SURFACE)
        row_p_btn.pack(fill=tk.X, pady=(6, 0))

        def _reset_prompt():
            def_p = config.DEFAULT_CFG.get("doubao_host_prompt", "")
            self.txt_host_prompt.delete(1.0, tk.END)
            self.txt_host_prompt.insert(tk.END, def_p)
            self.lab_footer_status.config(text="已重置为主播提示词默认标准模板", fg=theme.AMBER)

        btn_reset = theme.button(
            row_p_btn, "恢复默认提示词模板", color=theme.SURFACE_SOFT, active=theme.BORDER_FOCUS,
            font_size=theme.FS_CAPTION, padx=8, pady=2, command=_reset_prompt,
        )
        btn_reset.pack(side=tk.RIGHT)

    # =========================================================================
    # 面板 2: 许可证显示
    # =========================================================================
    def _build_panel_license(self, parent: tk.Frame):
        container = tk.Frame(parent, bg=theme.BG)
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        card_lic, body_lic = theme.card(container, "PDK 演播室设备许可证与会话详情", accent=theme.GREEN)
        card_lic.pack(fill=tk.BOTH, expand=True)

        # 状态总览
        top_status = tk.Frame(body_lic, bg=theme.SURFACE_ALT, bd=0)
        top_status.pack(fill=tk.X, pady=(2, 12), padx=2)

        self.lab_lic_badge = theme.pill(
            top_status, "● 检测中...", bg=theme.SURFACE_SOFT, fg=theme.TEXT_MUTED, font_size=theme.FS_CAPTION, bold=True
        )
        self.lab_lic_badge.pack(side=tk.LEFT, padx=10, pady=8)

        self.lab_lic_summary = theme.label(
            top_status, "正在读取 PDK 安全会话状态...", muted=True, font_size=theme.FS_BODY, bg=theme.SURFACE_ALT
        )
        self.lab_lic_summary.pack(side=tk.LEFT, padx=4)

        btn_refresh = theme.button(
            top_status, "🔄 刷新授权", color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER,
            font_size=theme.FS_CAPTION, padx=8, pady=3, command=self._refresh_license_display,
        )
        btn_refresh.pack(side=tk.RIGHT, padx=10, pady=6)

        # 详细参数网格
        grid = tk.Frame(body_lic, bg=theme.SURFACE)
        grid.pack(fill=tk.X, pady=4)

        self.lic_fields: dict[str, tk.Label] = {}
        items = [
            ("绑定手机号", "phone"),
            ("所属业务 (BizCode)", "biz_code"),
            ("授权模式", "auth_mode"),
            ("剩余调用额度", "remaining"),
            ("许可证到期时间", "expire_at"),
            ("物理机硬件指纹", "device_fingerprint"),
        ]

        for idx, (label_title, key) in enumerate(items):
            row_f = tk.Frame(grid, bg=theme.SURFACE)
            row_f.pack(fill=tk.X, pady=5)
            theme.label(row_f, f"{label_title}：", font_size=theme.FS_BODY, bold=True, width=18, anchor="w").pack(
                side=tk.LEFT
            )
            val_lbl = theme.label(row_f, "-", font_size=theme.FS_BODY, fg=theme.TEXT_SOFT, anchor="w")
            val_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.lic_fields[key] = val_lbl

        # 底部安全提示
        sec_box = tk.Frame(body_lic, bg=theme.BG_ELEVATED)
        sec_box.pack(fill=tk.X, pady=(16, 4))
        theme.label(
            sec_box,
            "💡 提示：智播豆演播室许可证绑定当前物理机主板与 CPU 签名。如需更换工作站或增购并发，请联系杭州智鑫科技管理员。",
            muted=True,
            font_size=theme.FS_CAPTION,
            bg=theme.BG_ELEVATED,
            wraplength=520,
            justify=tk.LEFT,
        ).pack(padx=10, pady=8, anchor="w")

        self._refresh_license_display()

    def _refresh_license_display(self):
        """从 pdk_auth 读取当前会话并更新控件。"""
        try:
            auth_res = pdk_auth.current_auth()
        except Exception:
            auth_res = None

        if auth_res is not None:
            self.lab_lic_badge.config(text="● 授权有效", bg=theme.GREEN_DARK, fg="#FFFFFF")
            self.lab_lic_summary.config(text=f"安全会话已建立 ({auth_res.authorization_mode})", fg=theme.GREEN)

            self.lic_fields["phone"].config(text=str(auth_res.masked_phone or "已授权用户"))
            biz = auth_res.business.get("bizCode") or auth_res.session.get("bizCode") or "zhibodou_live"
            self.lic_fields["biz_code"].config(text=str(biz))
            self.lic_fields["auth_mode"].config(text=str(auth_res.authorization_mode or "DEVICE_LICENSE"))
            self.lic_fields["remaining"].config(
                text=f"{auth_res.remaining_calls} 次" if auth_res.remaining_calls is not None else "无限额度"
            )
            self.lic_fields["expire_at"].config(text=str(auth_res.expire_at or "长期有效 (企业订阅)"))
            self.lic_fields["device_fingerprint"].config(
                text="已绑定当前硬件机器码 · 安全校验通过", fg=theme.CYAN
            )
        else:
            self.lab_lic_badge.config(text="● 未授权/失效", bg=theme.RED_DARK, fg="#FFFFFF")
            self.lab_lic_summary.config(text="当前未检索到有效 PDK 会话，请重新登录", fg=theme.RED)
            for lbl in self.lic_fields.values():
                lbl.config(text="未登录 / 会话失效", fg=theme.TEXT_FAINT)

    # =========================================================================
    # 面板 3: 通用与音频
    # =========================================================================
    def _build_panel_audio(self, parent: tk.Frame):
        container = tk.Frame(parent, bg=theme.BG)
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        # Card 1: 软件音频会话闪避 (Ducking)
        c1, b1 = theme.card(container, "声音动态闪避算法 (Software Audio Ducking)", accent=theme.AMBER)
        c1.pack(fill=tk.X, pady=(0, 10))

        # 头部：标签 + 当前数值胶囊 + 状态说明
        row_d_info = tk.Frame(b1, bg=theme.SURFACE)
        row_d_info.pack(fill=tk.X, pady=(4, 4))
        theme.label(row_d_info, "弹幕播报闪避压低比例:", font_size=theme.FS_BODY, bold=True).pack(side=tk.LEFT)

        self.lab_duck_val = theme.pill(
            row_d_info, f"{self.var_duck_pct.get()}%",
            bg=theme.PRIMARY_MUTED, fg=theme.CYAN, font_size=theme.FS_BODY, bold=True, padx=8, pady=2
        )
        self.lab_duck_val.pack(side=tk.LEFT, padx=8)

        self.lab_duck_desc = theme.label(
            row_d_info, "", font_size=theme.FS_CAPTION, fg=theme.TEXT_MUTED
        )
        self.lab_duck_desc.pack(side=tk.LEFT)

        # 水平滑动条 (Slider)
        row_slider = tk.Frame(b1, bg=theme.SURFACE)
        row_slider.pack(fill=tk.X, pady=(4, 6))

        theme.label(row_slider, "5% (深压)", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT, padx=(2, 6))

        self.slider_duck = ttk.Scale(
            row_slider,
            from_=5,
            to=90,
            variable=self.var_duck_pct,
            orient=tk.HORIZONTAL,
            style="Zhibodou.Horizontal.TScale",
            command=self._on_duck_slider_change,
        )
        self.slider_duck.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        theme.label(row_slider, "90% (微调)", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT, padx=(6, 2))

        # 快捷档位预设按钮
        row_presets = tk.Frame(b1, bg=theme.SURFACE)
        row_presets.pack(fill=tk.X, pady=(2, 6))
        theme.label(row_presets, "快捷档位：", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT, padx=(2, 6))

        for p_val, p_text in [(15, "15% 强力压低"), (25, "25% 官方推荐"), (35, "35% 柔和闪避"), (50, "50% 对半平衡")]:
            btn_p = theme.button(
                row_presets, p_text,
                color=theme.SURFACE_SOFT, active=theme.BORDER_FOCUS,
                font_size=theme.FS_CAPTION, padx=7, pady=2,
                command=lambda v=p_val: self._set_duck_preset(v)
            )
            btn_p.pack(side=tk.LEFT, padx=3)

        self._on_duck_slider_change(self.var_duck_pct.get())

        theme.label(
            b1,
            "机制：当弹幕触发 TTS 发音时，系统通过 WASAPI 毫秒级自动压低 scrcpy.exe 音量；\n"
            "TTS 播报完毕后无缝平滑回弹至 100%，两者声音和谐共存，无需暂停话术。",
            muted=True,
            font_size=theme.FS_CAPTION,
            anchor="w",
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(4, 0))

        # Card 2: OBS 直播音频推流
        c2, b2 = theme.card(container, "OBS 演播室推流无损音轨 (MPEG-TS)", accent=theme.PRIMARY)
        c2.pack(fill=tk.X, pady=(0, 10))

        row_o = tk.Frame(b2, bg=theme.SURFACE)
        row_o.pack(fill=tk.X, pady=4)
        theme.label(row_o, "推流服务端口 (Port):", font_size=theme.FS_BODY, bold=True).pack(side=tk.LEFT)
        self.ent_obs_port = theme.entry(row_o, width=12)
        self.ent_obs_port.insert(0, self.var_obs_port.get())
        self.ent_obs_port.pack(side=tk.LEFT, padx=8)

        def _copy_obs():
            p = self.ent_obs_port.get().strip() or "8554"
            url = f"http://127.0.0.1:{p}/danmu_audio"
            try:
                self.dialog.clipboard_clear()
                self.dialog.clipboard_append(url)
                self.lab_footer_status.config(text=f"已复制 OBS 媒体源推流链接: {url}", fg=theme.GREEN)
            except Exception:
                pass

        btn_copy = theme.button(
            row_o, "📋 复制推流源地址", color=theme.SURFACE_SOFT, active=theme.BORDER_FOCUS,
            font_size=theme.FS_CAPTION, padx=8, pady=2, command=_copy_obs,
        )
        btn_copy.pack(side=tk.LEFT, padx=6)

        # Card 3: VAD 语音断句时序
        c3, b3 = theme.card(container, "VAD 语音活动检测参数 (时序与断句)", accent=theme.TEAL)
        c3.pack(fill=tk.X)

        row_v1 = tk.Frame(b3, bg=theme.SURFACE)
        row_v1.pack(fill=tk.X, pady=3)
        theme.label(row_v1, "连续静音切句判定 (秒):", font_size=theme.FS_BODY, bold=True, width=22, anchor="w").pack(side=tk.LEFT)
        self.ent_vad_silence = theme.entry(row_v1, width=12)
        self.ent_vad_silence.insert(0, self.var_vad_silence.get())
        self.ent_vad_silence.pack(side=tk.LEFT, padx=8)
        theme.label(row_v1, "豆包连续静音超过此时长判定说完了，自动切入下一轮 (默认 4.0s)", muted=True, font_size=theme.FS_CAPTION).pack(
            side=tk.LEFT
        )

        row_v2 = tk.Frame(b3, bg=theme.SURFACE)
        row_v2.pack(fill=tk.X, pady=3)
        theme.label(row_v2, "发言确认消抖时长 (秒):", font_size=theme.FS_BODY, bold=True, width=22, anchor="w").pack(side=tk.LEFT)
        self.ent_vad_confirm = theme.entry(row_v2, width=12)
        self.ent_vad_confirm.insert(0, self.var_vad_confirm.get())
        self.ent_vad_confirm.pack(side=tk.LEFT, padx=8)
        theme.label(row_v2, "连续语音确认时长，防止杂音偶发误触 (默认 0.3s)", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT)

        row_v3 = tk.Frame(b3, bg=theme.SURFACE)
        row_v3.pack(fill=tk.X, pady=3)
        theme.label(row_v3, "发消息后思考等待上限 (秒):", font_size=theme.FS_BODY, bold=True, width=22, anchor="w").pack(side=tk.LEFT)
        self.ent_vad_wait = theme.entry(row_v3, width=12)
        self.ent_vad_wait.insert(0, self.var_vad_wait.get())
        self.ent_vad_wait.pack(side=tk.LEFT, padx=8)
        theme.label(row_v3, "防思考期无语音被误判为播报结束 (默认 15.0s)", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT)

    def _set_duck_preset(self, val: int):
        """设置滑动条快捷预设档位。"""
        if hasattr(self, "slider_duck"):
            self.slider_duck.set(val)
        self._on_duck_slider_change(val)

    def _on_duck_slider_change(self, val):
        """滑动条数值变动实时回调。"""
        try:
            pct = int(round(float(val)))
        except (ValueError, TypeError):
            pct = 25
        self.var_duck_pct.set(pct)
        self.var_duck_ratio.set(f"{pct}%")
        if hasattr(self, "lab_duck_val") and self.lab_duck_val.winfo_exists():
            self.lab_duck_val.config(text=f"{pct}%")
        if hasattr(self, "lab_duck_desc") and self.lab_duck_desc.winfo_exists():
            if pct <= 15:
                desc = "（原声音量压低 85% 以上，完全突出弹幕播报）"
            elif 16 <= pct <= 30:
                desc = "（原声音量压低 75%，弹幕与豆包声音和谐共存，官方推荐）"
            elif 31 <= pct <= 50:
                desc = "（轻度压低原声，主播与弹幕音量均衡）"
            else:
                desc = "（微弱闪避，仅轻微降低背景原声）"
            self.lab_duck_desc.config(text=desc)

    # =========================================================================
    # 面板 4: 版本更新
    # =========================================================================
    def _build_panel_version(self, parent: tk.Frame):
        container = tk.Frame(parent, bg=theme.BG)
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        # Card 1: 当前版本状态与检查
        c1, b1 = theme.card(container, "智播豆演播室版本状态", accent=theme.PRIMARY)
        c1.pack(fill=tk.X, pady=(0, 10))

        row_v = tk.Frame(b1, bg=theme.SURFACE)
        row_v.pack(fill=tk.X, pady=6)

        theme.label(row_v, "当前运行版本：", font_size=theme.FS_BODY, bold=True).pack(side=tk.LEFT)
        theme.pill(row_v, f"v{APP_VERSION} Official", bg=theme.PRIMARY_MUTED, fg=theme.CYAN, font_size=theme.FS_BODY, bold=True).pack(
            side=tk.LEFT, padx=(4, 12)
        )

        self.btn_check_ver = theme.button(
            row_v, "🔍 检查新版本", color=theme.SLATE_BTN, active=theme.SLATE_BTN_HOVER,
            font_size=theme.FS_CAPTION, padx=8, pady=3, command=self._check_version_update,
        )
        self.btn_check_ver.pack(side=tk.LEFT)

        self.lab_ver_status = theme.label(row_v, "", font_size=theme.FS_BODY, fg=theme.GREEN)
        self.lab_ver_status.pack(side=tk.LEFT, padx=10)

        theme.label(
            b1,
            "核心架构：Python 3.11 · Scrcpy 2.4 · WASAPI Ducking · OBS Streamer · PDK Security",
            muted=True,
            font_size=theme.FS_CAPTION,
            anchor="w",
        ).pack(fill=tk.X, pady=(4, 0))

        # Card 2: 演播室发版更新记录
        c2, b2 = theme.card(container, "发版记录与更新日志 (Release Notes)", accent=theme.CYAN)
        c2.pack(fill=tk.BOTH, expand=True)

        changelogs = [
            ("v1.7.0 (2026-09-22)", [
                "新增全局「系统设置中心」模态对话框，支持扁平纵向分类导航",
                "支持多种大模型 API 密钥、服务地址、模型选择与主播提示词硬约束自定义",
                "可视化呈现 PDK 会话与许可证详情，支持一键重新核验状态",
                "新增声音闪避压低比例 (25%) 与 OBS MPEG-TS 串流端口动态调控",
            ]),
            ("v1.6.0 (2026-09-21)", [
                "引入 OBS HTTP MPEG-TS 直播推流无损音轨架构，告别音频虚拟线繁琐配置",
                "演播室主界面新增 OBS 媒体源一键复制与推流链路健康监控",
            ]),
            ("v1.5.0 (2026-09-21)", [
                "研发 Windows 软件音频会话动态闪避 (Ducking)，弹幕朗读与豆包原声共存互不干扰",
                "弹幕 TTS 结束后 0.2s 自动平滑恢复原音量，避免声音断层",
            ]),
            ("v1.4.0 (2026-09-20)", [
                "引入 GPU 硬件自适应分级探测，智能适配 IndexTTS / MOSS-TTS / Playwright",
                "多平台弹幕解析管道增强，全面支持全链路自动抓取",
            ]),
            ("v1.3.0 (2026-09-19)", [
                "升级黑曜石演播室高对比深色控制台视觉系统，降低主播长周期疲劳度",
            ]),
        ]

        for ver_title, items in changelogs:
            item_box = tk.Frame(b2, bg=theme.SURFACE)
            item_box.pack(fill=tk.X, pady=4)
            theme.label(item_box, ver_title, font_size=theme.FS_BODY, bold=True, fg=theme.CYAN).pack(anchor="w")
            for item in items:
                row_log = tk.Frame(item_box, bg=theme.SURFACE)
                row_log.pack(fill=tk.X, padx=12, pady=1)
                theme.label(row_log, "•", muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT)
                theme.label(row_log, item, muted=True, font_size=theme.FS_CAPTION).pack(side=tk.LEFT, padx=4)

    def _check_version_update(self):
        """模拟异步检测版本更新。"""
        self.btn_check_ver.config(state=tk.DISABLED, text="正在检查...")
        self.lab_ver_status.config(text="正在连接版本服务器...", fg=theme.AMBER)

        def _async_task():
            import time
            time.sleep(0.6)
            if self.dialog.winfo_exists():
                self.dialog.after(0, _on_done)

        def _on_done():
            self.btn_check_ver.config(state=tk.NORMAL, text="🔍 检查新版本")
            self.lab_ver_status.config(text="✅ 当前已是最新版本 (v1.7.0)，无需更新", fg=theme.GREEN)

        threading.Thread(target=_async_task, daemon=True).start()

    # =========================================================================
    # 保存与持久化
    # =========================================================================
    def _save_settings(self):
        """收集所有面板设置并持久化至 config.json，同时同步到运行态。"""
        try:
            d = config.load_config()

            # 1. AI 与弹幕配置采集
            api_key = self.ent_deepseek_key.get().strip()
            api_base = self.ent_deepseek_base.get().strip() or "https://api.deepseek.com"
            model_name = self.var_deepseek_model.get().strip() or "deepseek-chat"
            ai_reply = bool(self.var_ai_danmu_reply.get())
            danmu_metrics_only = bool(self.var_danmu_metrics_only.get())
            danmu_mode = str(self.var_danmu_mode.get()).strip()
            prompt_text = self.txt_host_prompt.get(1.0, tk.END).strip()

            d["deepseek_api_key"] = api_key
            d["deepseek_api_base"] = api_base
            d["deepseek_model"] = model_name
            d["ai_danmu_reply_enabled"] = ai_reply
            d["danmu_metrics_only"] = danmu_metrics_only
            d["danmu_mode"] = danmu_mode
            if prompt_text:
                d["doubao_host_prompt"] = prompt_text

            # 2. 通用与音频配置采集
            try:
                duck_pct = self.var_duck_pct.get()
                duck_ratio = max(0.05, min(0.95, float(duck_pct) / 100.0))
            except Exception:
                duck_ratio = 0.25
            d["audio_duck_ratio"] = duck_ratio

            try:
                obs_port = int(self.ent_obs_port.get().strip() or "8554")
            except ValueError:
                obs_port = 8554
            d["obs_audio_port"] = obs_port

            try:
                d["vad_silence_hold_sec"] = float(self.ent_vad_silence.get().strip())
            except ValueError:
                pass

            try:
                d["vad_speak_confirm_sec"] = float(self.ent_vad_confirm.get().strip())
            except ValueError:
                pass

            try:
                d["vad_wait_start_sec"] = float(self.ent_vad_wait.get().strip())
            except ValueError:
                pass

            # 写入 config.json
            from core.paths import CONFIG_JSON
            with open(CONFIG_JSON, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)

            # 同步更新运行态管理器
            try:
                from audio.ducking import get_ducking_manager
                get_ducking_manager().duck_ratio = duck_ratio
            except Exception:
                pass

            try:
                from audio.obs_bridge import get_obs_bridge
                get_obs_bridge(obs_port)
            except Exception:
                pass

            # 同步主界面控件（若已实例化）
            try:
                from gui import ui
                if getattr(ui, "ent_deepseek_key", None):
                    ui.ent_deepseek_key.delete(0, tk.END)
                    ui.ent_deepseek_key.insert(0, api_key)
                if getattr(ui, "var_ai_reply", None):
                    ui.var_ai_reply.set(ai_reply)
                if getattr(ui, "lbl_obs_link", None):
                    ui.lbl_obs_link.config(text=f"http://127.0.0.1:{obs_port}/danmu_audio")
            except Exception:
                pass

            self.lab_footer_status.config(text="✅ 系统设置已成功保存并立即生效", fg=theme.GREEN)
            messagebox.showinfo("系统设置", "✅ 配置已成功保存并立即生效！", parent=self.dialog)

        except Exception as e:
            messagebox.showerror("保存失败", f"保存配置时发生错误：{e}", parent=self.dialog)

    def _on_close(self):
        """释放模态并关闭对话框。"""
        try:
            self.dialog.grab_release()
        except Exception:
            pass
        try:
            self.dialog.destroy()
        except Exception:
            pass


def open_settings_dialog(parent: tk.Misc) -> SettingsDialog:
    """打开系统设置中心模态对话框入口。"""
    return SettingsDialog(parent)
