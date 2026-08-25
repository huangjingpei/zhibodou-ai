"""
@FileName：tb.py
@Description：个人开发者
@Author：秋恋猫
@Time：2025/3/4/周二 0:36
@Website：www.qiulianmao.com
@Copyright：©2022-2025 秋恋猫
"""
import json

from live_plate.Message import CreatChatMessage, CreatRoomMessage

commentList = []


# class Tb:
#     def __init__(self):
#         pass
#
#     def ParseTbComment(self, data):
#         data_test = data
#         try:
#
#             msg_list = []
#             data = data[data.find('{'): data.rfind('}') + 1]
#             data = json.loads(data)
#             if 'comments' in data['data']:
#                 for msg in data['data']['comments']:
#                     if msg['commentId'] not in commentList:
#                         commentList.append(msg['commentId'])
#                         msg_list.append(
#                             CreatChatMessage(name=msg['publisherNick'], head_image='', content=msg['content']))
#             if 'dataList' in data['data']:
#                 for msg in data['data']['dataList']:
#                     if msg['type'] == 'uv':
#                         room_detail = msg['data'][-1]['value'].split(',')
#                         msg_list.append(CreatRoomMessage(count=room_detail[5]))
#
#             return msg_list
#         except Exception as error:
#             print('解析错误', data_test)
#             return []

class Tb():
    def __init__(self):
        pass
    def ParseTbComment(self, data):
        data_test = data
        try:

            msg_list = []
            data = data[data.find('{'): data.rfind('}') + 1]
            data = json.loads(data)
            if 'comments' in data['data']:
                for msg in data['data']['comments']:
                    if msg['commentId'] not in commentList:
                        commentList.append(msg['commentId'])
                        msg_list.append(
                            CreatChatMessage(name=msg['publisherNick'], head_image='', content=msg['content']))
            if 'dataList' in data['data']:
                for msg in data['data']['dataList']:
                    if msg['type'] == 'uv':
                        room_detail = msg['data'][-1]['value'].split(',')
                        msg_list.append(CreatRoomMessage(count=room_detail[5]))

            return msg_list
        except Exception as error:
            print('解析错误', data_test)
            return []
