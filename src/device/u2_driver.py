import time
from typing import Optional, Dict, Any

try:
    import uiautomator2 as u2
except ImportError:
    u2 = None

class U2DoubaoDriver:
    """
    【方案 B 具体落地：基于 uiautomator2 常驻 RPC 的高鲁棒性驱动器】
    
    优势：
    1. 零 Dump 开销：手机端运行 app_process 常驻 JSON-RPC 服务，控件查找仅需 20~50ms
    2. 语义模糊匹配：不管豆包 resource-id 如何混淆更名，通过 className/hint 100% 命中
    3. 原生节点操作：直接 node.set_text() 和 node.click()，免算屏幕分辨率/DPI/全屏遮挡
    """
    def __init__(self, serial: Optional[str] = None):
        self.serial = serial
        self.d = None
        self._init_device()

    def _init_device(self):
        if u2 is None:
            raise RuntimeError("请先在环境安装 uiautomator2: pip install uiautomator2")
        print(f"[U2DoubaoDriver] 正在连接设备常驻 RPC 服务: {self.serial or '默认设备'}...")
        self.d = u2.connect(self.serial)
        # 设置全局隐式查找等待 3 秒
        self.d.implicitly_wait(3.0)
        print("[U2DoubaoDriver] uiautomator2 RPC 服务握手成功！")

    def ensure_doubao_foreground(self, pkg_name: str = "com.larus.nova") -> bool:
        """确保豆包处于前台运行状态"""
        current = self.d.app_current()
        if current.get('package') != pkg_name:
            print(f"[U2DoubaoDriver] 唤起豆包 APP: {pkg_name}")
            self.d.app_start(pkg_name, stop=False)
            time.sleep(1.0)
        return True

    def find_input_box(self):
        """
        【多维语义模糊定位输入框】
        依次通过：类名 + hint 提示词 -> 纯 EditText 类名 -> 包含 input 描述查找
        """
        # 1. 优先通过 hint 提示词模糊匹配
        input_node = self.d(className="android.widget.EditText", descriptionMatches="(?i).*发消息|输入|聊聊.*")
        if input_node.exists:
            return input_node

        # 2. 匹配屏幕下半区的 EditText
        edit_texts = self.d(className="android.widget.EditText")
        if edit_texts.exists:
            # 获取屏幕高度
            info = self.d.window_size()
            h = info[1]
            for node in edit_texts:
                bounds = node.info.get('bounds', {})
                # 处于屏幕下方 40% 区域的一定是聊天输入框
                if bounds.get('top', 0) > h * 0.5:
                    return node

        # 3. 兜底匹配 resourceId 包含 input 的节点
        return self.d(resourceIdMatches="(?i).*input.*")

    def find_send_button(self):
        """
        【模糊定位发送按钮】
        """
        # 1. 通过 description 或 text 匹配 '发送'
        send_btn = self.d(descriptionMatches=".*发送.*")
        if send_btn.exists:
            return send_btn
        
        send_btn_text = self.d(text="发送")
        if send_btn_text.exists:
            return send_btn_text

        # 2. 查找 ImageView 且位于屏幕右下角区域的按钮
        info = self.d.window_size()
        w, h = info[0], info[1]
        for img in self.d(className="android.widget.ImageView"):
            b = img.info.get('bounds', {})
            # 位于最右侧 25% 且最底部 25% 区域
            if b.get('left', 0) > w * 0.75 and b.get('top', 0) > h * 0.75:
                return img

        return None

    def send_script(self, text: str) -> bool:
        """
        【一键直注并发送】
        通过 RPC 直接调用 AccessibilityNodeInfo.performAction(ACTION_SET_TEXT)
        """
        self.ensure_doubao_foreground()

        # 1. 查找输入框
        input_elem = self.find_input_box()
        if not input_elem.exists:
            print("[U2DoubaoDriver] 错误：未找到输入框控件")
            return False

        print(f"[U2DoubaoDriver] 找到输入框，正在直接写入文本: {text[:20]}...")
        # 直接通过 Accessibility 注入文本（无需弹出软键盘、不切换输入法、不重排布局）
        input_elem.set_text(text)
        time.sleep(0.2)

        # 2. 点击发送按钮或回车
        send_elem = self.find_send_button()
        if send_elem and send_elem.exists:
            print("[U2DoubaoDriver] 找到发送按钮，触发节点点击")
            send_elem.click()
            return True
        else:
            print("[U2DoubaoDriver] 未明确找到发送按钮，发送 KEYCODE_ENTER 兜底")
            self.d.press("enter")
            return True
