import gzip
import json

from configobj import ConfigObj

import codecs

from live_plate.Message import CreatChatMessage, CreatMemberMessage, CreatSocialMessage, CreatRoomMessage
from live_plate.pdd import pdd_message_pb2


def b(e):
    e = bytearray(e)
    s = e[16:]
    new8 = uint8_arr_to_int(s)
    return new8


def uint8_arr_to_int(uint8_arr):
    arr = []
    for i in range(len(uint8_arr)):
        arr.append(uint8_arr[i])
    return arr


def S(e):
    e = bytearray(e)
    n = len(e)
    r = ""
    for i in range(n):
        r += chr(e[i])
    r = decode(r)
    r = k(r)
    return r


def decode(e):
    t = a(e)
    n = len(t)
    r = 0
    s = []
    while True:
        o = l(t, n, r)
        if o is False:
            break
        s.append(o)
        r += 1
    return utf16_codes_to_string(s)


def a(e):
    r = []
    i = 0
    a = len(e)
    while i < a:
        t = ord(e[i])
        i += 1
        if 55296 <= t <= 56319 and i < a:
            n = ord(e[i])
            if 56320 == (64512 & n):
                r.append(((1023 & t) << 10) + (1023 & n) + 65536)
                i += 1
            else:
                r.append(t)
        else:
            r.append(t)
    return r


def l(t, n, r):
    if r > n:
        raise Exception("Invalid byte index")
    if r == n:
        return False
    e = 255 & t[r]
    r += 1
    if 128 & e == 0:
        return e
    if 224 & e == 192:
        i = (31 & e) << 6 | u(r, t)
        if i >= 128:
            return i
        raise Exception("Invalid continuation byte")
    if 240 & e == 224:
        i = (15 & e) << 12 | u(r, t) << 6 | u(r, t)
        if i >= 2048:
            return i
        raise Exception("Invalid continuation byte")
    if 248 & e == 240:
        i = (7 & e) << 18 | u(r, t) << 12 | u(r, t) << 6 | u(r, t)
        if 65536 <= i <= 1114111:
            return i
        raise Exception("Invalid UTF-8 detected")
    raise Exception("Invalid UTF-8 detected")


def k(e):
    return e.replace("\n", "\\\\n").replace("\r", "\\\\r").replace("\t", "\\\\t").replace("\u2028", "")


def utf16_codes_to_string(e):
    t = ""
    n = len(e)
    r = -1
    while r < n - 1:
        r += 1
        t_chr = e[r]
        if t_chr > 65535:
            t += chr(((t_chr - 65536) >> 10) & 1023 | 55296)
            t_chr = 56320 | 1023 & t_chr
        t += chr(t_chr)
    return t


def u(r, t):
    # global r, t
    e = 255 & t[r]
    r += 1
    return e


def pdd_pb(data: bytes):
    listmessage=[]

    try:
        data = list(data)
        result = b(data)
        TitanDownstream = pdd_message_pb2.TitanDownstream()
        TitanDownstream.ParseFromString(bytes(result))
        body = gzip.decompress(TitanDownstream.body)
        if TitanDownstream.command == "titan.mLite":
            MulticastLite = pdd_message_pb2.MulticastLite()
            MulticastLite.ParseFromString(body)
        elif TitanDownstream.command == "titan.mNotify":
            MulticastNotify = pdd_message_pb2.MulticastNotify()
            MulticastNotify.ParseFromString(body)
        result = S(list(MulticastLite.payload))
        result = json.loads(result)
        for i in result:

            if i['message_type'] == 'live_chat':
                for message in i['message_data']['live_chat_list']:

                    listmessage.append(CreatChatMessage(name=message['nickname'], head_image="", content=message['chat_message']))

            if i['message_type'] == 'live_chat_notice':

                for message in i['message_data']['live_chat_notice_list']:
                    if message['live_chat_notice_type'] == 'enter':


                        listmessage.append(CreatMemberMessage(message['live_chat_notice_data']['user_list'][0]['nickname'], ""))


    except Exception as e:
        print(e)

    return listmessage

class Pdd():
    def b(self, e):
        e = bytearray(e)
        s = e[16:]
        new8 = self.uint8_arr_to_int(s)
        return new8

    def uint8_arr_to_int(self, uint8_arr):
        arr = []
        for i in range(len(uint8_arr)):
            arr.append(uint8_arr[i])
        return arr

    def S(self, e):
        e = bytearray(e)
        n = len(e)
        r = ""
        for i in range(n):
            r += chr(e[i])
        r = self.decode(r)
        r = self.k(r)
        return r

    def decode(self, e):
        t = self.a(e)
        n = len(t)
        r = 0
        s = []
        while True:
            o = self.l(t, n, r)
            if o is False:
                break
            s.append(o)
            r += 1
        return self.utf16_codes_to_string(s)

    def a(self, e):
        r = []
        i = 0
        a = len(e)
        while i < a:
            t = ord(e[i])
            i += 1
            if 55296 <= t <= 56319 and i < a:
                n = ord(e[i])
                if 56320 == (64512 & n):
                    r.append(((1023 & t) << 10) + (1023 & n) + 65536)
                    i += 1
                else:
                    r.append(t)
            else:
                r.append(t)
        return r

    def l(self, t, n, r):
        if r > n:
            raise Exception("Invalid byte index")
        if r == n:
            return False
        e = 255 & t[r]
        r += 1
        if 128 & e == 0:
            return e
        if 224 & e == 192:
            i = (31 & e) << 6 | self.u(r, t)
            if i >= 128:
                return i
            raise Exception("Invalid continuation byte")
        if 240 & e == 224:
            i = (15 & e) << 12 | self.u(r, t) << 6 | self.u(r, t)
            if i >= 2048:
                return i
            raise Exception("Invalid continuation byte")
        if 248 & e == 240:
            i = (7 & e) << 18 | self.u(r, t) << 12 | self.u(r, t) << 6 | self.u(r, t)
            if 65536 <= i <= 1114111:
                return i
            raise Exception("Invalid UTF-8 detected")
        raise Exception("Invalid UTF-8 detected")

    def k(self, e):
        return e.replace("\n", "\\\\n").replace("\r", "\\\\r").replace("\t", "\\\\t").replace("\u2028", "")

    def utf16_codes_to_string(self, e):
        t = ""
        n = len(e)
        r = -1
        while r < n - 1:
            r += 1
            t_chr = e[r]
            if t_chr > 65535:
                t += chr(((t_chr - 65536) >> 10) & 1023 | 55296)
                t_chr = 56320 | 1023 & t_chr
            t += chr(t_chr)
        return t

    def u(self, r, t):
        # global r, t
        e = 255 & t[r]
        r += 1
        return e

    def pdd_pb(self, data):
        listmessage = []

        try:

            result = self.b(data)

            TitanDownstream = pdd_message_pb2.TitanDownstream()
            TitanDownstream.ParseFromString(bytes(result))
            body = gzip.decompress(TitanDownstream.body)

            if TitanDownstream.command == "titan.mLite":
                MulticastLite = pdd_message_pb2.MulticastLite()
                MulticastLite.ParseFromString(body)
            elif TitanDownstream.command == "titan.mNotify":
                MulticastNotify = pdd_message_pb2.MulticastNotify()
                MulticastNotify.ParseFromString(body)

            else:
                print(TitanDownstream.command)

            result = self.S(list(MulticastLite.payload))
            result = json.loads(result)

            for i in result:
                print(i)

                if i['message_type'] == 'live_chat':
                    for message in i['message_data']['live_chat_list']:
                        listmessage.append(
                            CreatChatMessage(name=message['nickname'], head_image="", content=message['chat_message']))
                if i['message_type'] == 'live_chat_notice':
                    for message in i['message_data']['live_chat_notice_list']:
                        if message['live_chat_notice_type'] == 'enter':
                            listmessage.append(
                                CreatMemberMessage(message['live_chat_notice_data']['user_list'][0]['nickname'], ""))
                if i['message_type'] == 'live_chat_ext':
                    for message in i['message_data']['live_chat_ext_list']:
                        listmessage.append(CreatSocialMessage(name=message['body']['title'], head_image=""))
                if i['message_type'] == 'live_chat_notice':
                    for message in i['message_data']['live_chat_notice_list']:
                        listmessage.append(
                            CreatSocialMessage(message['live_chat_notice_data']['user_list'][0]['nickname']))

                if i['message_type'] == "live_realtime_statistic":
                    for message in i['message_data']['live_realtime_statistic_list']:
                        print(message.get("statistic_name", ""), message.get("statistic_value", ""))
                        if message.get("statistic_name", "") == "在线人数":
                            print("在线人数", message['statistic_value'])
                            listmessage.append(CreatRoomMessage(message['statistic_value']))



        except Exception as e:
            print('pdd Error', e)

        return listmessage
if __name__ == '__main__':
    hex = '000a0066000000000000000000000598300152ed0a1f8b0800000000000000ed57cb6fdb3618c7801db601bb14d8a5bb6cea50ec6025e2432269c028f232d6438ba1ed4e4b415012f5889e96283b7691c3fee41d76df47394e93262dd2a2d83060b62c48e4c7efc5eff7e3e7affef8f3cb07df610f63843095980694059ec0d2430f7f4a048da244099770eeb9d44f882b54e4bb5473ac58c8021c28e7afef7f7fe354baef55aaa559b7da993a65bed4520d71aeeb48cb7aa89cc976acea5399c720e113ee61460817d42301e1cc039176e83359e565d93b53140402334610f585985c19889551cef4cd1d16a601f330e293db5332d67d043603b6e7e1d3819e78ec87d3818b237861cc3b742e264e94e9a8d0b1ecb366b5f5f0ce9c80e8a7074b11475c603ff0fdcf122ca1ff52b051a68cac1b9347fabdb1624e19f50962ec1362bd664096796f9c29d4d8a8c4a82ed5f04e264edecba4e9c085a9e9063db9bdf2d2e5ac31b2d765097ef44378c7e8ad856d97375d6ed6ce9479de1df33b5fe3a153266f6a678a3dcf4aae540ebeb968e284908ec8ce3899316d3fdddf4f863aafd2bd368edb3cda8b9a6a3f8eade67d2c08a52c895c96c4d8620bb94208eec6b1af28e37e1433bcd7d6e95e5fe6957d009741d7e2033bf788e280f99ef0044202c4d3a6897b99d74963dd6ebba6824040d165e6aabc964d2d7b556a9976cdd0da0cd8c4220a3a76cb6b55d9c4bd78417d4adcd3c13ff2e67017271cca6c8ee02e3c4f9c0e813f0fec2c3a808a0b0e4ea0fa08155612d971e1b3d38178c843509150c61c13bbe6c48739728ce07ec88f4609049e9b6ca8423974e5b54cbe93c6aaeadd4a19dde5aa74616edfa6c4459e8bc5be5684081e69175c085c1a63e58a84046e82794850cc298ff9de59ab6d4e33d5cb0882b7bbb6cdcb2e0b44d82cc4f159285bd5a9ca26316afb97790aa2f5509600a9c1ee06b2658051407ce6f9b0440d263b1e9aa7f14e6ccca47dbdbe41db0a7ba6cad2ce708a3027840193b5f9d5c24d7f434f34f4a6a97eb5ce6888bcdf8d6f8bdb3e5f5cedfa1dd6eae232a5a3c85e66aaf2c94e7a765df8b16c2259cbaa30236e66e8716bc19a4005cd7c36ce9a4e01242ad51533246e2ce8641fcde2a1814bda08614e15e3930c958932d9d7b3df9ecba39317af0e9e3e978707af8e7e912f9f6fc52add01e46a50a3d219f646bdad5a571a86c27c33db82e79ab9b8a9545ecf38bee982690a5dcf68afb230ceb3869eb168a84a4dcfcd7ab5248b455de364b159928dc9c8a6ad8afecc447a95a982aedbea3c18d2d65f6cd6cba80859a8fd61a916d9a23927e7e5b2309bae2dc3304b97619d15f972a946d3638097d43abb9b58771b7585ada68b750734128cb4f60e40612bc3612d43534ba3cf81601c0b95c343800d9e1fd9e7f140012c84806fb03671925bf4730fd020d7a32ee6fb98b3182a18b80803d06942b91b724c5d5f538a050e35c564e4a18b2da3bea5cbb1fe3d7b6cbc8f8cb7f402e17c9877fd0ff2ee4d3afb1876fa0719e5495e01549e356987f7479bb5ca4bd0e49dc3ef47e77f3ef92ff3090e2baa8bf355bf5c400fcc36b11fd767cb2021f90a476c509131695cd5fddaacced4a25cf7cb75a4739a45b44b562b9daa343d0f891f6d36ab222a4cc1ca94ae972425fe226f8a344d5977a6d467e013cb1d2a2a2cecea188eb7b28161e7113d1e916a9bee581b284c79d9878d9d9665991d60eba6ab94ed9292063275a5607e728046c36f87f1383e3fe68c5887764cc5bd137ba8cf8fe098e7f8908c5de53d2c201fbec15d16ece7ba059ff2a3fb6abdbfdf5b02616c4e2c8d10faf9fd0e30f2403716f31b4c7ef11afabb5e776f3bdf910b88a0c8c758303823ea3c2a2e09ef3d091e97508f09e1539fb37796dc8eedf5055c1ff1cfe0f5cf5fe087df7cdd433f6e5ee5957ef0eddbbe3e40fedf51d7b11d570e00001001609acfaf97f69cc9bf630a0b746974616e2e6d4c697465688ec484b7fcffffffff017001'
    config = ConfigObj("setting/setting.ini", encoding='UTF8')
    data = bytes.fromhex(hex)
    print(pdd_pb(data, config))

    hex2 = '000a00660000027600000001000000700808120e746974616e2e6d4c69746541636b1801200032146d6f62696c652e79616e676b6564756f2e636f6d4a3f0881f104121332303233303531305f333635383834315f30311a2437623162303934322d373766612d343934302d393533352d35383365633934373664343458f604'
    data2 = bytes.fromhex(hex)
    print(pdd_pb(data2, config))
