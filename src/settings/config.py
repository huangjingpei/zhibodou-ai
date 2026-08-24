# ====================== 全局业务配置 ======================
# 负责：pyautogui 初始化、WebSocket 地址、默认话术配置、配置读写。
import json
import os
import tkinter as tk
import pyautogui
from core.paths import CONFIG_JSON

# pyautogui 安全设置（程序自己控制鼠标，关闭 FAILSAFE 与放慢）
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# 弹幕 WebSocket 服务地址
WS_SERVER_URL = "ws://127.0.0.1:8899"

# 默认配置（界面初次打开 / 配置损坏时的兜底）
DEFAULT_CFG = {
    "product_name": "日用百货",
    "product_desc": "你就是今天的主播 用中国话直接说话术 不要讲解 日用百货 品类多一一展示 下方小黄车直接拍",
    "pre_meet_text": "你就是今天的主播 用中国话直接说话术 不要讲解 日用百货 品类多一一展示 下方小黄车随便拍",
    "r1_min": "0", "r1_max": "30", "cmd1": "留人话术内容填这里",
    "r2_min": "30", "r2_max": "100", "cmd2": "产品讲解话术内容填这里",
    "r3_min": "100", "r3_max": "9999", "cmd3": "逼单促单话术内容填这里",
    "script_interval": 25
}


def load_config():
    """读取 zhibodou_config.json，与默认配置合并。文件缺失/损坏时返回默认配置副本。"""
    if os.path.exists(CONFIG_JSON):
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                d = json.load(f)
            return {**DEFAULT_CFG, **d}
        except Exception:
            pass
    return DEFAULT_CFG.copy()


def save_config():
    """从界面控件采集配置并写入 zhibodou_config.json。
    延迟导入 ui 以读取控件，避免与 ui 模块形成循环依赖。"""
    from gui.ui import (ent_prod_name, ent_prod_desc, txt_pre_meet,
                    ent_r1min, ent_r1max, ent_cmd1,
                    ent_r2min, ent_r2max, ent_cmd2,
                    ent_r3min, ent_r3max, ent_cmd3, ent_interval)
    import tkinter.messagebox as messagebox
    try:
        d = {
            "product_name": ent_prod_name.get().strip(),
            "product_desc": ent_prod_desc.get().strip(),
            "pre_meet_text": txt_pre_meet.get(1.0, tk.END).strip(),
            "r1_min": ent_r1min.get(), "r1_max": ent_r1max.get(), "cmd1": ent_cmd1.get(),
            "r2_min": ent_r2min.get(), "r2_max": ent_r2max.get(), "cmd2": ent_cmd2.get(),
            "r3_min": ent_r3min.get(), "r3_max": ent_r3max.get(), "cmd3": ent_cmd3.get(),
            "script_interval": ent_interval.get()
        }
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("成功", "✅配置保存完成")
    except Exception as e:
        messagebox.showerror("错误", f"保存失败：{e}")
