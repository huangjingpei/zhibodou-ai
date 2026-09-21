# ====================== PDK 登录账号本地记忆 ======================
# 需求：用户在登录窗口输入过一次手机号/密码（含激活页卡密）后，写入本地
# 配置文件；下次启动客户端自动回填，无需再次输入。
#
# 存储位置（复用 core.paths 的目录解析，与 config.json 同源）：
#   · 源码运行   —— src/data/pdk_login.json
#   · 冻结 exe   —— exe 同级 data/pdk_login.json
#
# 安全说明：password / card_key 仅做 base64 混淆（防肉眼直读、防 shoulder
# surfing），并非加密。文件与 src/data/license.json 一样属于本机敏感数据，
# 已加入 .gitignore，绝不能提交到版本库。
import base64
import json
import os
import threading

from core.paths import DATA_DIR

CRED_FILE = os.path.join(DATA_DIR, "pdk_login.json")

_lock = threading.Lock()


def _encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _decode(text: str) -> str:
    try:
        return base64.b64decode(text.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def load() -> dict:
    """读取已保存的登录凭据。

    返回 {"phone": str, "password": str, "card_key": str}；
    文件不存在 / 损坏 / 字段缺失时对应值为空字符串，绝不抛异常。
    """
    out = {"phone": "", "password": "", "card_key": ""}
    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            out["phone"] = str(data.get("phone") or "").strip()
            out["password"] = _decode(str(data.get("password_b64") or ""))
            out["card_key"] = _decode(str(data.get("card_key_b64") or ""))
    except Exception:
        pass
    return out


def save(phone: str, password: str, card_key: str = "") -> bool:
    """登录/激活成功后保存凭据；失败静默（不阻塞登录流程）。"""
    try:
        payload = {
            "phone": str(phone or "").strip(),
            "password_b64": _encode(str(password or "")),
            "card_key_b64": _encode(str(card_key or "")),
            "saved_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        }
        tmp = CRED_FILE + ".tmp"
        with _lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CRED_FILE)   # 原子替换，避免写一半被读到
        return True
    except Exception:
        return False


def clear() -> None:
    """清除记住的凭据（例如用户主动退出登录时可调用）。"""
    try:
        if os.path.exists(CRED_FILE):
            os.remove(CRED_FILE)
    except Exception:
        pass
