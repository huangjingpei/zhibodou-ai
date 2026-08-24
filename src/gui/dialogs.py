# ====================== 密码 / 授权弹窗 ======================
import tkinter.simpledialog as simpledialog
import tkinter.messagebox as messagebox
from settings import auth
def dialog_modify_pwd():
    """验证旧密码 -> 输入两次新密码 -> 修改。"""
    old = simpledialog.askstring("验证旧密码", "请输入管理员旧密码", show="*")
    if old is None:
        return
    if not auth.verify_admin_pwd(old):
        messagebox.showerror("错误", "旧密码不正确")
        return
    new1 = simpledialog.askstring("设置新密码", "请输入新密码", show="*")
    if new1 is None:
        return
    new2 = simpledialog.askstring("确认新密码", "再次输入新密码", show="*")
    if new1 != new2:
        messagebox.showerror("错误", "两次密码不一致")
        return
    if auth.change_admin_password(old, new1):
        messagebox.showinfo("成功", "密码修改成功")
    else:
        messagebox.showerror("错误", "修改失败")


def dialog_auth_mgr():
    """授权管理器（当前测试版仅保留入口）。"""
    messagebox.showinfo("提示", "当前测试版本，授权管理器仅保留入口，无需激活")
