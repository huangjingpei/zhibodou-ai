# -*- coding: utf-8 -*-
"""冒烟测试：metrics_only 模式的 PostMessage 过滤逻辑（不开浏览器）。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "danma"))

from danma.main import DanmuBrowserCollector

MIXED = [
    {"type": "ChatMessage", "name": "用户A", "content": "你好"},
    {"type": "RoomMessage", "count": "123", "content": "当前直播间123人"},
    {"type": "LikeMessage", "name": "用户B", "count": "3"},
    {"type": "GiftMessage", "name": "用户C", "gift_name": "玫瑰", "gift_count": "2"},
    {"type": "MemberMessage", "name": "用户D", "content": "进入直播间"},
    {"type": "SocialMessage", "name": "用户E"},
    {"type": "SystemMessage", "content": "采集页面已启动"},
]

def run(online_only, label):
    got = []
    c = DanmuBrowserCollector(
        platform="douyin", url="https://live.douyin.com/646454278948",
        headless=True, message_callback=lambda items: got.extend(items),
        log_fn=lambda m: None, online_only=online_only,
    )
    c.PostMessage(list(MIXED))
    types = [m.get("type") for m in got]
    print(f"[{label}] online_only={online_only} -> {types}")
    return types

# 1) metrics_only=True：应只保留 Room/Like/Gift/System，丢弃 Chat/Member/Social
t1 = run(True, "过滤模式")
assert sorted(t1) == sorted(["RoomMessage", "LikeMessage", "GiftMessage", "SystemMessage"]), f"过滤失败: {t1}"

# 2) metrics_only=False：全部放行（完整弹幕模式不受影响）
t2 = run(False, "完整模式")
assert len(t2) == 7, f"完整模式误过滤: {t2}"

# 3) 全是弹幕文本时，过滤模式应不下发任何消息
got = []
c = DanmuBrowserCollector(message_callback=lambda items: got.extend(items), online_only=True, log_fn=lambda m: None)
c.PostMessage([{"type": "ChatMessage", "name": "x", "content": "hi"}])
assert got == [], "纯弹幕文本应被完全拦截"

# 4) 模拟真实解码输出形态：list 里混 RoomMessage + ChatMessage
got = []
c = DanmuBrowserCollector(message_callback=lambda items: got.extend(items), online_only=True, log_fn=lambda m: None)
c.PostMessage([{"type": "RoomMessage", "count": "88"}, {"type": "ChatMessage", "name": "x", "content": "hi"}])
assert [m["type"] for m in got] == ["RoomMessage"], "混排过滤失败"

print("SMOKE TEST: ALL PASS")
