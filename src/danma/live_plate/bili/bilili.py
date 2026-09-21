import json
import struct
import zlib
import brotli
from live_plate.Message import (
    CreatChatMessage,
    CreatMemberMessage,
    CreatLikeMessage,
    CreatGiftMessage,
    CreatSocialMessage,
)


def parse_cmd_message(msg):
    """
    解析 Bilibili 单个业务 JSON 字典，返回标准消息对象列表
    """
    if not isinstance(msg, dict):
        return []

    cmd = str(msg.get("cmd", ""))
    # 处理带后缀或前缀的命令，例如 DANMU_MSG:4:0:2:2:2:0
    if cmd.startswith("DANMU_MSG"):
        try:
            info = msg.get("info", [])
            if isinstance(info, list) and len(info) > 1:
                content = str(info[1])
                user_info = info[2] if len(info) > 2 and isinstance(info[2], list) else []
                name = str(user_info[1]) if len(user_info) > 1 else "B站用户"
                avatar = ""
                try:
                    if len(info) > 0 and isinstance(info[0], list) and len(info[0]) > 15:
                        avatar = str(info[0][15].get("user", {}).get("base", {}).get("face", ""))
                except Exception:
                    pass
                return [CreatChatMessage(name=name, head_image=avatar, content=content)]
            else:
                data = msg.get("data", {})
                name = str(data.get("uname") or data.get("name") or "B站用户")
                content = str(data.get("msg") or data.get("content") or "")
                if content:
                    return [CreatChatMessage(name=name, head_image=str(data.get("uface", "")), content=content)]
        except Exception:
            return []

    elif cmd == "INTERACT_WORD":
        try:
            data = msg.get("data", {})
            name = str(data.get("uname", "B站老铁"))
            msg_type = data.get("msg_type", 1)
            # 1: 进场, 2: 关注, 3: 分享
            if msg_type == 2:
                return [CreatSocialMessage(name=name, head_image="")]
            return [CreatMemberMessage(name=name, head_image="")]
        except Exception:
            return []

    elif cmd == "LIKE_INFO_V3_CLICK":
        # 用户点击点赞
        try:
            data = msg.get("data", {})
            name = str(data.get("uname", "热心观众"))
            count = data.get("click_count", 1) or 1
            return [CreatLikeMessage(name=name, head_image="", count=count)]
        except Exception:
            return []

    elif cmd == "LIKE_INFO_V3_UPDATE":
        # 房间累计点赞总数更新广播（非单人点赞，忽略以避免刷屏）
        return []

    elif cmd == "SEND_GIFT":
        try:
            data = msg.get("data", {})
            name = str(data.get("uname", "送礼老铁"))
            gift_name = str(data.get("giftName", "礼物"))
            num = int(data.get("num", 1) or 1)
            face = str(data.get("face", ""))
            return [CreatGiftMessage(name=name, head_image=face, gift_name=gift_name, gift_count=num)]
        except Exception:
            return []

    elif cmd == "SUPER_CHAT_MESSAGE":
        try:
            data = msg.get("data", {})
            user_info = data.get("user_info", {})
            name = str(user_info.get("uname", "醒目留言用户"))
            price = data.get("price", 0)
            message = str(data.get("message", ""))
            face = str(user_info.get("face", ""))
            return [CreatChatMessage(name=f"醒目留言(¥{price}) {name}", head_image=face, content=message)]
        except Exception:
            return []

    elif cmd == "ENTRY_EFFECT":
        try:
            data = msg.get("data", {})
            copy_writing = str(data.get("copy_writing", ""))
            if copy_writing:
                clean_name = copy_writing.replace("<%", "").replace("%>", "").replace("进入直播间", "").strip()
                return [CreatMemberMessage(name=clean_name or "贵宾用户", head_image="")]
        except Exception:
            return []

    return []


def _extract_packets(data: bytes):
    """
    底层递归解包，支持 Brotli (ver=3)、Zlib (ver=2)、明文 JSON (ver=0/1)
    """
    if not data or not isinstance(data, (bytes, bytearray)):
        return []

    extracted_msgs = []
    offset = 0
    data_len = len(data)

    while offset + 16 <= data_len:
        try:
            packet_len, header_len, proto_ver, op, seq = struct.unpack_from(">IHHII", data, offset)
        except Exception:
            break

        if packet_len < 16 or offset + packet_len > data_len:
            break

        body = data[offset + header_len : offset + packet_len]

        if proto_ver == 3:
            # Brotli 压缩包
            try:
                decompressed = brotli.decompress(body)
                extracted_msgs.extend(_extract_packets(decompressed))
            except Exception:
                pass
        elif proto_ver == 2:
            # Zlib 压缩包
            try:
                decompressed = zlib.decompress(body)
                extracted_msgs.extend(_extract_packets(decompressed))
            except Exception:
                pass
        elif proto_ver in (0, 1):
            if op == 5:
                # 业务通知
                try:
                    text = body.decode("utf-8", errors="ignore")
                    msg_obj = json.loads(text)
                    items = parse_cmd_message(msg_obj)
                    extracted_msgs.extend(items)
                except Exception:
                    pass
            elif op == 3:
                # 心跳/人气值回应
                pass

        offset += packet_len

    return extracted_msgs


def decode_packet(data):
    """
    接收 WebSocket 二进制 frame，返回 dict 包含 listmessage
    """
    if isinstance(data, str):
        return {"body": [], "listmessage": []}

    msgs = _extract_packets(data)
    return {"body": [], "listmessage": msgs}


if __name__ == '__main__':

    data = '0000001a0010000100000008000000017b22636f6465223a307d'
    data = bytes.fromhex(data)
    data = b"\x00\x00\x01}\x00\x10\x00\x03\x00\x00\x00\x05\x00\x00\x00\x00\x1b\xd7\x02\x00,\nl\x1b[v^\xed`\xb0\x1d\xb3\xc2\xa3\x98\xe2\xed\xb3\xe9B~\x16\xba\x16\xa8\xa2d\xa2\xa4\xd9\x04Q\x14*-\x03\x94s*\x7fB\xed\x1b''\x9eA\xc2\x08\xb43\x91\xd3\xc3\xc5\xb20\xd8\xd0\xc2S|\xe8\xf4P\x11\xd5\x97\xa1\xcb\xe9\xbf\xfd\xdb\x83\xe1\x8d\xf9s6\x87\xed!\x98H\xc0ii(\x81\x08x\x0eB:\xf9\x9f\x05`\xa0\xe0\x98\xd2?\x88\xd8\x93\xf0\xf9\x81\xcd\x1f\x8f\x98\xfc+tCP[\x97\x1fP\x7fD\xf3? z#\x80\xa3eI?\x82\xf0\xa5qo\xaf\x06*\x86\xf1\xcfp} -\xd3=fZ\x1a\xb0\xf8\x04\xb83\xf6\x0c\x8b@\xc43>\x95\xcf\xae\x99\x08\xd34\xe4/\x9d\xac\xc9\x08\x17\xc1\xdb\nZ\xeeY\xdc\x1c\xc4\xb8\xe6\xce\xfch\xdc\xdb\xb2\\E\xb8\x81\x96!B\xffu\xf6,\xd7\xa5l#|\xa8\x8a\xa7\xeaK\x07s\xbfc\xd3nKU\x05\x91\x04\x17\xe0\xd4=k\xac\x13\xf4w;D\xbat$[\x00jdi:\xf8%\xfa*:4\xd3\xde\xb5>8\x87\xe4M\xd7p\x07\xf4\x142$c\x06u?/`E\x17g\xf9\\0\xe7D\r\x8fT\xd2\xee\xf9$/{FU^\x81\xc6\x9a\x9e2\x0c\x81\x05\xd1\x80\xcd:\xb6\xecm\xfc\xd8\xe1\x93#\xda4\xbd2\x01C\xb2\xe9J.\xcb\x02wz\xec\x08\x02ah\xca\xdb\x92\xd2\xc5\xbb\x82\x14\xda\xf6/\xe3\xe6\xf6\xe6J9,E\xf0\xa3\x8e\x08S\x02"

    res = decode_packet(data)
    print(res)
