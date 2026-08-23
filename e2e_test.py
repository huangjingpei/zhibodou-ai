"""Definitive E2E test: every step verified via dump. ASCII only (no clipper on this phone)."""
import subprocess, time, re

def sh(args, timeout=5):
    return subprocess.run(["adb", "shell"] + args, capture_output=True, timeout=timeout)

def dump():
    sh(["uiautomator", "dump", "/sdcard/_e2e.xml"])
    r = sh(["cat", "/sdcard/_e2e.xml"])
    return r.stdout.decode("utf-8", errors="ignore")

def node_text(xml, rid):
    """返回 resource-id 节点的 text 属性"""
    m = re.search(r'resource-id="' + re.escape(rid) + r'"[^>]*?text="([^"]*)"', xml)
    if not m:  # 属性顺序可能 text 在前
        m = re.search(r'text="([^"]*)"[^>]*?resource-id="' + re.escape(rid) + r'"', xml)
    return m.group(1) if m else None

def node_bounds(xml, rid):
    m = re.search(r'resource-id="' + re.escape(rid) + r'"', xml)
    if not m: return None
    seg = xml[m.start():m.start()+400]
    mb = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', seg)
    return tuple(map(int, mb.groups())) if mb else None

def bounds_center(b):
    return ((b[0]+b[2])//2, (b[1]+b[3])//2) if b else None

INPUT_ID = "com.larus.nova:id/input_text"
SEND_ID  = "com.larus.nova:id/action_send"

print("STEP 0: 当前状态")
xml = dump()
print(f"  input_text 存在: {node_bounds(xml, INPUT_ID) is not None}")
print(f"  input_text.text: {node_text(xml, INPUT_ID)!r}")
vm = re.search(r'text="(按住说话)"', xml)
print(f"  语音模式(按住说话): {bool(vm)}")

# 如果在语音模式，点 action_input(文本输入) 切换到文字模式
VOICE_TOGGLE_ID = "com.larus.nova:id/action_input"
if not node_bounds(xml, INPUT_ID):
    tb = node_bounds(xml, VOICE_TOGGLE_ID)
    if tb:
        cx, cy = bounds_center(tb)
        print(f"  -> 点击 文本输入切换按钮({cx},{cy})")
        sh(["input", "tap", str(cx), str(cy)])
        time.sleep(1.0)
        xml = dump()
        print(f"  切换后 input_text 存在: {node_bounds(xml, INPUT_ID) is not None}")
    else:
        print("  -> 没找到语音/文字切换按钮，也没找到输入框")

print()
print("STEP 1: 点击输入框")
b = node_bounds(xml, INPUT_ID)
assert b, "input_text 不存在，无法继续"
sh(["input", "tap", str((b[0]+b[2])//2), str((b[1]+b[3])//2)])
time.sleep(0.8)

print("STEP 2: input text 输入 ASCII 文字 E2ESEND123")
sh(["input", "text", "E2ESEND123"])
time.sleep(0.8)
xml = dump()
t = node_text(xml, INPUT_ID)
print(f"  输入框内容: {t!r}")
assert t == "E2ESEND123", f"输入失败，得到 {t!r}"

print("STEP 3: 查找 action_send")
sb = node_bounds(xml, SEND_ID)
print(f"  action_send bounds: {sb}")
assert sb, "有文字但 action_send 未出现！"

print("STEP 4: 点击 action_send 中心点")
cx, cy = bounds_center(sb)
print(f"  tap ({cx},{cy})")
sh(["input", "tap", str(cx), str(cy)])
time.sleep(1.5)

print("STEP 5: 验证发送结果")
xml = dump()
t_after = node_text(xml, INPUT_ID)
print(f"  发送后输入框内容: {t_after!r} (空或占位符=已清空)")
msg_found = re.search(r'text="E2ESEND123"', xml)
print(f"  对话中出现 E2ESEND123: {bool(msg_found)}")
send_gone = node_bounds(xml, SEND_ID) is None
print(f"  action_send 已消失: {send_gone}")

print()
if msg_found and send_gone:
    print("*** 结论: action_send 点击发送链路完全正常! 之前失败纯粹是文字没进输入框(clipper缺失) ***")
elif t_after in ("", "发消息或按住说话...", None):
    print("*** 输入框已清空但消息未在可见区域找到(可能被AI回复顶走),再翻一下验证 ***")
else:
    print("*** 发送仍失败, 需进一步排查 ***")
