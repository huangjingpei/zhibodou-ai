# ====================== Windows 原生 API：解决投屏窗口可拖动/嵌入问题 ======================
# 封装 ctypes 调用 user32，实现把 scrcpy 窗口「塞进」程序 GUI 并锁死样式/尺寸。
import ctypes
import ctypes.wintypes as wintypes

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

HWND = wintypes.HWND

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

user32.SetParent.argtypes = [HWND, HWND]
user32.MoveWindow.argtypes = [HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.BOOL]


def get_tk_widget_hwnd(widget):
    """取 Tk 控件的 Windows 句柄。"""
    return int(widget.winfo_id())


def real_embed_window(child_hwnd, parent_hwnd, x, y, w, h):
    """把子窗口（scrcpy）嵌入父窗口（Tk 容器），去标题栏/边框并定位。"""
    user32.SetParent(child_hwnd, parent_hwnd)
    style = user32.GetWindowLongW(child_hwnd, GWL_STYLE)
    style = style & (~WS_CAPTION) & (~WS_THICKFRAME) & (~WS_SYSMENU)
    user32.SetWindowLongW(child_hwnd, GWL_STYLE, style)
    ex_style = user32.GetWindowLongW(child_hwnd, GWL_EXSTYLE)
    ex_style = ex_style | WS_EX_TRANSPARENT
    user32.SetWindowLongW(child_hwnd, GWL_EXSTYLE, ex_style)
    user32.MoveWindow(child_hwnd, x, y, w, h, True)


def find_scrcpy_main_hwnd():
    """在所有窗口里找标题为 'scrcpy' 的主窗口句柄（pygetwindow 懒加载）。"""
    import pygetwindow as gw
    for win in gw.getAllWindows():
        if win.title.strip() == "scrcpy":
            return win._hWnd
    return 0


def get_hwnd_rect(hwnd):
    """返回窗口 (left, top, width, height)。"""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    left = rect.left
    top = rect.top
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return left, top, width, height
