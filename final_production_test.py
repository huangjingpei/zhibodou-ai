# -*- coding: utf-8 -*-
"""生产路径最终验证：加载 zhibodou_full.py 中的真实 send_text_to_doubao()，
发送中文话术，验证消息真的进入豆包对话界面。"""
import sys, types, time, re, subprocess

# stub 掉 GUI 依赖，只加载纯逻辑部分
for mod in ['tkinter', 'tkinter.ttk', 'tkinter.scrolledtext', 'tkinter.messagebox',
            'tkinter.simpledialog', 'pyautogui', 'pyttsx3', 'websocket', 'pyperclip',
            'winsound']:
    sys.modules[mod] = types.ModuleType(mod)
sys.modules['tkinter'].END = 'end'

SRC = r'C:\Users\Administrator\WorkBuddy\zhibodou\zhibodou_full.py'
with open(SRC, encoding='utf-8') as f:
    src = f.read()
# 截取到 Windows API 段之前——全部 ADB/uiautomator/发送逻辑都在这一段
cut = src.find('# ===================== Windows原生API')
g = {}
exec(compile(src[:cut], 'zhibodou_full_head', 'exec'), g)

send_text_to_doubao = g['send_text_to_doubao']

MSG = "生产路径最终验证：今晚八点准时开播，整点福利炸不停！"
print(f"发送内容: {MSG}")
print("-" * 46)

t0 = time.time()
ok, err = send_text_to_doubao(MSG)
print(f"send_text_to_doubao 返回: ok={ok}, err={err!r}")
print(f"耗时: {time.time()-t0:.1f}s")
print("-" * 46)

# 独立复核：消息是否真的在豆包对话里
time.sleep(2)
subprocess.run(['adb', 'shell', 'uiautomator', 'dump', '/sdcard/_final.xml'],
               capture_output=True, timeout=15)
xml = subprocess.run(['adb', 'shell', 'cat', '/sdcard/_final.xml'],
                     capture_output=True, timeout=10).stdout.decode('utf-8', 'ignore')
print("独立复核:")
print(f"  消息出现在对话控件树: {'生产路径最终验证' in xml}")
m = re.search(r'resource-id="com.larus.nova:id/input_text"[^>]*?text="([^"]*)"', xml)
print(f"  输入框已清空: {m is None or m.group(1) == '' or '发消息' in m.group(1)}")
print(f"  action_send 已消失: {'action_send' not in xml}")

subprocess.run(['adb', 'exec-out', 'screencap', '-p'],
               stdout=open(r'C:\Users\Administrator\WorkBuddy\zhibodou\final_production_test.png', 'wb'))
print("截图: final_production_test.png")
