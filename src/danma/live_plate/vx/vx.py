import base64
import json
import hashlib

from live_plate.Message import CreatGiftMessage, CreatChatMessage, CreatMemberMessage, CreatLikeMessage

head_img_dict = {}

uid_dict = {}

auth_dict = {}

fans_dict = {}


message_list=[]
message_list2=[]
# md5加密
def md5_hash(text):
    m = hashlib.md5()
    m.update(text.encode('utf-8'))
    return m.hexdigest()


def get_uid(username_id, client_id):
    """
    获取用户uid
    :param username_id:
    :param client_id:
    :return:
    """

    if 'rewardmsg' in client_id or 'comboreward' in client_id:
        if username_id in uid_dict:
            uid = uid_dict[username_id]
            return uid
        else:
            return ''

    for i in ['joinlive', 'comment', 'appmsg']:
        if i in client_id:
            uid = md5_hash(client_id.split('_o9h')[-1])
            uid_dict[username_id] = uid
            return uid


def auth(message):
    """
    主播信息
    :param message:
    :return:
    """
    try:
        auth_dict['type'] = 'auth_message'
        auth_dict['uid'] = message['data']['finderUser']['uniqId']
        auth_dict['name'] = message['data']['finderUser']['nickname']

    except Exception as e:
        print(e, message)


def get_head_img(nickname):
    """
    获取用户头像
    :param nickname:
    :return:
    """
    if nickname in head_img_dict:
        return head_img_dict[nickname]
    else:
        return ''


def head_img(message):
    """
    头像数据：刷礼物才有
    有头像总比没有头像好！！！！
    有头像总比没有头像好！！！！
    :param message:
    :return:
    """

    for msg in message['data']['recentRewardContacts']:

        name = msg['contact']['contact']['nickname']
        head_url = msg['contact']['contact']['headUrl']
        head_img_dict[name] = head_url


def member(message):
    """
    进入直播间
    :param message:
    :return:
    """

    return CreatMemberMessage(name=message['nickname'],head_image="")



def chat(message):
    """
    发言
    :param message:
    :return:
    """


    return CreatChatMessage(name=message['nickname'],head_image='',content=message['content'])




def gift(message):
    """
    礼物信息
    :param message:
    :return:
    """

    payload = message['payload']
    payload = payload.encode(encoding='utf-8')
    encode_data = base64.b64decode(payload)
    gift_data = encode_data.decode(encoding='utf-8')
    gift_data = json.loads(gift_data)


    return CreatGiftMessage(name=message['fromUserContact']['contact']['nickname'], head_image='', gift_name=gift_data['reward_gift']['name'], gift_count=gift_data['reward_product_count'])






def gift_end(message):
    payload = message['payload']
    payload = payload.encode(encoding='utf-8')
    encode_data = base64.b64decode(payload)
    gift_data = encode_data.decode(encoding='utf-8')
    gift_data = json.loads(gift_data)


    return CreatGiftMessage(name=message['fromUserContact']['contact']['nickname'], head_image='',
                            gift_name=gift_data['reward_gift']['name'], gift_count=gift_data['reward_product_count'])




def like(message, config):
    """
    点赞信息
    :param message:
    :return:
    """
    print('点赞', message)
    fans = ''
    if 'badgeInfos' in message['fromUserContact']:
        res = message['fromUserContact']['badgeInfos']
        for msg in res:
            if msg['badgeType'] == 15:
                fans = msg['badgeName']
                fans_dict[message['fromUserContact']['contact']['nickname']] = fans


    return CreatLikeMessage(name=message['fromUserContact']['contact']['nickname'],head_image='',count=10)

def ParseVxMessage(res):
    msg_list = []
    for msg in res['data']['msgList']:
        if msg['type'] == 1 and msg['seq'] not in message_list:
            # print('解析发言')
            chat_message = chat(msg, )


            msg_list.append(chat_message)
            message_list.append(msg['seq'])

        if msg['type'] == 10005 and msg['seq'] not in message_list:
            member_message =member(msg)
            msg_list.append(member_message)


            message_list.append(msg['seq'])

    for msg in res['data']['appMsgList']:
        if msg['msgType'] == 20009 and msg['seq'] not in message_list2:
            # print('连刷过程中的礼物信息')
            gift_message = gift(msg)
            msg_list.append(gift_message)


            message_list2.append(msg['seq'])

        # if msg['msgType'] == 20013 and msg['seq'] not in message_list2:
        #     # print('连刷结束后的礼物信息')
        #     gift_end_message = gift_end(msg)
        #
        #     print(gift_end_message)
        #     message_list2.append(msg['seq'])

        if msg['msgType'] == 20006 and msg['seq'] not in message_list2:
            # print('点赞,连击10次触发')
            like_message = like(msg)
            msg_list.append(like_message)

            print(like_message)
            message_list2.append(msg['seq'])

    return msg_list