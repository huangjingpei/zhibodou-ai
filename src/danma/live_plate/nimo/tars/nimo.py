"""
@FileName：nimo_tars.py
@Description：个人开发者
@Author：秋恋猫
@Time：2024/2/1/001 01:51
@Website：www.qiulianmao.com
@Copyright：©2022-2024 秋恋猫
"""
from live_plate.nimo.tars.BinBuffer import BinBuffer
from live_plate.nimo.tars.Tars import TarsInputStream
from live_plate.nimo.tars.Vector import Vector


class WSPushMessage_V2:
    def __init__(self):
        self.sGroupId = ""
        self.vMsgItem = Vector(WSMsgItem())

    def readFrom(self, t: TarsInputStream):
        self.sGroupId = t.readString(0, False, self.sGroupId).decode('utf-8')
        self.vMsgItem = t.readVector(1, False, self.vMsgItem)


class WSMsgItem:
    def __init__(self):
        self.iUri = 0
        self.sMsg = BinBuffer()
        self.lMsgId = 0

    def _clone(self):
        return WSMsgItem()

    def _write(self, t: TarsInputStream, e, n):
        # Assuming writeStruct is a method of 't' that writes structured data
        # t.__writeStruct(e, n)
        pass

    def _read(self, t: TarsInputStream, e, n):
        return t.readStruct(e, True, n)

    def readFrom(self, t: TarsInputStream):
        self.iUri = t.readInt64(0, False, self.iUri)
        self.sMsg = t.readBytes(1, False, self.sMsg)
        self.lMsgId = t.readInt64(2, False, self.lMsgId)


class Ht:
    def __init__(self):
        self.rank = 0
        self.distance = 0
        self.beforeCountdown = 0
        self.afterCountdown = 0
        self.countdownStartTime = 0
        self.countdownEndTime = 0

        # self.anchorRankList = Vector(SimpleAnchorRankInfo())  # Replace with actual implementations
        self.rankStatus = 0
        self.finishAfterCountdown = 0
        self.roomId = 0
        self.udbUserId = 0

    def readFrom(self, t: TarsInputStream):
        self.rank = t.readInt32(0, False, self.rank)
        self.distance = t.readInt32(1, False, self.distance)
        self.beforeCountdown = t.readInt32(3, False, self.beforeCountdown)
        self.afterCountdown = t.readInt32(4, False, self.afterCountdown)
        self.countdownStartTime = t.readInt64(5, False, self.countdownStartTime)
        self.countdownEndTime = t.readInt64(6, False, self.countdownEndTime)
        # self.anchorRankList = t.read(tarscore.vector, 7, False, self.anchorRankList)
        self.rankStatus = t.readInt32(8, False, self.rankStatus)
        self.finishAfterCountdown = t.readInt32(9, False, self.finishAfterCountdown)
        self.roomId = t.readInt64(10, False, self.roomId)
        self.udbUserId = t.readInt64(11, False, self.udbUserId)


class WebSocketCommand:
    def __init__(self):
        self.iCmdType = 0
        self.vData = b''  # 二进制数据
        self.lRequestId = 0
        self.traceId = ""
        self.iEncryptType = 0
        self.lTime = 0
        self.sMD5 = ""

    def readFrom(self, t: TarsInputStream):
        self.iCmdType = t.readInt32(0, False, self.iCmdType)
        self.vData = t.readBytes(1, False, self.vData)
        self.lRequestId = t.readInt64(2, False, self.lRequestId)
        self.traceId = t.readString(3, False, self.traceId).decode('utf-8')
        self.iEncryptType = t.readInt64(4, False, self.iEncryptType)
        self.lTime = t.readInt64(5, False, self.lTime)
        self.sMD5 = t.readString(6, False, self.sMD5).decode('utf-8')


class MessageNotice:
    def __init__(self):
        self.lRoomId = 0
        self.sAvatar = ""
        self.sContent = "sContent"
        self.tUserInfo = SenderInfo()

    def readForm(self, t: TarsInputStream):
        self.tUserInfo = (t.readStruct(0, False, self.tUserInfo)).__dict__
        self.lRoomId = t.readInt64(1, False, self.lRoomId)
        self.sContent = t.readString(2, False, self.sContent).decode('utf-8')
        self.sAvatar = t.readString(11, False, self.sAvatar).decode('utf-8')


class SenderInfo:
    def __init__(self):
        self.lUid = 0
        self.sNickName = ""

    def readFrom(self, t: TarsInputStream):
        self.lUid = t.readInt64(0, False, self.lUid)
        self.sNickName = t.readString(1, False, self.sNickName).decode('utf-8')

        return self


class NewUserEnterRoomNotice:
    def __init__(self):
        self.lUserId = 0
        self.sNick = ""
        self.lRoomId = 0
        self.sAvatarUrl = ""

    def readForm(self, t: TarsInputStream):
        self.lUserId = t.readInt64(0, False, self.lUserId)
        self.sNick = t.readString(1, False, self.sNick).decode('utf-8')
        self.lRoomId = t.readInt64(5, False, self.lRoomId)
        self.sAvatarUrl = t.readString(7, False, self.sAvatarUrl).decode('utf-8')


class SendItemSubBroadcastPacket:
    def __init__(self):
        self.iItemType = 0
        self.iItemCount = 0
        self.lPresenterUid = 0
        self.lSenderUid = 0
        self.sSenderNick = ''
        self.fItemPrice = ''
        self.sSenderAvatarUrl = ''
        self.lRoomId = 0

    def readForm(self, t: TarsInputStream):
        self.iItemType = t.readInt32(0, False, self.iItemType)
        self.iItemCount = t.readInt32(1, False, self.iItemCount)
        self.lPresenterUid = t.readInt64(2, False, self.lPresenterUid)
        self.lSenderUid = t.readInt64(3, False, self.lSenderUid)
        self.sSenderNick = t.readString(5, False, self.sSenderNick).decode('utf-8')
        self.lRoomId = t.readInt64(6, False, self.lRoomId),
        self.sSenderAvatarUrl = t.readString(12, False, self.sSenderAvatarUrl).decode('utf-8')
        self.fItemPrice = t.readFloat(17, False, self.fItemPrice)


class SendGiftEffectBroadcastPacket:
    def __init__(self):
        self.sSenderAvatarUrl = None
        self.iPayType = None
        self.iComboScore = None
        self.lRoomId = None
        self.sSenderNick = None
        self.sPresenterNick = None
        self.lSenderUid = None
        self.lPresenterUid = None
        self.iItemCount = None
        self.iItemType = None

    def readForm(self, t: TarsInputStream):
        self.iItemType = t.readInt32(0, False, self.iItemType)
        self.iItemCount = t.readInt32(1, False, self.iItemCount)
        self.lPresenterUid = t.readInt64(2, False, self.lPresenterUid)
        self.lSenderUid = t.readInt64(3, False, self.lSenderUid)
        self.sPresenterNick = t.readString(4, False, self.sPresenterNick)
        self.sSenderNick = t.readString(5, False, self.sSenderNick)
        self.lRoomId = t.readInt64(6, False, self.lRoomId)
        self.iComboScore = t.readInt32(7, False, self.iComboScore)
        self.iPayType = t.readInt32(8, False, self.iPayType)

        self.sSenderAvatarUrl = t.readString(14, False, self.sSenderAvatarUrl),
