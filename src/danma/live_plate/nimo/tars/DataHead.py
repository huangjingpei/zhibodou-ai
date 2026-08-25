"""
@FileName：DataHead.py
@Description：个人开发者
@Author：秋恋猫
@Time：2024/2/1/001 12:13
@Website：www.qiulianmao.com
@Copyright：©2022-2024 秋恋猫
"""
import struct


class DataHead:
    EN_INT8 = 0
    EN_INT16 = 1
    EN_INT32 = 2
    EN_INT64 = 3
    EN_FLOAT = 4
    EN_DOUBLE = 5
    EN_STRING1 = 6
    EN_STRING4 = 7
    EN_MAP = 8
    EN_LIST = 9
    EN_STRUCTBEGIN = 10
    EN_STRUCTEND = 11
    EN_ZERO = 12
    EN_BYTES = 13

    @staticmethod
    def writeTo(buff, tag, vtype):
        if tag < 15:
            helper = (tag << 4) | vtype
            buff.writeBuf(struct.pack('!B', helper))
        else:
            helper = (0xF0 | vtype) << 8 | tag
            buff.writeBuf(struct.pack('!H', helper))
