# -*- coding: utf-8 -*-
"""合成 protobuf 验证：douyin_pb2 能把 WebcastRoomUserSeqMessage/Like/Gift 解成三个指标消息。"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "danma"))

from live_plate.douyin import douyin_message_pb2
from live_plate.douyin.dy import douyin_pb2 as decode

def make_response(method, payload_msg):
    """构造一层 Response{messages:[Message{method, payload}]}"""
    r = douyin_message_pb2.Response()
    m = r.messages.add()
    m.method = method
    m.payload = payload_msg.SerializeToString()
    return r.SerializeToString()

# 1) 在线人数
room = douyin_message_pb2.RoomUserSeqMessage()
room.total = 1357
out = decode(make_response("WebcastRoomUserSeqMessage", room))
assert len(out) == 1 and out[0]["type"] == "RoomMessage" and out[0]["count"] == "1357", out
print("✅ RoomUserSeq(total=1357) ->", out[0])

# 2) total=0（proto3 默认值省略场景，验证 .get 兜底不炸）
# 注：douyin_pb2 有 len<30 守卫，故混入一条 ChatMessage 撑起真实帧大小
r = douyin_message_pb2.Response()
m1 = r.messages.add()
m1.method = "WebcastChatMessage"
chat = douyin_message_pb2.ChatMessage()
chat.user.nickname = "测试用户"
chat.content = "你好直播间"
chat.user.avatarThumb.urlList.append("http://x/a.jpg")
m1.payload = chat.SerializeToString()
m2 = r.messages.add()
m2.method = "WebcastRoomUserSeqMessage"
room0 = douyin_message_pb2.RoomUserSeqMessage()
room0.total = 0
m2.payload = room0.SerializeToString()
out0 = decode(r.SerializeToString())
assert out0 and out0[0]["type"] == "ChatMessage", out0
room_msg = [m for m in out0 if m["type"] == "RoomMessage"]
assert room_msg and room_msg[0]["count"] == "0", out0
print("✅ RoomUserSeq(total=0)  ->", room_msg[0], "（total 缺省不炸）")

# 3) 点赞
like = douyin_message_pb2.LikeMessage()
like.count = 5
like.user.nickname = "测试用户"
like.user.avatarThumb.urlList.append("http://x/a.jpg")
out = decode(make_response("WebcastLikeMessage", like))
assert out and out[0]["type"] == "LikeMessage", out
print("✅ Like(count=5)         ->", out[0])

# 4) 点赞 count=0（验证 .get('count',1) 兜底）
like0 = douyin_message_pb2.LikeMessage()
like0.count = 0
like0.user.nickname = "测试用户"
like0.user.avatarThumb.urlList.append("http://x/a.jpg")
out0 = decode(make_response("WebcastLikeMessage", like0))
assert out0 and out0[0]["type"] == "LikeMessage" and out0[0]["count"] == "1", out0
print("✅ Like(count=0 缺省)    ->", out0[0], "（count 缺省兜底为 1）")

# 5) 礼物（走 type=4 分支）
gift = douyin_message_pb2.GiftMessage()
gift.giftId = 273
gift.repeatCount = 3
gift.gift.type = 4
gift.gift.id = 273
gift.common.describe = "送出了 3 个 小心心"
gift.user.nickname = "测试用户"
gift.user.avatarThumb.urlList.append("http://x/img.jpg")
out = decode(make_response("WebcastGiftMessage", gift))
assert out and out[0]["type"] == "GiftMessage", out
print("✅ Gift(type=4, x3)      ->", out[0])

print("\nDECODER TEST: ALL PASS —— 解码器到三个指标(Room/Like/Gift)的路径全部打通")
