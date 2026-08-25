from live_plate.Message import CreatChatMessage, CreatGiftMessage, CreatMemberMessage
from live_plate.nimo.tars.nimo import WSPushMessage_V2, WebSocketCommand, Ht, MessageNotice, NewUserEnterRoomNotice, \
    SendItemSubBroadcastPacket, SendGiftEffectBroadcastPacket

from live_plate.nimo.tars.Tars import TarsInputStream


def nimo_tars(data: bytes):
    e = TarsInputStream(data)
    n = WebSocketCommand()
    n.readFrom(e)
    listmessage = []

    if n.iCmdType == 22:
        e1 = TarsInputStream(n.vData)
        D = WSPushMessage_V2()
        D.readFrom(e1)

        for j in range(len(D.vMsgItem.value)):
            F = D.vMsgItem.value[j]
            G = F.iUri
            V = F.lMsgId
            if G == 1400:
                K = MessageNotice()
                Y = TarsInputStream(F.sMsg)
                K.readForm(Y)
                result = K.__dict__
                nickname = result['tUserInfo']['sNickName']
                roomid = result['lRoomId']

                uid = result['tUserInfo']['lUid']
                content = result['sContent']
                head_image = result['sAvatar']



                listmessage.append(CreatChatMessage(name=nickname,head_image=head_image,content=content))

            if G == 9000 or G == 9002:
                """
                礼物消息
                
                """
                K = SendItemSubBroadcastPacket()
                Y = TarsInputStream(F.sMsg)
                K.readForm(Y)

                result = K.__dict__

                nickname = result['sSenderNick']
                uid = result['lSenderUid']
                roomid = result['lRoomId']
                head_image = result['sSenderAvatarUrl']
                count = result['iItemCount']
                price = result['fItemPrice']

                giftType = result['iItemType']

                content = f"送礼{giftType} |  X {count}"


                listmessage.append(CreatGiftMessage(name=nickname, head_image=head_image, gift_name=giftType, gift_count=count))
            if G == 1516:
                """
                进入房间
                """
                K = NewUserEnterRoomNotice()
                Y = TarsInputStream(F.sMsg)
                K.readForm(Y)

                result = K.__dict__
                nickname = result['sNick']
                uid = result['lUserId']
                roomid = result['lRoomId']
                head_image = result['sAvatarUrl']


                listmessage.append(CreatMemberMessage(name=nickname,head_image=head_image))

    return listmessage
