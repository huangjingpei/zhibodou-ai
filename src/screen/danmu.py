# ====================== 弹幕解析 + WebSocket 接收循环 ======================
# 解析弹幕/礼物/点赞/在线人数，并更新到 GUI；后台维持 WebSocket 长连接。
import re
import time
import tkinter as tk
import websocket
from core import state
from gui import ui
from settings.config import WS_SERVER_URL


def parse_danmu(msg):
    """解析一条弹幕消息，更新实时数据计数与弹幕列表（线程安全经 root.after）。"""
    try:
        m_online = re.search(r"直播间人数[:：]\s*(\d+)", msg)
        if m_online:
            state.online_num = int(m_online.group(1))
            ui.root.after(0, lambda: ui.lab_online.config(text=f"📶 在线：{state.online_num} 人"))

        m_like = re.search(r"总点赞(\d+)", msg)
        if m_like:
            state.like_cnt = int(m_like.group(1))
            ui.root.after(0, lambda: ui.lab_like.config(text=f"👍 点赞：{state.like_cnt}"))

        if "$来了" in msg:
            state.gift_cnt += 1
            ui.root.after(0, lambda: ui.lab_gift.config(text=f"🎁礼物：{state.gift_cnt}"))

        m_comment = re.search(r"\[弹幕消息\]\s*\[(.*?)\]\s*(.+?)[:：](.+)", msg)
        if m_comment:
            uname = m_comment.group(2).strip()
            cnt = m_comment.group(3).strip()
            state.comment_cnt += 1
            tim = time.strftime("%H:%M:%S")
            ui.root.after(0, lambda t=tim, u=uname, c=cnt:
                          ui.txt_danmu.insert(tk.END, f"[{t}] {u}：{c}\n") or ui.txt_danmu.see(tk.END))
    except Exception:
        pass


def ws_danmu_loop():
    """WebSocket 长连接：断线自动重连。仅 live_running 且 system_power 时运行。"""
    while state.live_running and state.system_power:
        try:
            ws = websocket.WebSocketApp(WS_SERVER_URL, on_message=lambda w, m: parse_danmu(m))
            ws.run_forever()
        except Exception:
            time.sleep(2)
