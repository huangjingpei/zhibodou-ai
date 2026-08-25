import random
import time

import requests
import json

liveCookies = None
Cookie = "sessionid=BgAAoWLLAgS466TUYCcTtdpHksWjciOZuFOzI6tzTgaTdf41PKzhZovbHZ0r1%2BcGCGeAD0Nz2MF8uDw3qA00m0nD%2FESWzGcbdcgKvt9IzdH7;"
# Define the URL for the request
# BgAA%2FFOafIE%2BCOlw8w%2BQvBWNlhT2aDVbzOH%2FosvGy5I9YyXVkR0p15Il2ychbqbF%2FALS28mm5RkazWGmJzEKCy0YzOJITIqeVkWk
# BgAAqgtOVkuNBJ04uvkPbqHiEDNsznLwQGCrsx2JxkLQybaSpL%2B1zcfQxpscUJx71aKcqNxVfc5GyTDLbhG5hSIjM9o2P14SYLmv
url = "https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/live/msg?_rid=66f25abd-36d0ef35"
liveObjectId = None
liveId = None


def r():
    """
    获取当前时间的十六进制秒级时间戳。

    Returns:
        str: 当前时间的十六进制表示。
    """
    # 获取当前时间的秒级时间戳
    current_time = int(time.time())
    # 将整数转换为十六进制字符串并去掉 '0x' 前缀
    hex_time = hex(current_time)[2:]
    return hex_time


def i():
    """
    生成一个 8 位的随机十六进制字符串。

    Returns:
        str: 8 位随机十六进制字符串。
    """
    # 生成 8 个随机十六进制字符并连接成字符串
    random_hex = ''.join(random.randint(0, 15).__format__('x') for _ in range(8))
    return random_hex


def getrid():
    return f'{r()}-{i()}'


def msg():
    global liveCookies
    global liveObjectId
    global liveId
    headers = {
        "Connection": "keep-alive",
        "Content-Length": "2253",
        "Content-Type": "application/json",
        "Cookie": Cookie,
        "Host": "channels.weixin.qq.com",
        "Origin": "https://channels.weixin.qq.com",
        "Pragma": "no-cache",
        "Referer": "https://channels.weixin.qq.com/platform/live/liveBuild",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "X-WECHAT-UIN": "106131289",
        "sec-ch-ua": "\"Google Chrome\";v=\"129\", \"Not=A?Brand\";v=\"8\", \"Chromium\";v=\"129\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\""
    }

    payload = {
        "objectId": liveObjectId,
        "finderUsername": "v2_060000231003b20faec8c6eb891bc3d6cc0ce83db077728438455ec3f0fd580ef62005da2f0f@finder",
        "liveCookies": "xYFsnuKuxAfoSI+nvx7MVGiHkCtXslkeqXs+gpGLaGk6RlA3jnThAURYoAnJAMZtDQhycV0RdhqQ2YT+nT+Czl76Y/BNZ78OeLlTRXS9gxK5KePqitOaC4vnYPYrrv1/UpyBy5acBBykqc88IAqoIRRBQhNgZ2vyIUUHRB0C6rJFFhESlxBqL/hGzn1rtkJxieST0M2rmmseOWJ0Wv+uV22BnKYswvuDV9re0eQZO9aurUlTQGfmDVS6w5lDdRt5cNp8onK7rSAZYoFhJ81Dt/YRlOAo8Z7rxX6C4rJmPjN99cQNf4lcFS25CrHew19g1HfoqNfzQoP0IPEnIvAEviGonJOZ7EAQaU42U0NHNuaMuz41M8SqkJ1qwS9acB9nePPV6iYfJLCgHdG4bltR5VCDfV10ySLmBdFFZyTJz+K4rj7PamoaGoxo2iC/KGMPQ9zsLQGTAKUGHSz/dm5nTTK7DLUsBWmiElf67gb/tySwqrDwt/9jrDspkudq7zR5IrLmgkENq9Yj7GQwFtOSIjdijO2aEe3C/5URnUlNaoMkpy5626I6dP4c8T1fDeToZugz9cTH+cTFT1E4Z02rV4MIkdmJssC5KFEYrIBwc3U3x9ahVXsQIn7yonYfedWDs2Cfr0rFQgDv5te45qyxzRui4OtOZK6FsRMPWC/2ayJcgbmsmtY5s49ur47bwMFfopsPvgX9xAraz1toU4j6LXh1hArQieb7P+a/IEGzKDoPviWTUxf4EfzBAO/bZpWQy+X5XEu0Lsxeaq3C17W1zXd0g/BqHsRBjQ6LiYsDHKzdugUDzqFqQoXARb89RTpOcVC3nR6Z4LLWuU3bZibjHI/pWpENIfBrren8us0HO+jZ8KIFMFVuHGOtKPTUrRVPQWlgTdW4TFusrqMhJ0p37t56rtxSP8P2ddZuSw/zLFjM3EWkVgKuIgg6mGRlQMFxZju2uqqtadoj0T5tB+C2MzzhBhJIt9o3rMHzq3OxCQcXGb13IW481qaz4M1vpRjV/z2F06Xxmb7m5TkdYkep+9dEx9aN9JzgwPBFNa7cQC2R/ed81cQkdYOf7zwFfaixyxH4iJj9NBPlCNdagHia8AEuvvtYNzn6TiaAXWpl9uKSCudNA8u1rrar/YNaPUggA0N6WSugO8uZIs9ZEzy0Rj2ene6KPPG0vVo/3Ez8QXCHo6vL1DKTZJd3wCWfjAk3/sToxPNnjw0BVicU1JOu8RtjbuO3A3SlugS2o9fBN73xcv4nYqPzwuipqrpJma1/lDRTdRRm6Pilvzzl3S5FF1flMb5nH5Pqa3p3ek3FXJiVRdL/DqX5pSDZCzsgjMv+v/J7ByKA7+FEKC6e0gpdoAOtbTzhgAeVuof7IWPexKZ/xDRCjPVeGrsHMs0jrYQl0r0s/9F4sZHSym+rbSQPsZkGPxrgYkPBaSOdd4BdD0G/O7B4o9Twdnsll77xNROzN370XwNr+xDahKZ6/HI6xmGiCK1er8tTEqooQ4aNNHJM1G1yOC1dFtCt2Q9VLZH9DWkyOAoo5inTl5RkY8U93PQUqeQ0KJG8IaN+8Eqdg/a078uIgjmB8KBv15j0ErQHLxo8v1YNW7Hmy/O/fDtVTWf53p/1+80gr3vDLk+coQgXnv7XrLP6Ab2gSapmZCv298XAnjMON+Zf5DxbT2JOlOJUn5kdwneHELXbpcCUMbyv3i9742pu67ZYdCIjLh41QeYdZT07KYs2jwrSav1cS0DGhxbb5IudVjo6LNmA13bmzyKoaQyDDNFn59Pxb9hRNK4OtGBfwJTilL9m4KVcCM6tb+y0DA==",
        "liveId": liveId,
        "longpollingScene": 0,
        "timestamp": int(time.time() * 1000),
        "_log_finder_uin": "",
        "_log_finder_id": "v2_060000231003b20faec8c6eb891bc3d6cc0ce83db077728438455ec3f0fd580ef62005da2f0f@finder",
        "rawKeyBuff": None,
        "pluginSessionId": None,
        "scene": 7,
        "reqScene": 7
    }

    while True:
        payload['liveCookies'] = liveCookies
        payload['timestamp'] = int(time.time() * 1000)
        url = f"https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/live/msg?_rid={r()}-{i()}"
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        data = response.json()

        print(data['data']['msgList'], data['data']['appMsgList'])
        liveCookies = data['data']['liveCookies']


def join():
    global liveCookies
    global liveObjectId
    global liveId
    url2 = f'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/live/join_live?_rid={getrid()}'
    payload2 = {
        "finderUsername": "v2_060000231003b20faec8c6eb891bc3d6cc0ce83db077728438455ec3f0fd580ef62005da2f0f@finder",
        "liveId": liveId,
        "objectId": liveObjectId,
        "_log_finder_uin": "",
        "timestamp": f"{int(time.time() * 1000)}",
        "_log_finder_id": "v2_060000231003b20faec8c6eb891bc3d6cc0ce83db077728438455ec3f0fd580ef62005da2f0f@finder",
        "rawKeyBuff": None,
        "pluginSessionId": None,
        "scene": 7,
        "reqScene": 7
    }

    headers2 = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Length": "391",
        "Content-Type": "application/json",
        "Cookie": Cookie,
        "Host": "channels.weixin.qq.com",
        "Origin": "https://channels.weixin.qq.com",
        "Pragma": "no-cache",
        "Referer": "https://channels.weixin.qq.com/platform/live/liveBuild",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "X-WECHAT-UIN": "106131289",
        "sec-ch-ua": "\"Google Chrome\";v=\"129\", \"Not=A?Brand\";v=\"8\", \"Chromium\";v=\"129\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\""
    }

    response2 = requests.post(url2, headers=headers2, data=json.dumps(payload2))
    data = response2.json()
    liveCookies = data['data']['liveCookies']


def getliveId():
    get_shop_shelf = f'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/live/check_live_status?_rid={getrid()}'
    payload = {"timestamp": int(time.time() * 1000),
               "_log_finder_uin": "",
               "_log_finder_id": "v2_060000231003b20faec8c6eb891bc3d6cc0ce83db077728438455ec3f0fd580ef62005da2f0f@finder",
               "rawKeyBuff": None,
               "pluginSessionId": None,
               "scene": 7,
               "reqScene": 7
               }
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Length": "220",
        "Content-Type": "application/json",
        "Cookie": Cookie,
        "Host": "channels.weixin.qq.com",
        "Origin": "https://channels.weixin.qq.com",
        "Pragma": "no-cache",
        "Referer": "https://channels.weixin.qq.com/platform/live/liveBuild",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "X-WECHAT-UIN": "106131289",
        "sec-ch-ua": "\"Google Chrome\";v=\"129\", \"Not=A?Brand\";v=\"8\", \"Chromium\";v=\"129\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\""
    }
    res = requests.post(get_shop_shelf, headers=headers, data=json.dumps(payload))

    data = res.json()
    return {"liveObjectId": data['data']['liveObjectId'], "liveId": data['data']['liveId']}


if __name__ == '__main__':
    # cookie失效，重新登录

    id = getliveId()
    liveObjectId = id['liveObjectId']
    liveId = id['liveId']
    print(liveId)
    # 未开启直播，请直播

    join()
    msg()
