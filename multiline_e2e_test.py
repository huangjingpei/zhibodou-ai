# -*- coding: utf-8 -*-
"""多行中文话术端到端测试：使用修复后的 zhibodou_full.py 真实函数
验证：clipper(text)写入 → 粘贴 → 多行撑高 → ElementTree定位send(排除full_screen) → 点击 → 消息真发出"""
import sys, types, time

# stub GUI 依赖，只加载 ADB/定位函数
for mod in ['tkinter','tkinter.ttk','tkinter.scrolledtext','tkinter.messagebox','tkinter.simpledialog',
            'pyautogui','pyttsx3','websocket','pyperclip','winsound']:
    sys.modules[mod] = types.ModuleType(mod)
sys.modules['tkinter'].END = 'end'

src = open(r'C:\Users\Administrator\WorkBuddy\zhibodou\zhibodou_full.py', encoding='utf-8').read()
end_idx = src.find('# ===================== Windows原生API')
exec(compile(src[:end_idx], 'zb', 'exec'), globals())

# 若误入了全屏输入页，先退出
xml = _dump_ui_xml()
import re
if xml and '全屏' in xml and not _find_id_bounds(xml, DOUBAO_SEND_ID):
    subprocess.run(['adb','shell','input','keyevent','4'], capture_output=True)
    time.sleep(1.0)
    print('[预备] 从全屏输入页退出')

print('='*60)
print('STEP 1: 清空输入框草稿')
xml = _dump_ui_xml()
pt = _bounds_center(_find_id_bounds(xml, DOUBAO_INPUT_ID))
if pt:
    adb_tap(*pt); time.sleep(0.6)
    for _ in range(50):
        subprocess.run(['adb','shell','input','keyevent','67'], capture_output=True)
    time.sleep(0.4)
xml = _dump_ui_xml()
print('  清空后输入框:', repr(_find_node_text(xml, DOUBAO_INPUT_ID)[:30]))

print('='*60)
print('STEP 2: 多行中文话术写入剪贴板（含换行符，最贴近真实直播话术）')
ML = '家人们晚上好呀！\n今晚给大家带来的是阿克苏冰糖心苹果，产地直发，脆甜多汁，福利价只要五块九一斤，\n喜欢的家人们赶紧点击下方小黄车下单，数量有限先到先得，拍完记得回来扣个已拍！'
adb_set_phone_clipboard(ML)
time.sleep(0.4)

print('='*60)
print('STEP 3: 点输入框 + 粘贴')
ok = tap_input_box()
print(f'  tap_input_box: {ok}')
time.sleep(0.35)
adb_phone_paste()
time.sleep(1.2)  # 等多行撑高动画稳定

xml = _dump_ui_xml()
t = _find_node_text(xml, DOUBAO_INPUT_ID)
print(f'  粘贴后输入框: {t[:40]!r}... (len={len(t or "")})')
print(f'  多行撑高验证: input bounds={_find_id_bounds(xml, DOUBAO_INPUT_ID)}')

print('='*60)
print('STEP 4: 定位发送按钮（核心验证：必须排除 full_screen）')
xml = _dump_ui_xml()
send_b = _find_id_bounds(xml, DOUBAO_SEND_ID)
fs_b   = _find_id_bounds(xml, DOUBAO_FULLSCREEN_ID)
print(f'  action_send bounds:      {send_b}')
print(f'  action_full_screen bounds: {fs_b}')
if send_b and fs_b:
    sc = _bounds_center(send_b)
    fx1, fy1, fx2, fy2 = fs_b
    inside = fx1 <= sc[0] <= fx2 and fy1 <= sc[1] <= fy2
    print(f'  send 中心 {sc} 是否落入 full_screen 矩形: {inside}（必须为 False）')

print('='*60)
print('STEP 5: 用修复后的 tap_send_button() 真实发送')
ok = tap_send_button()
print(f'  tap_send_button: {ok}')
time.sleep(2.5)

print('='*60)
print('STEP 6: 验证消息真的发出去了')
xml = _dump_ui_xml()
t = _find_node_text(xml, DOUBAO_INPUT_ID)
print(f'  发送后输入框: {t[:30]!r}（应为空或占位符=发送成功）')
send_gone = _find_id_bounds(xml, DOUBAO_SEND_ID) is None
print(f'  action_send 已消失: {send_gone}')
# 消息本体可能被AI回复顶出可视区，用输入框清空+按钮消失双重判断
in_fs = _find_id_bounds(xml, DOUBAO_FULLSCREEN_ID) is not None
print(f'  是否误入全屏输入页: {in_fs}（应为 False）')

found = False
if xml:
    for kw in ['家人们晚上好', '冰糖心', '五块九']:
        if kw in xml:
            found = True
            print(f'  消息片段[{kw}]在屏幕可见区: True')
cleared = (not t) or t.startswith('发消息')
print(f'  结论: 输入框已清空={cleared}, 发送键消失={send_gone}, 未误入全屏={not in_fs}')
