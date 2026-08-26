import base64
import gzip
from google.protobuf.json_format import MessageToDict
from live_plate.douyin import douyin_message_pb2

from live_plate.Message import CreatMemberMessage, CreatSocialMessage, CreatLikeMessage, CreatChatMessage, \
    CreatGiftMessage, CreatRoomMessage


def douyin_pb(data: bytes):

    o = douyin_message_pb2.PushFrame()
    o.ParseFromString(data)
    payload = o.palyload
    for t in o.headersList:
        if t.key == 'compress_type' and t.value == "gzip":
            payload = gzip.decompress(o.palyload)
            break
    return douyin_pb2(payload)


def douyin_pb2(data: bytes):
    if len(data) < 30:
        return []
    r = douyin_message_pb2.Response()
    r.ParseFromString(data)
    e = r

    listmessage = []
    messagelist = e.messages
    for t in messagelist:
        o = t.payload
        if t.method == "WebcastGiftMessage":
            message_ = douyin_message_pb2.GiftMessage()
            message_.ParseFromString(o)
            content = message_.common.describe
            res = MessageToDict(message_, preserving_proto_field_name=True)
            name = res['user']['nickname']
            head_img = res['user']['avatarThumb']['urlList'][0]
            giftname = content.split('个')[-1]
            repeatEnd = 0
            gift_Id = ''
            gift_Count = ''
            gift_name = ''
            if 'repeatEnd' in res:
                gift_Id = res['giftId']
                gift_Count = res['repeatCount']
                gift_name = giftname
                repeatEnd = 1
            else:
                if 'gift' in res:
                    if str(res['gift']['type']) == '2':
                        gift_Id = res['giftId']
                        gift_Count = res['repeatCount']
                        gift_name = giftname
                        repeatEnd = 1

                    if str(res['gift']['type']) == '4':
                        gift_Id = res['gift']['id']
                        gift_Count = 1
                        gift_name = giftname
                        repeatEnd = 1
                    if str(res['gift']['type']) == '13':
                        gift_Id = res['gift']['id']
                        gift_Count = 1
                        gift_name = giftname
                        repeatEnd = 1

            if repeatEnd == 1:
                listmessage.append(CreatGiftMessage(name=name,head_image=head_img, gift_name=gift_name, gift_count=gift_Count))




        elif t.method == "WebcastChatMessage":

            message_ = douyin_message_pb2.ChatMessage()
            message_.ParseFromString(o)
            res = MessageToDict(message_, preserving_proto_field_name=True)
            name = res['user']['nickname']
            head_img = res['user']['avatarThumb']['urlList'][0]
            content = message_.content
            listmessage.append(CreatChatMessage(name=name,head_image=head_img, content=content))


        elif t.method == "WebcastSocialMessage":
            message_ = douyin_message_pb2.SocialMessage()
            message_.ParseFromString(o)
            res = MessageToDict(message_, preserving_proto_field_name=True)
            name = res['user']['nickname']

            head_img = res['user']['avatarThumb']['urlList'][0]

            listmessage.append(CreatSocialMessage(name=name,head_image=head_img))
        elif t.method == "WebcastLikeMessage":
            message_ = douyin_message_pb2.LikeMessage()
            message_.ParseFromString(o)
            res = MessageToDict(message_, preserving_proto_field_name=True)
            name = res['user']['nickname']

            head_img = res['user']['avatarThumb']['urlList'][0]



            listmessage.append(CreatLikeMessage(name=name,head_image=head_img,count=res['count']))

        elif t.method == "WebcastMemberMessage":

            message_ = douyin_message_pb2.MemberMessage()
            message_.ParseFromString(o)
            res = MessageToDict(message_, preserving_proto_field_name=True)
            content = '进入直播间'
            name = res['user']['nickname']
            head_img = res['user']['avatarThumb']['urlList'][0]


            listmessage.append(CreatMemberMessage(name=name,head_image=head_img))






        elif t.method == "WebcastRoomUserSeqMessage":
            message_ = douyin_message_pb2.RoomUserSeqMessage()
            message_.ParseFromString(o)
            res = MessageToDict(message_, preserving_proto_field_name=True)

            listmessage.append(CreatRoomMessage(count=res['total']))

    return listmessage

