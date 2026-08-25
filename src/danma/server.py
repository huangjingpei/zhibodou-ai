"""
@FileName：server.py
@Description：个人开发者
@Author：秋恋猫
@Time：2024/10/21/周一 20:44
@Website：www.qiulianmao.com
@Copyright：©2022-2024 秋恋猫
"""
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.route('/biz/danmaku/live/msg', methods=['POST'])
def handle_message():
    # 获取 JSON 数据
    data = request.get_json()

    # 打印接收到的数据
    print("收到的消息:", data)

    # 处理逻辑（这里可以添加你自己的逻辑）
    response_message = {
        "status": "success",
        "message": "消息已接收",
        "received_data": data
    }

    # 返回 JSON 响应
    return jsonify(response_message), 200


if __name__ == "__main__":
    app.run(host='127.0.0.1', port=7979)
