# -*- coding: utf-8 -*-
"""发送机制对照实验：
A. keyevent 66 (ENTER) 是否能发送
B. uiautomator 控件定位 + input tap 是否能发送
每步都带 dump 验证。
"""
import subprocess, time, re
import xml.etree.ElementTree as ET
import io

INPUT_ID = "com.larus.nova:id/input_text"
SEND_ID  = "com.larus.nova:id/action_send"
FS_ID    = "com.larus.nova:id/action_full_screen"
TOGGLE_ID= "com.larus.nova:id/action_input"

def sh(*args, timeout=12):
    return subprocess.run(["adb", "shell"] + list(args),
                          capture_output=True, timeout=timeout)

def dump():
    for _ in range(3):
        try:
            sh("uiautomator", "dump", "/sdcard/_exp.xml")
            raw = sh("cat", "/sdcard/_exp.xml").stdout.decode("utf-8", "ignore")
            if "<hierarchy" in raw:
                return raw
        except Exception:
            pass
        time.sleep(1.5)
    return ""

def nodes(xml):
    try:
        root = ET.parse(io.StringIO(xml)).getroot()
        return list(root.iter("node"))
    except Exception:
        return []

def find_node(xml, rid):
    for n in nodes(xml):
        if n.get("resource-id") == rid:
            return n
    return None

def bounds_of(n):
    if n is None: return None
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds", ""))
    return tuple(map(int, m.groups())) if m else None

def input_text_now(xml):
    n = find_node(xml, INPUT_ID)
    return n.get("text", "") if n is not None else None

def ensure_text_mode():
    xml = dump()
    if find_node(xml, INPUT_ID) is None:
        t = find_node(xml, TOGGLE_ID)
        b = bounds_of(t)
        if b:
            x, y = (b[0]+b[2])//2, (b[1]+b[3])//2
            sh("input", "tap", str(x), str(y))
            time.sleep(1.0)
            xml = dump()
    return xml

def clear_input():
    """聚焦输入框并清空"""
    xml = dump()
    n = find_node(xml, INPUT_ID)
    b = bounds_of(n)
    if b:
        sh("input", "tap", str((b[0]+b[2])//2), str((b[1]+b[3])//2))
        time.sleep(0.5)
    # 全选删除：keycombination 可能不支持，退格连发兜底
    for _ in range(50):
        sh("input", "keyevent", "67")
    time.sleep(0.4)
    t = input_text_now(dump())
    return (t is None) or (t == "") or t.startswith("发消息")

print("=" * 50)
print("步骤0: 确保文字模式 + 输入框清空")
ensure_text_mode()
print(f"  输入框已清空: {clear_input()}")

# ---------- 实验 A: 回车键发送 ----------
print()
print("=" * 50)
print("实验A: input text 灌入 ASCII 后按 keyevent 66 (ENTER)")
sh("input", "text", "ENTERTEST01")
time.sleep(0.8)
xml = dump()
t = input_text_now(xml)
send_node = find_node(xml, SEND_ID)
print(f"  灌入后输入框: {t!r}")
print(f"  action_send 存在: {send_node is not None}, bounds={bounds_of(send_node)}")

print("  -> 按下 ENTER (keyevent 66)")
sh("input", "keyevent", "66")
time.sleep(1.5)
xml = dump()
t2 = input_text_now(xml)
send_gone = find_node(xml, SEND_ID) is None
print(f"  按下后输入框: {t2!r}")
print(f"  action_send 消失: {send_gone}")
msg_sent = "ENTERTEST01" in xml
print(f"  消息出现在控件树: {msg_sent}")
print(f"  >>> 实验A结论: {'ENTER 能发送' if ((not t2 or t2=='' or t2.startswith('发消息')) and send_gone) else 'ENTER 不能发送(或需组合判定)'}")

# ---------- 实验 B: 控件定位点击发送 ----------
print()
print("=" * 50)
print("实验B: input text 灌入后, 控件定位 action_send 点击")
sh("input", "text", "TAPTEST02")
time.sleep(0.8)
xml = dump()
t = input_text_now(xml)
send_node = find_node(xml, SEND_ID)
fs_node = find_node(xml, FS_ID)
sb = bounds_of(send_node)
fb = bounds_of(fs_node)
print(f"  灌入后输入框: {t!r}")
print(f"  action_send: bounds={sb} clickable={send_node.get('clickable') if send_node is not None else '-'}")
print(f"  action_full_screen: bounds={fb} clickable={fs_node.get('clickable') if fs_node is not None else '-'}")

if sb:
    cx, cy = (sb[0]+sb[2])//2, (sb[1]+sb[3])//2
    # 保险：确认点击点在 send 区域内且不在 fullscreen 区域内
    in_fs = fb and (fb[0] <= cx <= fb[2] and fb[1] <= cy <= fb[3])
    print(f"  点击点 ({cx},{cy}) 是否落入 fullscreen 区域: {bool(in_fs)}")
    print(f"  -> 点击 action_send 中心")
    sh("input", "tap", str(cx), str(cy))
    time.sleep(1.5)
    xml = dump()
    t2 = input_text_now(xml)
    send_gone = find_node(xml, SEND_ID) is None
    print(f"  点击后输入框: {t2!r}")
    print(f"  action_send 消失: {send_gone}")
    print(f"  消息出现在控件树: {'TAPTEST02' in xml}")
else:
    print("  未找到 action_send, 实验B无法进行")

print()
print("=" * 50)
print("最终: 截图留证")
subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=open(r"C:\Users\Administrator\WorkBuddy\zhibodou\exp_send_result.png", "wb"))
print("done")
