"""
@FileName：facebook.py
@Description：个人开发者
@Author：秋恋猫
@Time：2024/10/27/周日 17:36
@Website：www.qiulianmao.com
@Copyright：©2022-2024 秋恋猫
"""
import json
from live_plate.Message import CreatMemberMessage, CreatSocialMessage, CreatLikeMessage, CreatChatMessage, \
    CreatGiftMessage, CreatRoomMessage
from live_plate.kuaishou.ks import head_img


def ParseFaceBookComment(framereceived):
    text = ''
    msg_list = []
    for value in framereceived:
        # 仅处理可打印字符
        if 32 <= value <= 126:  # ASCII 可打印字符范围
            text += chr(value)
        else:
            # 对于不可打印字符，可以选择添加一个占位符或忽略
            text += ''

    stack = []
    start = -1

    if ('{' in text and '}' in text):

        for i, char in enumerate(text):
            if char == '{':
                if not stack:
                    start = i  # 记录第一个 '{' 的位置
                stack.append(char)
            elif char == '}':
                if stack:
                    stack.pop()
                    if not stack:
                        # 当栈为空时，意味着我们找到了完整的 JSON
                        text = text[start:i + 1]

        text = json.loads(text)
        if 'data' in text:
            data = text['data']
            if 'live_video_comment_create_subscribe' in data:
                nickname = data['live_video_comment_create_subscribe']['comment']['user']['name']
                head_img = data['live_video_comment_create_subscribe']['comment']['user']['profile_picture']['uri']
                content = data['live_video_comment_create_subscribe']['comment']['body']['text']

                msg_list.append(CreatChatMessage(name=nickname, head_image=head_img, content=content))

    return msg_list
