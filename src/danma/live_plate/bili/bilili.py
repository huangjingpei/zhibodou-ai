import json
import struct
import urllib.parse
import brotli
from live_plate.Message import CreatChatMessage, CreatMemberMessage, CreatLikeMessage, CreatGiftMessage


def brotli_decode(bytes):
    return brotli.decompress(bytes)


def decode_packet(data):
    u = None
    res = struct.unpack_from('>i', data, 1)[0]
    n = {'body': [], 'packetLen': res}
    wsBinaryHeaderList = [
        {
            "name": "Header Length",
            "key": "headerLen",
            "bytes": 2,
            "offset": 4,
            "value": 16
        },
        {
            "name": "Protocol Version",
            "key": "ver",
            "bytes": 2,
            "offset": 6,
            "value": 1
        },
        {
            "name": "Operation",
            "key": "op",
            "bytes": 4,
            "offset": 8,
            "value": 7
        },
        {
            "name": "Sequence Id",
            "key": "seq",
            "bytes": 4,
            "offset": 12,
            "value": 1
        }
    ]
    for t in wsBinaryHeaderList:
        if t['bytes'] == 4:
            n[t['key']] = struct.unpack_from('>i', data, t['offset'])[0]
        elif t['bytes'] == 2:
            n[t['key']] = struct.unpack_from('>h', data, t['offset'])[0]

    if n['packetLen'] < len(list(data)):
        decode_packet(bytes(list(data)[:n['packetLen']]))
    if n['op'] and n['op'] in (5, 8):
        pass
    if n['op'] == 3:
        n['body'] = {'count': struct.unpack_from('>i', data, 4)[0]}
        return n

    for i in range(0, len(list(data)), n['packetLen']):
        s = struct.unpack_from('>i', data, i)[0]
        a = struct.unpack_from('>h', data, i + 4)[0]
        if n['ver'] == 0:
            try:
                c = bytes(list(data)[i + a:i + s]).decode(encoding='utf-8')
                u = json.loads(c) if c else None

            except Exception as e:
                pass

        elif n['ver'] == 3:
            datas = list(data)[i + a:i + s]
            res = brotli_decode(bytes(datas))
            u = decode_packet(res)['body']

        if u:
            n['body'].append(u)
    res = n['body']

    listmessage = []

    if type(res) == list and len(res) > 0:
        res = res[0]
        if type(res) == list:
            new_li = []
            for i in res:
                if i not in new_li:
                    new_li.append(i)
            for msg in new_li:
                if msg['cmd'] == 'DANMU_MSG':
                    name = msg['info'][2][1]

                    content = msg['info'][1]
                    listmessage.append(CreatChatMessage(name=name, head_image="", content=content))


                elif msg['cmd'] == 'INTERACT_WORD':
                    name = msg['data']['uname']

                    listmessage.append(CreatMemberMessage(name=name, head_image=""))

                elif msg['cmd'] == 'LIKE_INFO_V3_CLICK':
                    name = msg['data']['uname']

                    listmessage.append(CreatLikeMessage(name=name, head_image='', count=1))




                elif msg['cmd'] == 'SEND_GIFT':
                    name = msg['data']['uname']
                    conetnt = '送礼'

                    giftName = msg['data']['giftName']
                    num = msg['data']['num']

                    listmessage.append(CreatGiftMessage(name=name, head_image='', gift_name=giftName, gift_count=num))

                else:
                    print(msg)
    n['listmessage'] = listmessage

    return n


if __name__ == '__main__':

    data = '0000001a0010000100000008000000017b22636f6465223a307d'
    data = bytes.fromhex(data)
    data = b"\x00\x00\x01}\x00\x10\x00\x03\x00\x00\x00\x05\x00\x00\x00\x00\x1b\xd7\x02\x00,\nl\x1b[v^\xed`\xb0\x1d\xb3\xc2\xa3\x98\xe2\xed\xb3\xe9B~\x16\xba\x16\xa8\xa2d\xa2\xa4\xd9\x04Q\x14*-\x03\x94s*\x7fB\xed\x1b''\x9eA\xc2\x08\xb43\x91\xd3\xc3\xc5\xb20\xd8\xd0\xc2S|\xe8\xf4P\x11\xd5\x97\xa1\xcb\xe9\xbf\xfd\xdb\x83\xe1\x8d\xf9s6\x87\xed!\x98H\xc0ii(\x81\x08x\x0eB:\xf9\x9f\x05`\xa0\xe0\x98\xd2?\x88\xd8\x93\xf0\xf9\x81\xcd\x1f\x8f\x98\xfc+tCP[\x97\x1fP\x7fD\xf3? z#\x80\xa3eI?\x82\xf0\xa5qo\xaf\x06*\x86\xf1\xcfp} -\xd3=fZ\x1a\xb0\xf8\x04\xb83\xf6\x0c\x8b@\xc43>\x95\xcf\xae\x99\x08\xd34\xe4/\x9d\xac\xc9\x08\x17\xc1\xdb\nZ\xeeY\xdc\x1c\xc4\xb8\xe6\xce\xfch\xdc\xdb\xb2\\E\xb8\x81\x96!B\xffu\xf6,\xd7\xa5l#|\xa8\x8a\xa7\xeaK\x07s\xbfc\xd3nKU\x05\x91\x04\x17\xe0\xd4=k\xac\x13\xf4w;D\xbat$[\x00jdi:\xf8%\xfa*:4\xd3\xde\xb5>8\x87\xe4M\xd7p\x07\xf4\x142$c\x06u?/`E\x17g\xf9\\0\xe7D\r\x8fT\xd2\xee\xf9$/{FU^\x81\xc6\x9a\x9e2\x0c\x81\x05\xd1\x80\xcd:\xb6\xecm\xfc\xd8\xe1\x93#\xda4\xbd2\x01C\xb2\xe9J.\xcb\x02wz\xec\x08\x02ah\xca\xdb\x92\xd2\xc5\xbb\x82\x14\xda\xf6/\xe3\xe6\xf6\xe6J9,E\xf0\xa3\x8e\x08S\x02"

    res = decode_packet(data)
    print(res)
