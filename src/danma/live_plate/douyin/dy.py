import base64
import gzip
from google.protobuf.json_format import MessageToDict
from live_plate.douyin import douyin_message_pb2

from live_plate.Message import CreatMemberMessage, CreatSocialMessage, CreatLikeMessage, CreatChatMessage, \
    CreatGiftMessage, CreatRoomMessage


def _extract_user(res: dict):
    user = res.get('user') or {}
    name = user.get('nickname') or '游客'
    head_img = ''
    avatar = user.get('avatarThumb') or {}
    urls = avatar.get('urlList') or []
    if urls:
        head_img = urls[0]
    return name, head_img


def douyin_pb(data: bytes):
    if not data or isinstance(data, str) or len(data) < 5:
        return []
    try:
        o = douyin_message_pb2.PushFrame()
        o.ParseFromString(data)
        payload = o.palyload
        for t in o.headersList:
            if t.key == 'compress_type' and t.value == "gzip":
                payload = gzip.decompress(o.palyload)
                break
        return douyin_pb2(payload)
    except Exception:
        return []


def douyin_pb2(data: bytes):
    if not data or len(data) < 30:
        return []
    try:
        r = douyin_message_pb2.Response()
        r.ParseFromString(data)
    except Exception:
        return []

    listmessage = []
    messagelist = r.messages
    for t in messagelist:
        try:
            o = t.payload
            if t.method == "WebcastGiftMessage":
                message_ = douyin_message_pb2.GiftMessage()
                message_.ParseFromString(o)
                content = getattr(getattr(message_, 'common', None), 'describe', '') or ''
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name, head_img = _extract_user(res)
                giftname = content.split('个')[-1] if '个' in content else (content or '礼物')
                repeatEnd = 0
                gift_Id = ''
                gift_Count = ''
                gift_name = ''
                if 'repeatEnd' in res:
                    gift_Id = res.get('giftId', '')
                    gift_Count = res.get('repeatCount', 1)
                    gift_name = giftname
                    repeatEnd = 1
                else:
                    if 'gift' in res:
                        g_type = str(res['gift'].get('type', ''))
                        if g_type == '2':
                            gift_Id = res.get('giftId', '')
                            gift_Count = res.get('repeatCount', 1)
                            gift_name = giftname
                            repeatEnd = 1
                        elif g_type in ('4', '13'):
                            gift_Id = res['gift'].get('id', '')
                            gift_Count = 1
                            gift_name = giftname
                            repeatEnd = 1

                if repeatEnd == 1:
                    listmessage.append(CreatGiftMessage(name=name, head_image=head_img, gift_name=gift_name, gift_count=gift_Count))

            elif t.method == "WebcastChatMessage":
                message_ = douyin_message_pb2.ChatMessage()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name, head_img = _extract_user(res)
                content = message_.content
                listmessage.append(CreatChatMessage(name=name, head_image=head_img, content=content))

            elif t.method == "WebcastSocialMessage":
                message_ = douyin_message_pb2.SocialMessage()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name, head_img = _extract_user(res)
                listmessage.append(CreatSocialMessage(name=name, head_image=head_img))

            elif t.method == "WebcastLikeMessage":
                message_ = douyin_message_pb2.LikeMessage()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name, head_img = _extract_user(res)
                listmessage.append(CreatLikeMessage(name=name, head_image=head_img, count=res.get('count', 1)))

            elif t.method == "WebcastMemberMessage":
                message_ = douyin_message_pb2.MemberMessage()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name, head_img = _extract_user(res)
                listmessage.append(CreatMemberMessage(name=name, head_image=head_img))

            elif t.method == "WebcastRoomUserSeqMessage":
                message_ = douyin_message_pb2.RoomUserSeqMessage()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                listmessage.append(CreatRoomMessage(count=res.get('total', 0)))

        except Exception:
            continue

    return listmessage

