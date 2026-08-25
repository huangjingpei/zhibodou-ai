"""
@FileName：BinBuffer.py
@Description：个人开发者
@Author：秋恋猫
@Time：2024/2/1/001 02:12
@Website：www.qiulianmao.com
@Copyright：©2022-2024 秋恋猫
"""


class BinBuffer:
    def __init__(self, buff=bytes()):
        self.buffer = buff
        self.position = 0

    def writeBuf(self, buff):
        self.buffer += buff

    def getBuffer(self):
        return self.buffer

    def length(self):
        return len(self.buffer)
