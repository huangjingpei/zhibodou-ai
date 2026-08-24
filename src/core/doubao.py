# ====================== 豆包 APP 控件锚点（uiautomator 实测 2026-08-23） ======================
# input_text:       输入框（仅文字模式存在）
# action_send:      发送按钮（仅输入框有文字时出现）
# action_input:     语音→文字切换按钮(desc=文本输入)。语音模式下 input_text 不存在，须先点它！
# action_full_screen: 全屏输入按钮——多行文本把输入框撑高时出现在 action_send 正上方！
#   实测 bounds=[925,1979][1047,2128]，与 action_send [925,2124][1047,2265] x 完全重叠、上下紧贴。
#   绝不能点击 y<2128 的右侧区域，否则会误入全屏输入页！
DOUBAO_INPUT_ID        = "com.larus.nova:id/input_text"
DOUBAO_SEND_ID         = "com.larus.nova:id/action_send"
DOUBAO_FULLSCREEN_ID   = "com.larus.nova:id/action_full_screen"
DOUBAO_VOICE_TOGGLE_ID = "com.larus.nova:id/action_input"
DOUBAO_PKG             = "com.larus.nova"

# =====================【警告：已废弃硬编码兜底坐标】=====================================
# 旧兜底 (980,2120) 在多行文本模式下正好落在 action_full_screen 按钮内，导致误点进
# 全屏输入页！定位失败的正确做法是报错重试，而不是点一个可能过期的坐标。
# ==========================================================================================
