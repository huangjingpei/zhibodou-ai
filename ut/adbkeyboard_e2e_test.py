# -*- coding: utf-8 -*-
"""新发送链路 E2E 测试：
1. 文字模式确保
2. 控件定位聚焦输入框 + 清空
3. ADBKeyboard (ADB_INPUT_B64) 直接输入中文多行话术——彻底绕开剪贴板
4. 控件树定位 action_send（校验点击点不在全屏按钮内）点击
5. 发送后验证：输入框清空 + action_send 消失 + 消息出现在对话
"""
import subprocess, time, re, base64, os

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADB = os.path.join(PROJ_ROOT, "scrcpy", "adb.exe")
UT_DIR = os.path.dirname(os.path.abspath(__file__))
import xml.etree.ElementTree as ET
import io

INPUT_ID = "com.larus.nova:id/input_text"
SEND_ID  = "com.larus.nova:id/action_send"
FS_ID    = "com.larus.nova:id/action_full_screen"
TOGGLE_ID= "com.larus.nova:id/action_input"

CN_TEXT = "家人们晚上好！\n今晚福利价只要5.9一斤，\n库存不多先到先得，\n喜欢的主播点点关注！"

def sh(*args, timeout=12):
    return subprocess.run([ADB, "shell"] + list(args),
                          capture_output=True, timeout=timeout)

def dump():
    for _ in range(3):
        try:
            sh("uiautomator", "dump", "/sdcard/_e2e2.xml")
            raw = sh("cat", "/sdcard/_e2e2.xml").stdout.decode("utf-8", "ignore")
            if "<hierarchy" in raw:
                return raw
        except Exception:
            pass
        time.sleep(1.5)
    return ""

def node_of(xml, rid, clickable_only=False):
    if not xml: return None
    try:
        root = ET.parse(io.StringIO(xml)).getroot()
    except Exception:
        return None
    for n in root.iter("node"):
        if n.get("resource-id") == rid:
            if clickable_only and n.get("clickable") != "true":
                continue
            return n
    return None

def bounds_of(n):
    if n is None: return None
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds", ""))
    return tuple(map(int, m.groups())) if m else None

def input_text_now():
    n = node_of(dump(), INPUT_ID)
    return n.get("text", "") if n is not None else None

def is_empty(t):
    return (t is None) or (t == "") or ("发消息" in t)

print("步骤1: 确保文字模式")
xml = dump()
if node_of(xml, INPUT_ID) is None:
    b = bounds_of(node_of(xml, TOGGLE_ID))
    if b:
        sh("input", "tap", str((b[0]+b[2])//2), str((b[1]+b[3])//2))
        time.sleep(1.0)
xml = dump()
print(f"  input_text 存在: {node_of(xml, INPUT_ID) is not None}")

print("步骤2: 控件定位聚焦输入框 + 清空")
n = node_of(xml, INPUT_ID)
b = bounds_of(n)
sh("input", "tap", str((b[0]+b[2])//2), str((b[1]+b[3])//2))
time.sleep(0.6)
# 全选删除（Ctrl+A = keycombination 113 29; 退格 = 67）
sh("input", "keycombination", "113", "29")
time.sleep(0.3)
sh("input", "keyevent", "67")
time.sleep(0.4)
t = input_text_now()
if not is_empty(t):
    # 兜底：退格连发
    for _ in range(60):
        sh("input", "keyevent", "67")
    time.sleep(0.4)
    t = input_text_now()
print(f"  清空后输入框: {t!r} -> 已清空: {is_empty(t)}")

print("步骤3: ADBKeyboard 输入中文多行话术 (ADB_INPUT_B64)")
b64 = base64.b64encode(CN_TEXT.encode("utf-8")).decode("ascii")
r = sh("am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64)
out = r.stdout.decode("utf-8", "ignore")
print(f"  广播返回: {out.strip()[-70:]}")
time.sleep(1.0)
t = input_text_now()
ok_cn = (t == CN_TEXT) if t else False
print(f"  输入框内容匹配预期: {ok_cn}")
if t is not None:
    print(f"  (长度: 期望{len(CN_TEXT)} 实际{len(t)})")

print("步骤4: 控件定位点击 action_send")
xml = dump()
send_n = node_of(xml, SEND_ID, clickable_only=True)
fs_b = bounds_of(node_of(xml, FS_ID))
sb = bounds_of(send_n)
print(f"  action_send bounds={sb} fullscreen bounds={fs_b}")
if sb:
    cx = (sb[0] + sb[2]) // 2
    # 点击点向按钮下半部偏移，远离紧贴上沿的全屏按钮
    cy = sb[1] + (sb[3] - sb[1]) * 3 // 4
    in_fs = fs_b and (fs_b[0] <= cx <= fs_b[2] and fs_b[1] <= cy <= fs_b[3])
    in_send = sb[0] <= cx <= sb[2] and sb[1] <= cy <= sb[3]
    print(f"  点击点 ({cx},{cy}) 在send内: {in_send}, 在fullscreen内: {bool(in_fs)}")
    if in_send and not in_fs:
        sh("input", "tap", str(cx), str(cy))
        print("  已点击")
        time.sleep(1.8)
    else:
        print("  点击点校验失败，放弃点击!")
else:
    print("  未找到 action_send!")

print("步骤5: 发送结果验证")
t = input_text_now()
send_gone = node_of(dump(), SEND_ID) is None
print(f"  输入框已清空: {is_empty(t)}")
print(f"  action_send 已消失: {send_gone}")
xml = dump()
found = any(kw in xml for kw in ["家人们晚上好", "福利价只要", "点点关注"])
print(f"  话术出现在对话控件树: {found}")

subprocess.run([ADB, "exec-out", "screencap", "-p"],
               stdout=open(os.path.join(UT_DIR, "adbkeyboard_e2e.png"), "wb"))
print("截图: adbkeyboard_e2e.png")
