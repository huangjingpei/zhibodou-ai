def CreatMemberMessage(name, head_image):
    return {
        "type": "MemberMessage",
        "name": name,
        "head_image": head_image,
        "content": f"进入直播间"
    }


def CreatChatMessage(name, head_image, content):
    return {
        "type": "ChatMessage",
        "name": name,
        "head_image": head_image,
        "content": content

    }


def CreatSocialMessage(name, head_image):
    return {
        "type": "SocialMessage",
        "name": name,
        "head_image": head_image,
        "content": f"分享或关注了直播间"

    }


def CreatLikeMessage(name, head_image, count):
    return {
        "type": "LikeMessage",
        "name": name,
        "head_image": head_image,
        "count": str(count),
        "content": f"点赞了直播间{count}次"
    }


def CreatGiftMessage(name, head_image, gift_name, gift_count):
    return {
        "type": "GiftMessage",
        "name": name,
        "head_image": head_image,
        "gift_name": gift_name,
        "gift_count": str(gift_count),
        "content": f"{gift_name} X {gift_count}"
    }


def CreatRoomMessage(count):
    return {

        "type": "RoomMessage",
        "count": str(count),
        "content": f"当前直播间{count}人"
    }


def CreatSystemMessage(content):
    return {
        'type': 'SystemMessage',
        'content': content,
    }
