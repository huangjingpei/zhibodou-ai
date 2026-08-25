import gzip
from google.protobuf.json_format import MessageToDict
from live_plate.tiktok import tiktok_message_pb2

from live_plate.Message import CreatMemberMessage, CreatSocialMessage, CreatLikeMessage, CreatChatMessage, \
    CreatGiftMessage


def tiktok_pb(data: bytes):
    """
    tiktok PushFrame解析
    :param data:
    :param config:
    :return:
    """
    o = tiktok_message_pb2.PushFrame1()
    o.ParseFromString(data)
    payload = o.palyload1
    for t in o.headersList1:
        if t.key1 == 'compress_type' and t.value1 == "gzip":
            payload = gzip.decompress(o.palyload1)
            break
    return tiktok_pb2(payload)


def tiktok_pb2(data: bytes):
    """
    tiktok response解析
    :param data: onmessage
    :param config: setting/config
    :return:
    """
    listmessage = []
    r = tiktok_message_pb2.Response1()
    r.ParseFromString(data)

    e = r
    messagelist = e.messages1
    for t in messagelist:
        o = t.payload1
        try:
            if t.method1 == "WebcastGiftMessage":
                message_ = tiktok_message_pb2.GiftMessage1()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name = res['user1']['nickname1']
                head_img = res['user1']['avatarThumb1']['urlList1'][0]

                repeatEnd = 0

                gift_Id = res['giftId1']
                gift_count = res['repeatCount1']
                gift_name = res['gift1']['name1']
                if 'repeatEnd1' in res:
                    if 'gift1' in res:
                        pass

                    repeatEnd = 1
                else:
                    if 'gift1' in res:
                        if str(res['gift1']['type1']) == '2':

                            repeatEnd = 1
                        elif str(res['gift1']['type1']) == '3':

                            repeatEnd = 1
                        elif str(res['gift1']['type1']) == '4':

                            repeatEnd = 1

                if repeatEnd == 1:
                    listmessage.append(CreatGiftMessage(name=name,head_image=head_img, gift_name=gift_name, gift_count=gift_count))

            elif t.method1 == "WebcastChatMessage":
                message_ = tiktok_message_pb2.ChatMessage1()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name = res['user1']['nickname1']

                head_img = res['user1']['avatarThumb1']['urlList1'][0]
                content = message_.content1

                listmessage.append(CreatChatMessage(name=name, head_image=head_img,content=content))

            elif t.method1 == "WebcastSocialMessage":
                message_ = tiktok_message_pb2.SocialMessage1()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name = res['user1']['nickname1']
                head_img = res['user1']['avatarThumb1']['urlList1'][0]
                listmessage.append(CreatSocialMessage(name=name, head_image=head_img))

            elif t.method1 == "WebcastLikeMessage":
                message_ = tiktok_message_pb2.LikeMessage1()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name = res['user1']['nickname1']
                count = res['count1']
                head_img = res['user1']['avatarThumb1']['urlList1'][0]
                listmessage.append(CreatLikeMessage(name=name, head_image=head_img, count=count))

            elif t.method1 == "WebcastMemberMessage":

                message_ = tiktok_message_pb2.MemberMessage1()
                message_.ParseFromString(o)
                res = MessageToDict(message_, preserving_proto_field_name=True)
                name = res['user1']['nickname1']
                head_img = res['user1']['avatarThumb1']['urlList1'][0]
                listmessage.append(CreatMemberMessage(name=name, head_image=head_img))
        except Exception as e:
            print()

    return listmessage
