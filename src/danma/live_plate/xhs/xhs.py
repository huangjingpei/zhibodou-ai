"""
@FileName：xhs.py
@Description：个人开发者
@Author：秋恋猫
@Time：2025/3/4/周二 0:38
@Website：www.qiulianmao.com
@Copyright：©2022-2025 秋恋猫
"""
import base64
import json

from live_plate.Message import CreatChatMessage,CreatMemberMessage,CreatRoomMessage,CreatSocialMessage

class Xhs():
    def __init__(self):
        pass

    def ParseXhsComment(self, framereceived):
        try:

            data = json.loads(framereceived)
            if 'body' in data and 'customData' in data['body']:
                customData = json.loads(data['body']['customData'])
                return self.Parse(customData)
        except Exception as e:
            print(f'error Xhs ParseXhsComment{e}')
        return []

    def ParseXhsShopComment(self, framereceived):
        data = json.loads(framereceived)
        if 'b' in data:
            data = data['b']
            if 'd' in data and 'b' in data['d']:
                data = data['d']['b']
                for msg in data:
                    if 'd' in msg:
                        msg = msg['d']
                        decoded_bytes = base64.b64decode(msg)
                        decoded_string = decoded_bytes.decode('utf-8')

                        customData = json.loads(json.loads(decoded_string)['customData'])
                        return self.Parse(customData)

    def Parse(self, customData):
        msg_list = []
        try:

            if customData['type'] == 'text':
                msg_list.append(CreatChatMessage(name=customData['profile']['nickname'],
                                                 head_image=customData['profile']['avatar'],
                                                 content=customData['desc']))

            elif customData['type'] == 'audience_join_v2':
                msg_list.append(CreatMemberMessage(name=customData['profile']['nickname'],
                                                   head_image=customData['profile']['avatar'], ))

            elif customData['type'] == 'refresh':
                msg_list.append(CreatRoomMessage(count=customData['room_data']['member_count']))

            elif customData['type'] == 'follow_emcee':
                msg_list.append(CreatSocialMessage(name=customData['profile']['nickname'],
                                                   head_image=customData['profile']['avatar'], ))
        except Exception as e:
            pass

        return msg_list