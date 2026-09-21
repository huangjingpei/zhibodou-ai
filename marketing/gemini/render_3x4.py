"""
智播豆宣发海报高清矢量渲染引擎 (Posters 04 - 12)
尺寸：896 x 1200 (标准 3:4 比例)
风格：黑曜石演播室控制台、暗黑极简玻璃拟态、青绿发光数据流
"""

import math
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 896, 1200
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "images", "3x4")
os.makedirs(OUT_DIR, exist_ok=True)

FONT_PATH_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_PATH_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_PATH_EN = "C:/Windows/Fonts/segoeuib.ttf"

def get_font(size, bold=False, en=False):
    path = FONT_PATH_EN if en else (FONT_PATH_BOLD if bold else FONT_PATH_REG)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# 基础色板
BG_DARK = (11, 16, 27)
BG_LIGHT = (18, 28, 44)
SURFACE = (19, 28, 45, 230)
SURFACE_BORDER = (34, 49, 71)
CYAN = (34, 211, 238)
EMERALD = (16, 185, 129)
VIOLET = (168, 85, 247)
AMBER = (245, 158, 11)
RED = (244, 63, 94)
WHITE = (248, 250, 252)
TEXT_MUTED = (148, 163, 184)
TEXT_FAINT = (100, 116, 139)

def create_base_canvas(page_num, glow_color=CYAN):
    im = Image.new("RGBA", (W, H), (11, 16, 27, 255))
    draw = ImageDraw.Draw(im)
    
    # 垂直微渐变背景
    for y in range(H):
        t = y / H
        r = int(11 * (1 - t) + 16 * t)
        g = int(16 * (1 - t) + 24 * t)
        b = int(27 * (1 - t) + 38 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
        
    # 背景微科技网格线
    grid_color = (25, 36, 56, 120)
    for x in range(0, W, 48):
        draw.line([(x, 0), (x, H)], fill=grid_color)
    for y in range(0, H, 48):
        draw.line([(0, y), (W, y)], fill=grid_color)
        
    # 顶部品牌条
    draw.rounded_rectangle([48, 38, 240, 72], radius=17, fill=(24, 35, 54, 220), outline=(40, 58, 85))
    draw.ellipse([64, 49, 74, 59], fill=EMERALD)
    draw.text((86, 44), "智播豆 · ZHIBODOU", fill=WHITE, font=get_font(14, bold=True))
    
    # 右侧序号
    draw.rounded_rectangle([W - 140, 38, W - 48, 72], radius=17, fill=(24, 35, 54, 220), outline=(40, 58, 85))
    draw.text((W - 94, 55), f"{page_num:02d} / 12", fill=CYAN, font=get_font(15, bold=True, en=True), anchor="mm")
    
    # 底部说明微文案
    draw.line([(48, H - 56), (W - 48, H - 56)], fill=(30, 44, 66))
    draw.text((48, H - 42), "ZHIBODOU · 全流程 AI 智能直播中控系统", fill=TEXT_FAINT, font=get_font(12, bold=True))
    draw.text((W - 48, H - 42), "一人掌管一个直播矩阵", fill=CYAN, font=get_font(12, bold=True), anchor="ra")
    
    return im, draw

def render_poster_04():
    im, draw = create_base_canvas(4, glow_color=CYAN)
    draw.text((W//2, 125), "直播间有多少人", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "就说什么样的话", fill=CYAN, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "低峰留人 · 中峰讲品 · 高峰逼单 · 动态自适应", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    cards = [
        ("区间 01  ·  0 ~ 30 人 (低峰流量)", "核心任务：趣味破冰 · 留住进场人流", "自动激活 01.txt 留人话术，强化停留时长，防止直播间冷清滑走", CYAN, "留人话术"),
        ("区间 02  ·  30 ~ 100 人 (起势爬坡)", "核心任务：深度种草 · 细拆产品卖点", "自动激活 02.txt 讲品话术，深度讲解痛点、规格与使用效果", EMERALD, "讲品话术"),
        ("区间 03  ·  100+ 人 (峰值放量)", "核心任务：高频逼单 · 促成极速转化", "自动激活 03.txt 逼单话术，强调库存紧俏、限时秒杀，高转化成交", AMBER, "逼单促单"),
    ]
    
    y = 290
    for title, subtitle, desc, color, tag in cards:
        draw.rounded_rectangle([48, y, W - 48, y + 175], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71), width=1)
        draw.rounded_rectangle([48, y + 12, 54, y + 163], radius=3, fill=color)
        draw.text((72, y + 24), title, fill=WHITE, font=get_font(20, bold=True))
        draw.rounded_rectangle([W - 170, y + 20, W - 72, y + 54], radius=12, fill=(28, 40, 62), outline=color)
        draw.text((W - 121, y + 37), tag, fill=color, font=get_font(13, bold=True), anchor="mm")
        draw.text((72, y + 68), subtitle, fill=color, font=get_font(15, bold=True))
        draw.text((72, y + 104), desc, fill=TEXT_MUTED, font=get_font(14))
        
        draw.line([(72, y + 144), (W - 72, y + 144)], fill=(28, 40, 62), width=4)
        progress_w = 200 if color == CYAN else (450 if color == EMERALD else 700)
        draw.line([(72, y + 144), (72 + progress_w, y + 144)], fill=color, width=4)
        y += 195
        
    draw.rounded_rectangle([48, y + 10, W - 48, y + 95], radius=14, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, y + 36), "💡 实时人数自适应机制", fill=EMERALD, font=get_font(16, bold=True))
    draw.text((72, y + 64), "系统直连直播平台实时数据接口，毫秒级比对区间阈值，全自动放行对应脚本，0 人工干预", fill=TEXT_MUTED, font=get_font(13))
    
    im.convert("RGB").save(f"{OUT_DIR}/04_人数驱动.png")
    print("Poster 04 generated.")

def render_poster_05():
    im, draw = create_base_canvas(5, glow_color=EMERALD)
    draw.text((W//2, 125), "像编辑记事本一样", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "掌控整场直播", fill=EMERALD, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "01/02/03.txt 一键开启 · 随存随生效 · 自动关闭热重载", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    draw.rounded_rectangle([48, 280, W - 48, 620], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71), width=1)
    draw.rounded_rectangle([48, 280, W - 48, 324], radius=18, fill=(24, 35, 54))
    draw.text((72, 302), "📄 01.txt - 留人话术 (记事本)", fill=WHITE, font=get_font(15, bold=True), anchor="lm")
    draw.ellipse([W - 120, 298, W - 108, 310], fill=EMERALD)
    draw.ellipse([W - 98, 298, W - 86, 310], fill=AMBER)
    draw.ellipse([W - 76, 298, W - 64, 310], fill=RED)
    
    lines = [
        "欢迎刚进直播间的新朋友！我们是源头工厂日用百货专场，",
        "今天所有上架好物全部给家人们破价放漏！",
        "左上角点点关注不迷路，下方小黄车1号链接直接拍，",
        "现货现发，7天无理由，手慢无！",
        "",
        "// 提示：保存文件 (Ctrl + S) 后系统将自动热加载，并为您安全关闭记事本窗口。"
    ]
    for i, line in enumerate(lines):
        color = EMERALD if "//" in line else (WHITE if i < 2 else TEXT_MUTED)
        draw.text((72, 350 + i * 40), line, fill=color, font=get_font(15))
        
    steps = [
        ("1. 点击打开", "一键唤起系统原生记事本", CYAN),
        ("2. 随心修改", "任意增删产品卖点与话术", WHITE),
        ("3. Ctrl+S 保存", "修改内容瞬间热加载生效", EMERALD),
        ("4. 自动关闭", "保存完毕窗口自动关闭退出", AMBER),
    ]
    step_w = (W - 96 - 36) // 4
    for i, (stitle, sdesc, scolor) in enumerate(steps):
        sx = 48 + i * (step_w + 12)
        draw.rounded_rectangle([sx, 650, sx + step_w, 820], radius=14, fill=(19, 28, 45), outline=(34, 49, 71))
        draw.text((sx + step_w//2, 690), f"STEP 0{i+1}", fill=scolor, font=get_font(12, bold=True, en=True), anchor="mm")
        draw.text((sx + step_w//2, 730), stitle, fill=WHITE, font=get_font(16, bold=True), anchor="mm")
        draw.text((sx + step_w//2, 770), sdesc, fill=TEXT_MUTED, font=get_font(11), anchor="mm")
        
    draw.rounded_rectangle([48, 850, W - 48, 1020], radius=16, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, 885), "⚡ 为什么采用纯文本 + 原生记事本方案？", fill=CYAN, font=get_font(18, bold=True))
    features = [
        "· 零上手门槛：运营和主播无需学习复杂后台，像打字一样直接写话术",
        "· 极速热重载：文件系统事件毫秒级监听，播报中实时更新，绝不中断直播",
        "· 本地防丢失：01/02/03.txt 永久留存本地，版本备份一目了然"
    ]
    for i, feat in enumerate(features):
        draw.text((72, 925 + i * 28), feat, fill=TEXT_MUTED, font=get_font(14))
        
    im.convert("RGB").save(f"{OUT_DIR}/05_话术热编.png")
    print("Poster 05 generated.")

def render_poster_06():
    im, draw = create_base_canvas(6, glow_color=CYAN)
    draw.text((W//2, 125), "告别死板倒计时", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "说完即接下一句", fill=CYAN, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "VAD 智能语音端点检测 · 播完自动放行 · 绝不冷场", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    draw.rounded_rectangle([48, 280, W - 48, 590], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    
    draw.rounded_rectangle([72, 310, W//2 - 12, 560], radius=14, fill=(24, 18, 28), outline=(60, 30, 40))
    draw.text((W//4 + 18, 345), "❌ 传统死板倒计时", fill=RED, font=get_font(18, bold=True), anchor="mm")
    draw.text((96, 390), "· 机械设定 30 秒间隔", fill=TEXT_MUTED, font=get_font(14))
    draw.text((96, 430), "· 没说完直接切断话术 (暴躁断句)", fill=RED, font=get_font(13))
    draw.text((96, 470), "· 说完后长时间尴尬静音 (冷场掉人)", fill=RED, font=get_font(13))
    draw.text((96, 510), "· 违规风险高，极易被识别为录播", fill=TEXT_MUTED, font=get_font(13))
    
    draw.rounded_rectangle([W//2 + 12, 310, W - 72, 560], radius=14, fill=(16, 32, 36), outline=(20, 80, 70))
    draw.text((W*3//4 - 18, 345), "✅ 智播豆 VAD 智能接力", fill=EMERALD, font=get_font(18, bold=True), anchor="mm")
    draw.text((W//2 + 36, 390), "· 纯算法声学电平高精监听", fill=WHITE, font=get_font(14))
    draw.text((W//2 + 36, 430), "· 豆包开口播报：锁定监听状态", fill=CYAN, font=get_font(13))
    draw.text((W//2 + 36, 470), "· 播报结束静音 4.0s：毫秒级放行", fill=EMERALD, font=get_font(13))
    draw.text((W//2 + 36, 510), "· 零空档自然接力，真人级丝滑", fill=WHITE, font=get_font(13))
    
    draw.rounded_rectangle([48, 620, W - 48, 860], radius=18, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, 655), "🎙️ 声音能量实时电平雷达 (VAD Audio Meter)", fill=WHITE, font=get_font(18, bold=True))
    
    bars = 36
    bar_w = (W - 144) // bars
    for i in range(bars):
        bx = 72 + i * bar_w
        val = abs(math.sin(i * 0.28) * 0.45 + math.cos(i * 0.5) * 0.35) + 0.1
        bh = max(12, min(100, int(val * 90)))
        by = 780 - bh
        bcolor = RED if bh > 80 else (AMBER if bh > 60 else (EMERALD if bh > 30 else CYAN))
        draw.rounded_rectangle([bx + 2, by, bx + bar_w - 2, 780], radius=3, fill=bcolor)
        
    draw.line([(72, 715), (W - 72, 715)], fill=(60, 80, 110), width=1)
    draw.text((W - 72, 705), "静音判定阈值 (-42dB)", fill=TEXT_FAINT, font=get_font(11), anchor="ra")
    draw.text((72, 810), "状态：● 豆包播报中 (-28 dB) ➔ 判定静音持续中 (4.0s) ➔ 触发下一轮促单口播", fill=CYAN, font=get_font(13, bold=True))
    
    draw.rounded_rectangle([48, 890, W - 48, 1020], radius=16, fill=(19, 28, 45), outline=(34, 49, 71))
    draw.text((72, 925), "独家 VB-CABLE 数字回环与双路验音技术", fill=EMERALD, font=get_font(18, bold=True))
    draw.text((72, 960), "直通系统级音频底层，消除单帧杂音偶发误触，确保话术完完整整讲完，每一句话都交代清楚。", fill=TEXT_MUTED, font=get_font(14))
    
    im.convert("RGB").save(f"{OUT_DIR}/06_VAD语音接力.png")
    print("Poster 06 generated.")

def render_poster_07():
    im, draw = create_base_canvas(7, glow_color=VIOLET)
    draw.text((W//2, 125), "秒级读懂弹幕", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "答在客户心坎上", fill=VIOLET, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "DeepSeek 意图过滤 · 感谢礼物 · 购物问答秒回", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    scenarios = [
        ("🎁 送礼感谢", "观众送出【大啤酒 / 小心心】", "“感谢大哥送出的大啤酒！祝大哥财源广进，小黄车福利已为您安排！”", AMBER),
        ("❓ 购物问询", "观众提问：“身高175体重130穿什么码？”", "“175/130拍L码正合适，合身显瘦，喜欢宽松可以拍XL拍下秒发！”", EMERALD),
        ("🚚 物流售后", "观众提问：“什么时候发货？发什么快递？”", "“咱们全是现货秒发，默认顺丰包邮，48小时直达家人们手中！”", CYAN),
        ("🚫 无效杂音", "灌水广告、辱骂垃圾弹幕", "【智能语义研判：判定无转化价值与低俗垃圾，自动拦截静默不打扰】", TEXT_FAINT),
    ]
    
    y = 280
    for title, input_text, output_text, color in scenarios:
        draw.rounded_rectangle([48, y, W - 48, y + 145], radius=16, fill=(19, 28, 45, 230), outline=(34, 49, 71))
        draw.rounded_rectangle([68, y + 16, 190, y + 46], radius=10, fill=(28, 38, 58), outline=color)
        draw.text((129, y + 31), title, fill=color, font=get_font(14, bold=True), anchor="mm")
        draw.text((210, y + 23), input_text, fill=WHITE, font=get_font(14, bold=True))
        
        draw.rounded_rectangle([68, y + 58, W - 68, y + 130], radius=10, fill=(15, 22, 36))
        draw.text((84, y + 74), output_text, fill=color if color != TEXT_FAINT else TEXT_FAINT, font=get_font(13))
        y += 160
        
    draw.rounded_rectangle([48, y + 10, W - 48, y + 140], radius=16, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, y + 38), "🧠 为什么 DeepSeek 是直播弹幕的最佳大脑？", fill=VIOLET, font=get_font(18, bold=True))
    draw.text((72, y + 72), "· 深度电商意图分类：准确区分闲聊、送礼与高意向成交流量，不做机器人式机械复读", fill=TEXT_MUTED, font=get_font(13))
    draw.text((72, y + 100), "· 毫秒级极速响应：结合本地 Ollama / DeepSeek API，观众问完话音刚落，解答即刻响起", fill=TEXT_MUTED, font=get_font(13))
    
    im.convert("RGB").save(f"{OUT_DIR}/07_AI弹幕回复.png")
    print("Poster 07 generated.")

def render_poster_08():
    im, draw = create_base_canvas(8, glow_color=EMERALD)
    draw.text((W//2, 125), "不同显卡算力", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "自动匹配最佳发声", fill=EMERALD, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "8G+ IndexTTS拟真 · 4G+ MOSS轻量 · 集显文字回复", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    tiers = [
        ("FLAGSHIP 旗舰档 (显存 ≥ 8GB)", "IndexTTS 拟真声音克隆", "具备顶级声音克隆还原能力，情感丰满、语气逼真，声线与顶级真人主播无异，高门槛高回报。", VIOLET, "RTX 3070 / 4070 / 4090+"),
        ("EFFICIENT 轻量档 (4GB ≤ 显存 < 8GB)", "MOSS-TTS-Nano 高性能低开销", "专为轻薄独显笔记本与中端工作站深度优化，极速推理低显存占用，音色清澈自然，开播顺畅自如。", EMERALD, "RTX 3050 / 2060 / GTX 1660"),
        ("LIGHTWEIGHT 极速档 (集显 / 低算力)", "Playwright 网页端自动化直接打字", "无需任何独立显卡，直接通过浏览器驱动在直播间公屏极速打字回复，低成本设备人人体面开播。", CYAN, "轻薄本 / 核显 / 旧办公电脑"),
    ]
    
    y = 280
    for title, eng_name, desc, color, gpu in tiers:
        draw.rounded_rectangle([48, y, W - 48, y + 195], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71))
        draw.text((72, y + 24), title, fill=color, font=get_font(13, bold=True, en=True))
        draw.text((72, y + 54), eng_name, fill=WHITE, font=get_font(22, bold=True))
        draw.rounded_rectangle([W - 250, y + 20, W - 72, y + 54], radius=10, fill=(28, 40, 62), outline=color)
        draw.text((W - 161, y + 37), gpu, fill=color, font=get_font(11, bold=True, en=True), anchor="mm")
        draw.text((72, y + 100), desc, fill=TEXT_MUTED, font=get_font(14))
        
        draw.rounded_rectangle([72, y + 150, W - 72, y + 172], radius=6, fill=(15, 22, 36))
        ratio = 0.95 if color == VIOLET else (0.65 if color == EMERALD else 0.3)
        draw.rounded_rectangle([72, y + 150, 72 + int((W - 144) * ratio), y + 172], radius=6, fill=color)
        y += 215
        
    draw.rounded_rectangle([48, y + 10, W - 48, y + 95], radius=14, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, y + 36), "🔍 系统开机自动硬件探测", fill=CYAN, font=get_font(16, bold=True))
    draw.text((72, y + 64), "无需手动繁琐配置，软件启动瞬间自动检测 GPU 显存，无缝选定匹配方案，拒绝爆显存与闪退。", fill=TEXT_MUTED, font=get_font(13))
    
    im.convert("RGB").save(f"{OUT_DIR}/08_硬件自适应.png")
    print("Poster 08 generated.")

def render_poster_09():
    im, draw = create_base_canvas(9, glow_color=CYAN)
    draw.text((W//2, 125), "主副双声并存", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "纯算法优雅避让", fill=CYAN, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "WASAPI 毫秒级闪避至25% · 绝不抢话 · 广播级听感", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    draw.rounded_rectangle([48, 280, W - 48, 640], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 310), "📊 广播级双声波形闪避时序图 (WASAPI Software Ducking)", fill=WHITE, font=get_font(17, bold=True))
    
    draw.text((72, 355), "① 豆包主话术音量 (平时 100%) ➔ 闪避下凹至 25% ➔ 平滑渐变复原", fill=EMERALD, font=get_font(13, bold=True))
    pts1 = [
        (72, 420), (220, 420),
        (260, 425), (300, 490), (320, 495),
        (580, 495), (600, 490), (640, 425),
        (W - 72, 420)
    ]
    for i in range(len(pts1) - 1):
        draw.line([pts1[i], pts1[i+1]], fill=EMERALD, width=4)
        
    draw.text((320, 515), "▼ 自动压低至 25% (不抢话，隐约可听)", fill=EMERALD, font=get_font(12, bold=True))
    
    draw.text((72, 555), "② 弹幕 TTS 回复音量 (平时 0%) ➔ 突发插播 100% ➔ 播完归零", fill=VIOLET, font=get_font(13, bold=True))
    pts2 = [
        (72, 600), (300, 600),
        (310, 565), (320, 540),
        (580, 540), (590, 565), (600, 600),
        (W - 72, 600)
    ]
    for i in range(len(pts2) - 1):
        draw.line([pts2[i], pts2[i+1]], fill=VIOLET, width=4)
        
    draw.text((450, 520), "▲ 弹幕回复清晰发声 (100%)", fill=VIOLET, font=get_font(12, bold=True), anchor="mm")
    
    advantages = [
        ("纯软件算法调度", "通过 Windows WASAPI 独立声卡会话进行衰减，不改动物理手机音量，不损坏麦克风动态范围。", CYAN),
        ("60ms 极速平滑淡入", "绝无粗暴突兀的断音或爆音感，主副声音自然并存，给观众如同专业电台主播的听觉体验。", EMERALD),
        ("120ms 丝滑复原", "弹幕回复结束瞬间，主讲口播声平滑拉升回 100%，连贯流畅，绝不给直播间留下任何空虚尴尬。", VIOLET),
    ]
    y = 665
    for atitle, adesc, acolor in advantages:
        draw.rounded_rectangle([48, y, W - 48, y + 95], radius=14, fill=(15, 22, 36), outline=(30, 44, 66))
        draw.text((72, y + 22), atitle, fill=acolor, font=get_font(16, bold=True))
        draw.text((72, y + 54), adesc, fill=TEXT_MUTED, font=get_font(13))
        y += 115
        
    im.convert("RGB").save(f"{OUT_DIR}/09_声音闪避.png")
    print("Poster 09 generated.")

def render_poster_10():
    im, draw = create_base_canvas(10, glow_color=EMERALD)
    draw.text((W//2, 125), "零配置推流", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "OBS 浏览器源一键拉取", fill=EMERALD, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "内置极轻量 HTTP 桥 · 复制链接直接播报 · 告别复杂配置", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    draw.rounded_rectangle([48, 280, W - 48, 620], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 315), "🌐 轻量级 HTTP + SSE 实时音频推流架构", fill=WHITE, font=get_font(18, bold=True))
    
    draw.rounded_rectangle([72, 360, W - 72, 430], radius=12, fill=(15, 22, 36), outline=CYAN, width=1)
    draw.text((96, 395), "http://127.0.0.1:8554/danmu_audio", fill=CYAN, font=get_font(20, bold=True, en=True), anchor="lm")
    draw.rounded_rectangle([W - 190, 372, W - 92, 418], radius=8, fill=EMERALD)
    draw.text((W - 141, 395), "📋 复制链接", fill=WHITE, font=get_font(13, bold=True), anchor="mm")
    
    draw.rounded_rectangle([72, 460, W//2 - 12, 590], radius=12, fill=(28, 20, 24), outline=(60, 30, 40))
    draw.text((W//4 + 18, 490), "❌ 传统推流方案", fill=RED, font=get_font(16, bold=True), anchor="mm")
    draw.text((92, 525), "· 必须安装笨重 FFmpeg (几百兆)", fill=TEXT_MUTED, font=get_font(13))
    draw.text((92, 555), "· 命令行转流，易断流，CPU 占用高", fill=RED, font=get_font(13))
    
    draw.rounded_rectangle([W//2 + 12, 460, W - 72, 590], radius=12, fill=(18, 30, 36), outline=(20, 70, 60))
    draw.text((W*3//4 - 18, 490), "✅ 智播豆浏览器源方案", fill=EMERALD, font=get_font(16, bold=True), anchor="mm")
    draw.text((W//2 + 32, 525), "· 内置微型纯 Python 服务，零外部依赖", fill=WHITE, font=get_font(13))
    draw.text((W//2 + 32, 555), "· OBS 添加浏览器源即刻出声，稳定可靠", fill=EMERALD, font=get_font(13))
    
    steps = [
        ("第 1 步", "在智播豆界面点击【复制】音频链接"),
        ("第 2 步", "在 OBS 来源列表中点击【+】添加【浏览器】"),
        ("第 3 步", "粘贴链接并勾选【通过 OBS 控制音频】，完成！"),
    ]
    y = 650
    for snum, sdesc in steps:
        draw.rounded_rectangle([48, y, W - 48, y + 80], radius=14, fill=(15, 22, 36), outline=(30, 44, 66))
        draw.rounded_rectangle([68, y + 20, 150, y + 60], radius=8, fill=(28, 40, 62))
        draw.text((109, y + 40), snum, fill=CYAN, font=get_font(14, bold=True), anchor="mm")
        draw.text((170, y + 40), sdesc, fill=WHITE, font=get_font(15, bold=True), anchor="lm")
        y += 98
        
    draw.rounded_rectangle([48, 960, W - 48, 1030], radius=12, fill=(19, 28, 45))
    draw.text((W//2, 995), "💡 零延迟 HTML5 Audio 架构，完美支持 OBS Studio / 抖音直播伴侣 / 视频号助手", fill=TEXT_MUTED, font=get_font(13), anchor="mm")
    
    im.convert("RGB").save(f"{OUT_DIR}/10_OBS推流.png")
    print("Poster 10 generated.")

def render_poster_11():
    im, draw = create_base_canvas(11, glow_color=CYAN)
    draw.text((W//2, 125), "一人管控多机矩阵", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 175), "降低 90% 人力成本", fill=CYAN, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 225), "24 小时不间断开播 · 矩阵式带货 · 运营成本归零", fill=TEXT_MUTED, font=get_font(17), anchor="mm")
    
    draw.rounded_rectangle([48, 280, W - 48, 700], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 315), "⚖️ 传统人工直播团队 vs 智播豆 AI 矩阵中控", fill=WHITE, font=get_font(18, bold=True))
    
    rows = [
        ("人力配备", "3~4人 / 间 (主播+中控+场控)", "1人 看管 5~10 台直播手机", RED, EMERALD),
        ("单月支出", "¥ 30,000 ~ 50,000 / 月", "极低电力与算力消耗，近乎为零", RED, EMERALD),
        ("开播时长", "每天 4~6 小时，极易疲劳", "7 × 24 小时通宵不间断带货", RED, EMERALD),
        ("话术质量", "依赖主播发挥，情绪波动大", "金牌爆款话术，稳定持续输出", RED, EMERALD),
        ("起号成本", "招人难、培训慢、离职即停播", "随开随播，支持快速多账号矩阵测品", RED, EMERALD),
    ]
    y = 360
    for item, trad, zbd, c1, c2 in rows:
        draw.rounded_rectangle([72, y, W - 72, y + 54], radius=10, fill=(15, 22, 36))
        draw.text((96, y + 27), item, fill=WHITE, font=get_font(14, bold=True), anchor="lm")
        draw.text((220, y + 27), trad, fill=c1, font=get_font(13), anchor="lm")
        draw.text((W - 96, y + 27), zbd, fill=c2, font=get_font(14, bold=True), anchor="rm")
        y += 66
        
    draw.rounded_rectangle([48, 730, W - 48, 1020], radius=18, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, 765), "🚀 为什么电商卖家正在全面拥抱【智播豆】？", fill=EMERALD, font=get_font(18, bold=True))
    points = [
        ("· 拯救闲置手机", "旧安卓手机插上线直接投屏变身带货主机，废物利用创造增量营收"),
        ("· 抢占凌晨流量", "夜间 00:00 - 06:00 竞品主播全下播，智播豆 24 小时低成本抢收全网冷门高转化流量"),
        ("· 矩阵裂变扩张", "单机模型跑通，直接一键复制 5 台、10 台，快速形成全网直播轰炸矩阵"),
    ]
    for i, (pt, pd) in enumerate(points):
        draw.text((72, 815 + i * 65), pt, fill=CYAN, font=get_font(15, bold=True))
        draw.text((72, 845 + i * 65), pd, fill=TEXT_MUTED, font=get_font(13))
        
    im.convert("RGB").save(f"{OUT_DIR}/11_矩阵降本.png")
    print("Poster 11 generated.")

def render_poster_12():
    im, draw = create_base_canvas(12, glow_color=EMERALD)
    draw.text((W//2, 130), "开启您的 AI 智能直播新纪元", fill=WHITE, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, 180), "智播豆 · AI 智能直播工作台", fill=EMERALD, font=get_font(28, bold=True), anchor="mm")
    draw.text((W//2, 230), "立即部署 · 释放无限商业潜能", fill=CYAN, font=get_font(18, bold=True), anchor="mm")
    
    draw.rounded_rectangle([48, 280, W - 48, 760], radius=18, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 315), "🌟 智播豆 6 大硬核能力全景矩阵", fill=WHITE, font=get_font(18, bold=True))
    
    abilities = [
        ("1. 实时人数驱动", "进场人数动态驱动区间话术", CYAN),
        ("2. 记事本热重载", "01/02/03.txt 随改随存秒生效", EMERALD),
        ("3. VAD 智能接力", "纯算法语音监听，说完即换", VIOLET),
        ("4. DeepSeek 弹幕", "大模型意图过滤与礼物感谢", AMBER),
        ("5. 纯算法声音避让", "WASAPI 闪避至25%，主次分明", CYAN),
        ("6. OBS 浏览器直推", "极轻量 HTTP 桥，一键拉流", EMERALD),
    ]
    bw = (W - 96 - 24) // 2
    for i, (atitle, adesc, acolor) in enumerate(abilities):
        col = i % 2
        row = i // 2
        ax = 72 + col * (bw + 24)
        ay = 360 + row * 125
        draw.rounded_rectangle([ax, ay, ax + bw, ay + 105], radius=12, fill=(15, 22, 36), outline=(30, 44, 66))
        draw.text((ax + 20, ay + 22), atitle, fill=acolor, font=get_font(16, bold=True))
        draw.text((ax + 20, ay + 58), adesc, fill=TEXT_MUTED, font=get_font(13))
        
    draw.rounded_rectangle([48, 790, W - 48, 1020], radius=18, fill=(15, 22, 36), outline=EMERALD, width=2)
    draw.text((W//2, 840), "🚀 抢占先机，开启全天候智能带货", fill=WHITE, font=get_font(24, bold=True), anchor="mm")
    draw.text((W//2, 885), "无需经验 · 现成方案 · 极速部署 · 专属售后技术支持", fill=TEXT_MUTED, font=get_font(15), anchor="mm")
    
    draw.rounded_rectangle([W//2 - 160, 925, W//2 + 160, 985], radius=16, fill=EMERALD)
    draw.text((W//2, 955), "立即体验 · 预约演示", fill=WHITE, font=get_font(20, bold=True), anchor="mm")
    
    im.convert("RGB").save(f"{OUT_DIR}/12_CTA收束.png")
    print("Poster 12 generated.")

if __name__ == "__main__":
    render_poster_04()
    render_poster_05()
    render_poster_06()
    render_poster_07()
    render_poster_08()
    render_poster_09()
    render_poster_10()
    render_poster_11()
    render_poster_12()
    print("All posters (04 - 12) rendered successfully!")
