# ====================== 授权 / 管理员密码系统 ======================
# 机器码绑定、授权校验、管理员密码的增改与校验。纯文件操作，不依赖 GUI。
import hashlib
import os
from core.paths import AUTH_FILE, PWD_FILE, EXPIRE_FILE

SECRET_SALT = "ZhangAiChenZhiBoDou2026"
DEFAULT_ADMIN_PWD = "aichen888"


def get_machine_code():
    """根据 CPU + MAC + 盐生成机器码（md5）。"""
    import platform
    import uuid
    cpu = platform.processor()
    mac = hex(uuid.getnode())
    raw = f"{cpu}{mac}{SECRET_SALT}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def check_machine_auth():
    """PDK 会话、业务状态和许可证均校验成功后才通过。"""
    try:
        from pdk import auth_service
        return auth_service.is_authenticated()
    except Exception:
        return False


def save_machine_bind():
    """将机器码签名写入授权文件。"""
    mc = get_machine_code()
    key = hashlib.sha256((mc + SECRET_SALT).encode("utf-8")).hexdigest()
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        f.write(key)
    return True


def get_auth_remain_sec():
    """返回 (剩余秒数, 是否过期)。当前测试版：极大值 / 未过期。"""
    return 99999999, False


def check_cannot_power_on():
    """没有有效 PDK 登录态时禁止启动直播链路。"""
    return not check_machine_auth()


def init_admin_password():
    """首次运行初始化管理员密码文件（md5 存储，不存明文）。"""
    if not os.path.exists(PWD_FILE):
        md5_val = hashlib.md5(DEFAULT_ADMIN_PWD.encode("utf-8")).hexdigest()
        with open(PWD_FILE, "w") as f:
            f.write(md5_val)


def verify_admin_pwd(input_pwd):
    """校验管理员密码。"""
    if not os.path.exists(PWD_FILE):
        return False
    with open(PWD_FILE, "r") as f:
        saved = f.read().strip()
    return hashlib.md5(input_pwd.encode("utf-8")).hexdigest() == saved


def change_admin_password(old_pwd, new_pwd):
    """先验证旧密码，再写入新密码 md5。"""
    if not verify_admin_pwd(old_pwd):
        return False
    new_md5 = hashlib.md5(new_pwd.encode("utf-8")).hexdigest()
    with open(PWD_FILE, "w") as f:
        f.write(new_md5)
    return True
