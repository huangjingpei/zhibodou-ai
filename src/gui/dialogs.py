# ====================== PDK 账户 / 授权弹窗 ======================
import tkinter.messagebox as messagebox
from pdk import auth_service as pdk_auth


def dialog_pdk_profile():
    """显示已由服务端校验的账户资料，不展示 Token 或完整设备 ID。"""
    result = pdk_auth.current_auth()
    if result is None:
        messagebox.showerror("PDK 账户", "当前没有有效 PDK 会话，请重新登录")
        return
    messagebox.showinfo(
        "PDK 账户资料",
        "手机号：%s\n业务：%s\n授权模式：%s\n状态：%s\n剩余次数：%s" % (
            result.masked_phone,
            result.business.get("bizCode") or result.session.get("bizCode") or "-",
            result.authorization_mode or "-",
            result.status,
            result.remaining_calls,
        ),
    )


def dialog_pdk_license():
    """显示当前设备许可证摘要。"""
    result = pdk_auth.current_auth()
    if result is None:
        messagebox.showerror("设备许可证", "当前没有有效 PDK 会话，请重新登录")
        return
    if result.authorization_mode != "DEVICE_LICENSE":
        messagebox.showinfo(
            "设备许可证",
            "当前业务授权模式为 %s，不使用设备许可证。" % (result.authorization_mode or "未知"),
        )
        return
    messagebox.showinfo(
        "设备许可证",
        "状态：%s\n到期时间：%s\n设备：当前登录设备" % (
            result.status,
            result.expire_at or "未返回",
        ),
    )
