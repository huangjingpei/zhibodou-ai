"""
智播豆 16:9 全画幅宣发海报渲染引擎 (极致排版优化版)
尺寸：1280 x 720 (标准 16:9 宽屏)
重构重点：
1. 彻底解决“长方向框框”过多与位置不当问题（消除多重无序嵌套、消除底部挤压的长条扁框）。
2. 左栏全面采用“单体统摄大卡片”，内部使用优雅虚线/细线分隔与图标排版，告别机械堆叠。
3. 右栏 3D 画面移除遮挡画面的粗暴悬浮方块，改用演播室四角精密科技取景框。
4. 对比表格（Poster 11）废除 5 个独立悬浮砖块，重构为专业彭博/特斯拉风格数据行。
5. 硬件与声学图表（Poster 08、09）将过厚纯色色块条精细化为声学仪轨与霓虹光轨。
"""

import math
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "images", "16x9")
SRC_3X4_DIR = os.path.join(BASE_DIR, "images", "3x4")
os.makedirs(OUT_DIR, exist_ok=True)

FONT_PATH_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_PATH_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_PATH_EN = "C:/Windows/Fonts/segoeuib.ttf"

def get_font(size, bold=False, en_only=False):
    path = FONT_PATH_EN if en_only else (FONT_PATH_BOLD if bold else FONT_PATH_REG)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# 基础色板
BG_DARK = (11, 16, 27)
BG_LIGHT = (18, 28, 44)
SURFACE = (19, 28, 45, 235)
SURFACE_BORDER = (34, 49, 71)
CYAN = (34, 211, 238)
EMERALD = (16, 185, 129)
VIOLET = (168, 85, 247)
AMBER = (245, 158, 11)
RED = (244, 63, 94)
WHITE = (248, 250, 252)
TEXT_MUTED = (148, 163, 184)
TEXT_FAINT = (100, 116, 139)

def create_base_16x9_canvas(page_num, glow_color=CYAN):
    im = Image.new("RGBA", (W, H), (11, 16, 27, 255))
    draw = ImageDraw.Draw(im)
    
    # 垂直微渐变背景覆盖全画幅
    for y in range(H):
        t = y / H
        r = int(11 * (1 - t) + 16 * t)
        g = int(16 * (1 - t) + 24 * t)
        b = int(27 * (1 - t) + 38 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
        
    # 背景科技网格线覆盖整个 1280 宽度
    grid_color = (25, 36, 56, 110)
    for x in range(0, W, 48):
        draw.line([(x, 0), (x, H)], fill=grid_color)
    for y in range(0, H, 48):
        draw.line([(0, y), (W, y)], fill=grid_color)
        
    # 顶部品牌条 (左侧，低调优雅)
    draw.rounded_rectangle([48, 22, 230, 54], radius=16, fill=(24, 35, 54, 220), outline=(40, 58, 85))
    draw.ellipse([62, 33, 72, 43], fill=EMERALD)
    draw.text((82, 28), "智播豆 · ZHIBODOU", fill=WHITE, font=get_font(13, bold=True))
    
    # 顶部序号胶囊 (右侧)
    draw.rounded_rectangle([W - 148, 22, W - 48, 54], radius=16, fill=(24, 35, 54, 220), outline=(40, 58, 85))
    draw.text((W - 98, 38), f"{page_num:02d} / 12", fill=glow_color, font=get_font(14, bold=True, en_only=True), anchor="mm")
    
    # 底部说明与状态信息
    draw.line([(48, H - 46), (W - 48, H - 46)], fill=(30, 44, 66))
    draw.text((48, H - 32), "ZHIBODOU · 全流程 AI 智能直播中控系统", fill=TEXT_FAINT, font=get_font(12, bold=True))
    draw.text((W - 48, H - 32), "一人掌管一个直播矩阵", fill=glow_color, font=get_font(12, bold=True), anchor="ra")
    
    return im, draw

def save_dual_posters(im, num_str, cn_name, en_name):
    rgb_im = im.convert("RGB")
    rgb_im.save(f"{OUT_DIR}/{num_str}_{cn_name}.png", quality=95)
    rgb_im.save(f"{OUT_DIR}/{num_str}_{en_name}.png", quality=95)
    print(f"Saved: {num_str}_{cn_name}.png & {num_str}_{en_name}.png")

def composite_3d_asset(im, src_filename, target_rect):
    """将 3D 渲染图无缝融入右侧取景框中，绝不在画面上方乱贴长条色块"""
    src_path = os.path.join(SRC_3X4_DIR, src_filename)
    if not os.path.exists(src_path):
        return
    src_im = Image.open(src_path).convert("RGBA")
    
    w_src, h_src = src_im.size
    crop_box = (0, 230, w_src, h_src - 20)
    cropped = src_im.crop(crop_box)
    
    rx, ry, rw, rh = target_rect
    scale = max(rw / cropped.width, rh / cropped.height)
    new_w = int(cropped.width * scale)
    new_h = int(cropped.height * scale)
    resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    cx = (new_w - rw) // 2
    cy = (new_h - rh) // 2
    fitted = resized.crop((cx, cy, cx + rw, cy + rh))
    im.paste(fitted, (rx, ry))

def draw_corner_brackets(draw, rect, color, length=24, width=2):
    """在四角绘制精美科技取景准星线，替代粗笨的大边框"""
    x1, y1, x2, y2 = rect
    # 左上
    draw.line([(x1, y1), (x1 + length, y1)], fill=color, width=width)
    draw.line([(x1, y1), (x1, y1 + length)], fill=color, width=width)
    # 右上
    draw.line([(x2, y1), (x2 - length, y1)], fill=color, width=width)
    draw.line([(x2, y1), (x2, y1 + length)], fill=color, width=width)
    # 左下
    draw.line([(x1, y2), (x1 + length, y2)], fill=color, width=width)
    draw.line([(x1, y2), (x1, y2 - length)], fill=color, width=width)
    # 右下
    draw.line([(x2, y2), (x2 - length, y2)], fill=color, width=width)
    draw.line([(x2, y2), (x2, y2 - length)], fill=color, width=width)

# ==========================================
# 01 品牌封面 (Brand Hero)
# ==========================================
def render_poster_01():
    im, draw = create_base_16x9_canvas(1, glow_color=CYAN)
    
    # 左栏面包屑微标签 (无突兀外框，极简专业)
    draw.text((48, 76), "● FEATURE 01 · 品牌总览", fill=CYAN, font=get_font(13, bold=True))
    draw.text((48, 115), "智播豆", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "AI 智能直播工作台", fill=CYAN, font=get_font(32, bold=True))
    draw.text((48, 218), "一人掌管多机，开启无人带货新纪元", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：单一统摄玻璃大卡片 (取代原来 4 个破碎的长条方块)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 288), "● 一体化全链路中控体系", fill=WHITE, font=get_font(16, bold=True))
    
    chips = [
        ("真机高清投屏", "Scrcpy 底层协议直连，超低延迟无损画质呈现"),
        ("豆包大模型口播", "高仿真真人声学起伏，语速自然，情感丰满动听"),
        ("全天候无人值守", "自动感知人数话术接力，7×24h 通宵抢占流量"),
    ]
    y = 330
    for title, desc in chips:
        draw.ellipse([74, y + 4, 82, y + 12], fill=CYAN)
        draw.text((96, y), title, fill=WHITE, font=get_font(15, bold=True))
        draw.text((96, y + 28), desc, fill=TEXT_MUTED, font=get_font(13))
        draw.line([(72, y + 74), (446, y + 74)], fill=(28, 40, 62))
        y += 88
        
    # 底部整合提示区 (不再是一个单独漂浮的扁框，而是自然融于大卡片底部)
    draw.text((72, 606), "开箱即用 · 集成投屏、口播、弹幕、避让、推流", fill=EMERALD, font=get_font(12, bold=True))
    
    # 右栏：3D 演播室主机视效 (移除画面内突兀悬浮的文字方块)
    right_rect = (500, 76, 732, 572)
    composite_3d_asset(im, "01_cover.png", right_rect)
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle([500, 76, 1232, 648], radius=16, outline=(40, 60, 90), width=1)
    draw_corner_brackets(draw, [500, 76, 1232, 648], CYAN, length=24, width=2)
    
    save_dual_posters(im, "01", "品牌封面", "cover")

# ==========================================
# 02 行业痛点 (Industry Pain Points)
# ==========================================
def render_poster_02():
    im, draw = create_base_16x9_canvas(2, glow_color=RED)
    
    draw.text((48, 76), "● FEATURE 02 · 行业痛点深度剖析", fill=RED, font=get_font(13, bold=True))
    draw.text((48, 115), "高薪难招好主播", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "断播即是亏损", fill=RED, font=get_font(34, bold=True))
    draw.text((48, 218), "中小商家与团队面临的 4 大不可承受之痛", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：单一大卡片容纳 4 项痛点 (杜绝 5 个上下挤压的细长扁框)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(19, 28, 45, 230), outline=(50, 30, 40))
    draw.text((72, 285), "● 传统人工带货的致命软肋", fill=WHITE, font=get_font(16, bold=True))
    
    pains = [
        ("人力成本高企", "底薪加提成月耗数万，主播离职带走粉丝资产", RED),
        ("主播状态起伏", "情绪化、请假迟到、开播率不稳定导致流量腰斩", AMBER),
        ("深夜通宵难熬", "凌晨 0~6 点高转化黄金捡漏期无人开播守候", RED),
        ("录播封禁风险", "录播极易触发平台算法风控检测，惨遭断流封号", AMBER),
    ]
    y = 325
    for title, desc, col in pains:
        draw.ellipse([74, y + 5, 82, y + 13], fill=col)
        draw.text((96, y), title, fill=WHITE, font=get_font(14, bold=True))
        draw.text((96, y + 26), desc, fill=TEXT_MUTED, font=get_font(12))
        y += 68
        
    draw.line([(72, 595), (446, 595)], fill=(40, 25, 35))
    draw.text((72, 612), "● 痛点终结：智播豆实现 24 小时全自动化接管", fill=RED, font=get_font(12, bold=True))
    
    # 右栏：3D 深夜空台
    right_rect = (500, 76, 732, 572)
    composite_3d_asset(im, "02_pain.png", right_rect)
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle([500, 76, 1232, 648], radius=16, outline=(60, 30, 40), width=1)
    draw_corner_brackets(draw, [500, 76, 1232, 648], RED, length=24, width=2)
    
    save_dual_posters(im, "02", "行业痛点", "pain")

# ==========================================
# 03 产品全景 (Product Architecture)
# ==========================================
def render_poster_03():
    im, draw = create_base_16x9_canvas(3, glow_color=EMERALD)
    
    draw.text((48, 76), "● FEATURE 03 · 架构总览", fill=EMERALD, font=get_font(13, bold=True))
    draw.text((48, 115), "全链路 AI 数字人", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "直播中控系统", fill=EMERALD, font=get_font(34, bold=True))
    draw.text((48, 218), "投屏 · 口播 · 接力 · 弹幕 · 避让 · 推流", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：单一大卡片 (去除琐碎小条框)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(19, 28, 45, 230), outline=(20, 60, 50))
    draw.text((72, 288), "● 端到端全链路工程级架构", fill=WHITE, font=get_font(16, bold=True))
    
    features = [
        ("原生底层协议直连", "Scrcpy 真机高清无损投屏，免装第三方杂乱应用"),
        ("双大模型高效协同", "豆包专业口播带货 + DeepSeek 毫秒级弹幕过滤"),
        ("全闭环防风控体系", "VAD 声学静音感知，真机互动质感，平台合规友好"),
    ]
    y = 330
    for title, desc in features:
        draw.ellipse([74, y + 4, 82, y + 12], fill=EMERALD)
        draw.text((96, y), title, fill=WHITE, font=get_font(15, bold=True))
        draw.text((96, y + 28), desc, fill=TEXT_MUTED, font=get_font(13))
        draw.line([(72, y + 74), (446, y + 74)], fill=(20, 40, 36))
        y += 88
        
    draw.text((72, 606), "极简部署 · 复制音频源直接接入 OBS，无需复杂配置", fill=EMERALD, font=get_font(12, bold=True))
    
    # 右栏：3D 架构图 (移除内部悬浮杂色块)
    right_rect = (500, 76, 732, 572)
    composite_3d_asset(im, "03_arch.png", right_rect)
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle([500, 76, 1232, 648], radius=16, outline=(20, 80, 70), width=1)
    draw_corner_brackets(draw, [500, 76, 1232, 648], EMERALD, length=24, width=2)
    
    save_dual_posters(im, "03", "产品全景", "arch")

# ==========================================
# 04 人数驱动 (Audience Driven)
# ==========================================
def render_poster_04():
    im, draw = create_base_16x9_canvas(4, glow_color=CYAN)
    
    draw.text((48, 76), "● FEATURE 04 · 流量自适应策略", fill=CYAN, font=get_font(13, bold=True))
    draw.text((48, 115), "直播间有多少人", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "就说什么样的话", fill=CYAN, font=get_font(34, bold=True))
    draw.text((48, 218), "低峰留人 · 中峰讲品 · 高峰逼单 · 动态自适应", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：一体化原理解析大卡 (移除底部浮空扁框)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, 290), "● 实时人数感知闭环", fill=EMERALD, font=get_font(17, bold=True))
    
    points = [
        ("毫秒级平台直连", "直通抖音/视频号/快手直播间数据底层，秒级捕捉在线人数跃迁。"),
        ("全自动策略放行", "人数一旦突破设定阈值，毫秒级无缝切换对应话术，无需人工值守切换。"),
        ("最大化公域转化", "冷清时趣味破冰拉高停留时长，爆流时高频逼单极速促成成交转化。"),
    ]
    y = 340
    for ptitle, pdesc in points:
        draw.ellipse([74, y + 4, 82, y + 12], fill=CYAN)
        draw.text((96, y), ptitle, fill=WHITE, font=get_font(14, bold=True))
        draw.text((96, y + 26), pdesc, fill=TEXT_MUTED, font=get_font(12))
        y += 82
        
    draw.line([(72, 595), (446, 595)], fill=(28, 40, 62))
    draw.text((72, 612), "● 算法引擎自动判定 · 0 人工干预", fill=CYAN, font=get_font(12, bold=True))
    
    # 右栏：3 个精心设计的策略区间卡片 (优化边框与内部层次)
    cards = [
        ("区间 01  ·  0 ~ 30 人 (低峰流量)", "核心任务：趣味破冰 · 留住进场人流", "自动激活 01.txt 留人话术，强化停留时长，防止直播间冷清滑走", CYAN, "留人话术", 0.25),
        ("区间 02  ·  30 ~ 100 人 (起势爬坡)", "核心任务：深度种草 · 细拆产品卖点", "自动激活 02.txt 讲品话术，深度讲解痛点、规格与使用效果", EMERALD, "讲品话术", 0.65),
        ("区间 03  ·  100+ 人 (峰值放量)", "核心任务：高频逼单 · 促成极速转化", "自动激活 03.txt 逼单话术，强调库存紧俏、限时秒杀，高转化成交", AMBER, "逼单促单", 0.95),
    ]
    y = 76
    for title, subtitle, desc, color, tag, ratio in cards:
        draw.rounded_rectangle([500, y, 1232, y + 176], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71), width=1)
        # 顶部标题栏与标签
        draw.text((524, y + 22), title, fill=WHITE, font=get_font(18, bold=True))
        draw.rounded_rectangle([1110, y + 18, 1208, y + 48], radius=8, fill=(28, 40, 62), outline=color)
        draw.text((1159, y + 33), tag, fill=color, font=get_font(13, bold=True), anchor="mm")
        
        draw.text((524, y + 62), subtitle, fill=color, font=get_font(14, bold=True))
        draw.text((524, y + 94), desc, fill=TEXT_MUTED, font=get_font(13))
        
        # 纤细精致的仪表光轨 (不再是粗苯长条)
        bar_x1, bar_y, bar_x2 = 524, y + 142, 1208
        draw.line([(bar_x1, bar_y), (bar_x2, bar_y)], fill=(28, 40, 62), width=4)
        active_w = int((bar_x2 - bar_x1) * ratio)
        draw.line([(bar_x1, bar_y), (bar_x1 + active_w, bar_y)], fill=color, width=4)
        y += 194
        
    save_dual_posters(im, "04", "人数驱动", "audience")

# ==========================================
# 05 话术热编 (Instant Script Notepad)
# ==========================================
def render_poster_05():
    im, draw = create_base_16x9_canvas(5, glow_color=EMERALD)
    
    draw.text((48, 76), "● FEATURE 05 · 话术热重载架构", fill=EMERALD, font=get_font(13, bold=True))
    draw.text((48, 115), "像编辑记事本一样", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "掌控整场直播", fill=EMERALD, font=get_font(34, bold=True))
    draw.text((48, 218), "01/02/03.txt 随存随生效 · 自动关闭", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：一体化流程图 (4 步纵向时间轴，取代 4 个零散长条方块)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 288), "● 记事本热生效极简工作流", fill=WHITE, font=get_font(16, bold=True))
    
    # 时间轴纵向连线
    draw.line([(88, 335), (88, 560)], fill=(34, 49, 71), width=2)
    
    steps = [
        ("01", "一键点击打开", "唤起系统原生记事本，熟悉亲切", CYAN),
        ("02", "随心修改话术", "任意增删产品卖点、优惠与促单词", WHITE),
        ("03", "Ctrl+S 极速保存", "系统毫秒级监听变动，瞬间热重载", EMERALD),
        ("04", "窗口自动安全关闭", "保存后自动退出记事本，绝不遮挡", AMBER),
    ]
    y = 330
    for num, stitle, sdesc, scol in steps:
        draw.ellipse([78, y + 2, 98, y + 22], fill=(24, 35, 54), outline=scol, width=2)
        draw.text((88, y + 12), num, fill=scol, font=get_font(10, bold=True, en_only=True), anchor="mm")
        draw.text((112, y), stitle, fill=WHITE, font=get_font(14, bold=True))
        draw.text((112, y + 26), sdesc, fill=TEXT_MUTED, font=get_font(12))
        y += 66
        
    draw.line([(72, 595), (446, 595)], fill=(28, 40, 62))
    draw.text((72, 612), "● 零学习门槛 · 播报中更新绝不中断直播推流", fill=EMERALD, font=get_font(12, bold=True))
    
    # 右栏：原生记事本 IDE 真实窗口 (修复标题栏圆角嵌套冲突)
    draw.rounded_rectangle([500, 76, 1232, 500], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71), width=1)
    # 标题栏无缝紧密结合
    draw.rectangle([501, 77, 1231, 118], fill=(24, 35, 54))
    draw.text((524, 98), "01.txt - 留人话术 (Windows 原生记事本)", fill=WHITE, font=get_font(14, bold=True), anchor="lm")
    # 红黄绿圆点
    draw.ellipse([1150, 92, 1162, 104], fill=EMERALD)
    draw.ellipse([1172, 92, 1184, 104], fill=AMBER)
    draw.ellipse([1194, 92, 1206, 104], fill=RED)
    
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
        draw.text((524, 142 + i * 44), line, fill=color, font=get_font(15))
        
    # 下方方案优势卡片
    draw.rounded_rectangle([500, 520, 1232, 648], radius=14, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((524, 542), "● 为什么坚持纯文本 + 原生记事本方案？", fill=CYAN, font=get_font(15, bold=True))
    draw.text((524, 574), "· 零学习成本：运营人员无需培训复杂的后台系统，像打字一样直接改话术。", fill=TEXT_MUTED, font=get_font(13))
    draw.text((524, 604), "· 本地数据资产：01/02/03.txt 永久留存本地磁盘，离线修改，版本备份一目了然。", fill=TEXT_MUTED, font=get_font(13))
    
    save_dual_posters(im, "05", "话术热编", "scripts")

# ==========================================
# 06 VAD 语音接力 (VAD Smart Relay)
# ==========================================
def render_poster_06():
    im, draw = create_base_16x9_canvas(6, glow_color=CYAN)
    
    draw.text((48, 76), "● FEATURE 06 · VAD 声学智能接力", fill=CYAN, font=get_font(13, bold=True))
    draw.text((48, 115), "告别死板倒计时", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "说完即接下一句", fill=CYAN, font=get_font(34, bold=True))
    draw.text((48, 218), "VAD 智能语音端点检测 · 绝不冷场", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：上下两张对比卡片（严格水平分割对齐，高度规整）
    draw.rounded_rectangle([48, 260, 470, 440], radius=14, fill=(28, 18, 24), outline=(60, 30, 40))
    draw.text((68, 282), "[传统方案] 死板倒计时模式", fill=RED, font=get_font(15, bold=True))
    draw.text((68, 314), "· 机械设定固定 30 秒间隔", fill=TEXT_MUTED, font=get_font(13))
    draw.text((68, 342), "· 没说完直接粗暴切断 (暴躁断句)", fill=RED, font=get_font(13))
    draw.text((68, 370), "· 说完后长时间尴尬静音 (冷场掉人)", fill=RED, font=get_font(13))
    draw.text((68, 398), "· 违规风险高，极易被平台识别为录播", fill=TEXT_MUTED, font=get_font(12))
    
    draw.rounded_rectangle([48, 458, 470, 648], radius=14, fill=(16, 32, 36), outline=(20, 80, 70))
    draw.text((68, 480), "[智播豆方案] VAD 智能接力", fill=EMERALD, font=get_font(15, bold=True))
    draw.text((68, 512), "· 纯算法声学电平毫秒级精准监听", fill=WHITE, font=get_font(13))
    draw.text((68, 540), "· 豆包开口播报：锁定监听状态", fill=CYAN, font=get_font(13))
    draw.text((68, 568), "· 播完静音持续 4.0s：毫秒级放行下一句", fill=EMERALD, font=get_font(13))
    draw.text((68, 596), "· 零空档自然连贯，真人级丝滑接力", fill=WHITE, font=get_font(13))
    
    # 右栏：与左栏完全对称对齐（440 结束，458 开始）
    draw.rounded_rectangle([500, 76, 1232, 440], radius=14, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((524, 102), "● 声音能量实时电平雷达 (VAD Audio Meter)", fill=WHITE, font=get_font(17, bold=True))
    
    # 48 柱音频均衡器
    bars = 48
    bar_w = (732 - 48) // bars
    for i in range(bars):
        bx = 524 + i * bar_w
        val = abs(math.sin(i * 0.25) * 0.5 + math.cos(i * 0.42) * 0.35) + 0.12
        bh = max(14, min(140, int(val * 130)))
        by = 310 - bh
        bcolor = RED if bh > 115 else (AMBER if bh > 85 else (EMERALD if bh > 45 else CYAN))
        draw.rounded_rectangle([bx + 1, by, bx + bar_w - 2, 310], radius=3, fill=bcolor)
        
    draw.line([(524, 230), (1208, 230)], fill=(60, 80, 110), width=1)
    draw.text((1208, 218), "静音判定阈值 (-42dB)", fill=TEXT_FAINT, font=get_font(11), anchor="ra")
    draw.text((524, 345), "状态：● 豆包播报中 (-28 dB) -> 判定静音持续 (4.0s) -> 毫秒级放行下一轮", fill=CYAN, font=get_font(14, bold=True))
    draw.text((524, 385), "动态声学特征自适应，过滤环境白噪声，精准锁死每一句话的起止时刻。", fill=TEXT_MUTED, font=get_font(13))
    
    # 下方技术卡片 (458 到 648，高度 190)
    draw.rounded_rectangle([500, 458, 1232, 648], radius=14, fill=(19, 28, 45), outline=(34, 49, 71))
    draw.text((524, 484), "● 独家 VB-CABLE 数字回环与双路验音技术", fill=EMERALD, font=get_font(16, bold=True))
    draw.text((524, 520), "直通系统级音频底层，消除单帧杂音偶发误触，确保每一句产品卖点都完完整整交代清楚。", fill=TEXT_MUTED, font=get_font(13))
    draw.text((524, 558), "无需外接任何实体麦克风或声卡硬件，纯虚拟音频回环驱动，系统资源开销近乎为零。", fill=TEXT_MUTED, font=get_font(13))
    
    save_dual_posters(im, "06", "VAD语音接力", "vad")

# ==========================================
# 07 AI 弹幕回复 (DeepSeek Danmu Brain)
# ==========================================
def render_poster_07():
    im, draw = create_base_16x9_canvas(7, glow_color=VIOLET)
    
    draw.text((48, 76), "● FEATURE 07 · 弹幕智能中枢", fill=VIOLET, font=get_font(13, bold=True))
    draw.text((48, 115), "秒级读懂弹幕", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "答在客户心坎上", fill=VIOLET, font=get_font(34, bold=True))
    draw.text((48, 218), "DeepSeek 意图过滤 · 感谢礼物 · 购物问答秒回", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：单一大卡片 (消除浮动小条框)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, 288), "● 为什么 DeepSeek 是最佳大脑？", fill=VIOLET, font=get_font(16, bold=True))
    
    benefits = [
        ("深度电商意图分类", "准确区分送礼、尺码询问、售后与闲聊。"),
        ("拒绝机械复读机", "结合上下文生成亲切自然的真人回复。"),
        ("智能静默过滤", "对发广告、低俗辱骂等无效弹幕自动拦截。"),
        ("双轨引擎自由配置", "支持云端 DeepSeek API 或本地部署 Ollama。"),
    ]
    y = 330
    for btitle, bdesc in benefits:
        draw.ellipse([74, y + 4, 82, y + 12], fill=VIOLET)
        draw.text((96, y), btitle, fill=WHITE, font=get_font(14, bold=True))
        draw.text((96, y + 24), bdesc, fill=TEXT_MUTED, font=get_font(12))
        y += 66
        
    draw.line([(72, 595), (446, 595)], fill=(28, 40, 62))
    draw.text((72, 612), "● 提升 300% 互动留存率 · 转化率倍增", fill=EMERALD, font=get_font(12, bold=True))
    
    # 右栏：4 个对话场景（移除内部重叠方块，改用极简竖条指示器）
    scenarios = [
        ("礼物感谢", "观众送出【大啤酒 / 小心心】", "“感谢大哥送出的大啤酒！祝大哥财源广进，小黄车福利已为您安排！”", AMBER),
        ("购物问询", "观众提问：“身高175体重130穿什么码？”", "“175/130拍L码正合适，合身显瘦，喜欢宽松可以拍XL拍下秒发！”", EMERALD),
        ("物流售后", "观众提问：“什么时候发货？发什么快递？”", "“咱们全是现货秒发，默认顺丰包邮，48小时直达家人们手中！”", CYAN),
        ("无效杂音", "灌水广告、低俗垃圾弹幕", "【智能语义研判：判定无转化价值与低俗垃圾，自动拦截静默不打扰】", TEXT_FAINT),
    ]
    y = 76
    for title, input_text, output_text, color in scenarios:
        draw.rounded_rectangle([500, y, 1232, y + 130], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71))
        # 左侧彩色小指示条 (与卡片边框浑然一体)
        draw.rounded_rectangle([500, y + 14, 505, y + 116], radius=2, fill=color)
        
        draw.text((524, y + 18), f"[{title}]", fill=color, font=get_font(13, bold=True))
        draw.text((600, y + 18), input_text, fill=WHITE, font=get_font(14, bold=True))
        
        # 回复内容（直接展示，不再外包一层多余的厚重长框）
        draw.text((524, y + 64), output_text, fill=color if color != TEXT_FAINT else TEXT_FAINT, font=get_font(14))
        y += 144
        
    save_dual_posters(im, "07", "AI弹幕回复", "danmu")

# ==========================================
# 08 硬件自适应 (Hardware Adaptive)
# ==========================================
def render_poster_08():
    im, draw = create_base_16x9_canvas(8, glow_color=EMERALD)
    
    draw.text((48, 76), "● FEATURE 08 · 硬件算力自适应", fill=EMERALD, font=get_font(13, bold=True))
    draw.text((48, 115), "不同显卡算力", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "自动匹配最佳发声", fill=EMERALD, font=get_font(34, bold=True))
    draw.text((48, 218), "8G+ 拟真 · 4G+ 轻量 · 集显文字回复", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：单一大卡片
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, 290), "● 系统开机自动硬件探测", fill=CYAN, font=get_font(17, bold=True))
    
    specs = [
        ("零繁琐手工配置", "软件启动瞬间自动获取显存容量与算力架构。"),
        ("拒绝爆显存闪退", "依据可用显存自动锁定最佳模型，直播稳如磐石。"),
        ("老旧电脑焕新生", "哪怕只有轻薄本集显，也能调用 Playwright 打字。"),
    ]
    y = 340
    for stitle, sdesc in specs:
        draw.ellipse([74, y + 4, 82, y + 12], fill=EMERALD)
        draw.text((96, y), stitle, fill=WHITE, font=get_font(14, bold=True))
        draw.text((96, y + 26), sdesc, fill=TEXT_MUTED, font=get_font(12))
        y += 82
        
    draw.line([(72, 595), (446, 595)], fill=(28, 40, 62))
    draw.text((72, 612), "● 智能选定匹配模式 · 彻底告别爆显存与死机", fill=EMERALD, font=get_font(12, bold=True))
    
    # 右栏：3 档硬件算力（将厚重粗苯的纯色色块条替换为精致声学仪轨）
    tiers = [
        ("FLAGSHIP 旗舰档 (显存 ≥ 8GB)", "IndexTTS 拟真声音克隆", "具备顶级声音克隆还原能力，语气逼真、情感丰满，声线与顶级真人主播无异。", VIOLET, "RTX 3070 / 4070 / 4090+", 0.95),
        ("EFFICIENT 轻量档 (4GB ≤ 显存 < 8GB)", "MOSS-TTS-Nano 高性能低开销", "专为独显轻薄本与中端工作站深度优化，极速推理低显存占用，音色清澈自然。", EMERALD, "RTX 3050 / 2060 / GTX 1660", 0.65),
        ("LIGHTWEIGHT 极速档 (集显 / 低算力)", "Playwright 网页端自动化公屏打字", "无需任何独立显卡，通过浏览器驱动在公屏打字互动，低成本设备人人体面开播。", CYAN, "轻薄本 / 核显 / 旧电脑", 0.30),
    ]
    y = 76
    for title, eng_name, desc, color, gpu, ratio in tiers:
        draw.rounded_rectangle([500, y, 1232, y + 176], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71))
        draw.text((524, y + 22), title, fill=color, font=get_font(13, bold=True))
        draw.text((524, y + 48), eng_name, fill=WHITE, font=get_font(19, bold=True))
        
        draw.rounded_rectangle([1030, y + 18, 1208, y + 48], radius=8, fill=(28, 40, 62), outline=color)
        draw.text((1119, y + 33), gpu, fill=color, font=get_font(11, bold=True), anchor="mm")
        
        draw.text((524, y + 90), desc, fill=TEXT_MUTED, font=get_font(13))
        
        # 仪表轨 (6px 优雅发光细线，带显存百分比标注，不再是无意义的空心大方框)
        bar_x1, bar_y, bar_x2 = 524, y + 146, 1208
        draw.line([(bar_x1, bar_y), (bar_x2, bar_y)], fill=(28, 40, 62), width=4)
        active_w = int((bar_x2 - bar_x1) * ratio)
        draw.line([(bar_x1, bar_y), (bar_x1 + active_w, bar_y)], fill=color, width=4)
        y += 194
        
    save_dual_posters(im, "08", "硬件自适应", "hardware")

# ==========================================
# 09 声音避让 (Algorithmic Ducking)
# ==========================================
def render_poster_09():
    im, draw = create_base_16x9_canvas(9, glow_color=CYAN)
    
    draw.text((48, 76), "● FEATURE 09 · 声学闪避算法", fill=CYAN, font=get_font(13, bold=True))
    draw.text((48, 115), "主副双声并存", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "纯算法优雅避让", fill=CYAN, font=get_font(34, bold=True))
    draw.text((48, 218), "WASAPI 毫秒级闪避至 25% · 绝不抢话", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：一体化技术原理解析大卡 (彻底废除 3 个零碎框 + 1 个底部压扁框)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 288), "● 广播级声学闪避优势", fill=WHITE, font=get_font(16, bold=True))
    
    benefits = [
        ("纯软件算法调度", "通过 Windows WASAPI 声卡会话衰减，不改手机音量，保护麦克风。"),
        ("60ms 极速平滑淡入", "绝无粗暴突兀的断音或爆音感，主副声音自然并存，电台级听感。"),
        ("120ms 丝滑平稳复原", "弹幕回复结束瞬间，主讲口播声平滑拉升回 100%，连贯流畅绝不冷场。"),
    ]
    y = 330
    for atitle, adesc in benefits:
        draw.ellipse([74, y + 4, 82, y + 12], fill=CYAN)
        draw.text((96, y), atitle, fill=WHITE, font=get_font(15, bold=True))
        draw.text((96, y + 26), adesc, fill=TEXT_MUTED, font=get_font(12))
        draw.line([(72, y + 74), (446, y + 74)], fill=(28, 40, 62))
        y += 88
        
    draw.text((72, 606), "● 彻底告别生硬机械中断 · 保护主播口播连贯性", fill=EMERALD, font=get_font(12, bold=True))
    
    # 右栏：波形时序大卡片 (优化垂直间距与底部时序流指示栏)
    draw.rounded_rectangle([500, 76, 1232, 648], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71), width=1)
    draw.text((524, 106), "● 广播级双声波形闪避时序图 (WASAPI Software Ducking)", fill=WHITE, font=get_font(17, bold=True))
    
    # 曲线 1：豆包主讲话术音量
    draw.text((524, 150), "① 豆包主话术音量 (平时 100%) -> 弹幕来时闪避下凹至 25% -> 平滑复原", fill=EMERALD, font=get_font(13, bold=True))
    pts1 = [
        (524, 230), (680, 230),
        (720, 235), (760, 310), (780, 315),
        (1000, 315), (1020, 310), (1060, 235),
        (1208, 230)
    ]
    for i in range(len(pts1) - 1):
        draw.line([pts1[i], pts1[i+1]], fill=EMERALD, width=4)
    draw.text((890, 335), "▼ 自动压低至 25% (不抢话，隐约可听背景口播)", fill=EMERALD, font=get_font(12, bold=True), anchor="mm")
    
    # 曲线 2：弹幕 TTS 音量
    draw.text((524, 385), "② 弹幕 TTS 回复音量 (平时 0%) -> 突发插播 100% -> 播完瞬间归零", fill=VIOLET, font=get_font(13, bold=True))
    pts2 = [
        (524, 500), (760, 500),
        (770, 460), (780, 420),
        (1000, 420), (1010, 460), (1020, 500),
        (1208, 500)
    ]
    for i in range(len(pts2) - 1):
        draw.line([pts2[i], pts2[i+1]], fill=VIOLET, width=4)
    draw.text((890, 442), "▲ 弹幕回复清晰发声 (100% 优先解答)", fill=VIOLET, font=get_font(12, bold=True), anchor="mm")
    
    # 底部时序状态指示条 (不再是空虚的悬浮条，而是带有正规内边距的指标带)
    draw.rectangle([501, 575, 1231, 647], fill=(15, 22, 36))
    draw.line([(501, 575), (1231, 575)], fill=(30, 44, 66))
    draw.text((866, 611), "时序流转：主音量 100% -> 侦测弹幕 TTS 触发 -> 60ms 淡入至 25% -> 播毕 120ms 丝滑拉回 100%", fill=CYAN, font=get_font(13, bold=True), anchor="mm")
    
    save_dual_posters(im, "09", "纯算法声音避让", "ducking")

# ==========================================
# 10 OBS 推流 (OBS Bridge)
# ==========================================
def render_poster_10():
    im, draw = create_base_16x9_canvas(10, glow_color=EMERALD)
    
    draw.text((48, 76), "● FEATURE 10 · 极简推流桥", fill=EMERALD, font=get_font(13, bold=True))
    draw.text((48, 115), "零配置推流", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "OBS 浏览器源一键拉取", fill=EMERALD, font=get_font(32, bold=True))
    draw.text((48, 218), "内置极轻量 HTTP 桥 · 复制链接直接播报", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：单一大卡片 (纵向连接 3 步接入法，消除琐碎框框)
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((72, 288), "● 3 步极速接入 OBS 直播间", fill=WHITE, font=get_font(16, bold=True))
    
    steps = [
        ("01", "复制音频直链", "在智播豆界面点击【复制】专属本地音频流地址"),
        ("02", "添加浏览器源", "打开 OBS 来源列表，点击【+】号选择【浏览器】"),
        ("03", "勾选音频控制", "粘贴 URL 并勾选【通过 OBS 控制音频】瞬间出声"),
    ]
    y = 330
    for num, stitle, sdesc in steps:
        draw.ellipse([74, y + 2, 98, y + 26], fill=(24, 35, 54), outline=CYAN, width=2)
        draw.text((86, y + 14), num, fill=CYAN, font=get_font(11, bold=True, en_only=True), anchor="mm")
        draw.text((112, y), stitle, fill=WHITE, font=get_font(15, bold=True))
        draw.text((112, y + 28), sdesc, fill=TEXT_MUTED, font=get_font(12))
        draw.line([(72, y + 74), (446, y + 74)], fill=(28, 40, 62))
        y += 88
        
    draw.text((72, 606), "● 完美支持 OBS / 抖音直播伴侣 / 视频号助手", fill=EMERALD, font=get_font(12, bold=True))
    
    # 右栏：HTTP 桥接卡片 (高度对称严整)
    draw.rounded_rectangle([500, 76, 1232, 250], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((524, 102), "● 内置极轻量 HTTP + SSE 实时音频流服务", fill=WHITE, font=get_font(17, bold=True))
    
    # URL 复制条
    draw.rounded_rectangle([524, 136, 1208, 196], radius=10, fill=(15, 22, 36), outline=CYAN, width=1)
    draw.text((544, 166), "http://127.0.0.1:8554/danmu_audio", fill=CYAN, font=get_font(18, bold=True), anchor="lm")
    draw.rounded_rectangle([1100, 146, 1195, 186], radius=8, fill=EMERALD)
    draw.text((1147, 166), "复制链接", fill=WHITE, font=get_font(13, bold=True), anchor="mm")
    
    draw.text((524, 218), "状态：● 本地音频推流微服务已就绪 · HTML5 Audio 极速直连 · 0 编解码损耗", fill=EMERALD, font=get_font(12, bold=True))
    
    # 下方方案对比 (左右严格等宽 356px，间距 20px，完全对称)
    draw.rounded_rectangle([500, 270, 856, 648], radius=14, fill=(28, 20, 24), outline=(60, 30, 40))
    draw.text((678, 300), "[传统推流方案]", fill=RED, font=get_font(15, bold=True), anchor="mm")
    draw.text((524, 342), "· 必须安装笨重 FFmpeg (近 300MB)", fill=TEXT_MUTED, font=get_font(13))
    draw.text((524, 392), "· 命令行管道转流，CPU 占用高易断流", fill=RED, font=get_font(13))
    draw.text((524, 442), "· 复杂的编解码参数配置，新手易出错", fill=TEXT_MUTED, font=get_font(13))
    draw.text((524, 492), "· 端口冲突与网络防火墙拦截风险高", fill=RED, font=get_font(13))
    draw.text((524, 542), "· 经常遇到声画不同步或单声道杂音", fill=TEXT_MUTED, font=get_font(13))
    
    draw.rounded_rectangle([876, 270, 1232, 648], radius=14, fill=(18, 32, 36), outline=(20, 80, 70))
    draw.text((1054, 300), "[智播豆浏览器源方案]", fill=EMERALD, font=get_font(15, bold=True), anchor="mm")
    draw.text((900, 342), "· 纯 Python 微型内置服务，零外部依赖", fill=WHITE, font=get_font(13))
    draw.text((900, 392), "· OBS 原生浏览器沙箱播放，极其稳定", fill=EMERALD, font=get_font(13))
    draw.text((900, 442), "· 单击复制即用，小白 10 秒轻松上手", fill=WHITE, font=get_font(13))
    draw.text((900, 492), "· 内存开销极低，通宵开播永不掉线", fill=EMERALD, font=get_font(13))
    draw.text((900, 542), "· 广播级立体声输出，音质清澈悦耳", fill=WHITE, font=get_font(13))
    
    save_dual_posters(im, "10", "OBS推流", "obs")

# ==========================================
# 11 矩阵降本 (Multi Device Matrix ROI)
# ==========================================
def render_poster_09_matrix():
    im, draw = create_base_16x9_canvas(11, glow_color=CYAN)
    
    draw.text((48, 76), "● FEATURE 11 · 矩阵商业价值", fill=CYAN, font=get_font(13, bold=True))
    draw.text((48, 115), "一人管控多机矩阵", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "降低 90% 人力成本", fill=CYAN, font=get_font(34, bold=True))
    draw.text((48, 218), "24 小时不间断开播 · 矩阵式带货 · 运营成本归零", fill=TEXT_MUTED, font=get_font(15, bold=True))
    
    # 左栏：单一大卡片
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(15, 22, 36), outline=(30, 44, 66))
    draw.text((72, 288), "● 为什么电商卖家全面拥抱智播豆？", fill=EMERALD, font=get_font(16, bold=True))
    
    points = [
        ("拯救闲置安卓手机", "旧手机插上线直接投屏变身带货主机，废物利用创造增量利润。"),
        ("抢占凌晨黄金流量", "夜间 00:00 - 06:00 竞品下播，智播豆 24 小时抢收冷门高转化流量。"),
        ("矩阵极速裂变扩张", "单机跑通直接复制 5~10 台，快速形成全网直播轰炸矩阵。"),
    ]
    y = 335
    for ptitle, pdesc in points:
        draw.ellipse([74, y + 4, 82, y + 12], fill=CYAN)
        draw.text((96, y), ptitle, fill=WHITE, font=get_font(14, bold=True))
        draw.text((96, y + 26), pdesc, fill=TEXT_MUTED, font=get_font(12))
        y += 82
        
    draw.line([(72, 595), (446, 595)], fill=(28, 40, 62))
    draw.text((72, 612), "● 投资回报率 (ROI) 提升 400% 以上", fill=WHITE, font=get_font(12, bold=True))
    
    # 右栏：正规现代数据表格 (彻底废除 5 个独立悬浮方块，重构为专业彭博/特斯拉风格数据行)
    draw.rounded_rectangle([500, 76, 1232, 648], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((524, 102), "● 传统人工直播团队 vs 智播豆 AI 矩阵中控", fill=WHITE, font=get_font(17, bold=True))
    
    # 表头分割线
    draw.line([(524, 138), (1208, 138)], fill=(34, 49, 71), width=1)
    
    rows = [
        ("人力配备", "3~4人 / 间 (主播+中控+场控)", "1人 看管 5~10 台直播手机", RED, EMERALD),
        ("单月支出", "¥ 30,000 ~ 50,000 / 月", "极低电力与算力消耗，近乎为零", RED, EMERALD),
        ("开播时长", "每天 4~6 小时，极易疲劳", "7 × 24 小时通宵不间断带货", RED, EMERALD),
        ("话术质量", "依赖主播发挥，情绪波动大", "金牌爆款话术，稳定持续输出", RED, EMERALD),
        ("起号成本", "招人难、培训慢、离职即停播", "随开随播，支持快速多账号测品", RED, EMERALD),
    ]
    y = 152
    for i, (item, trad, zbd, c1, c2) in enumerate(rows):
        # 奇偶行微妙底色交替，极具高级感
        if i % 2 == 1:
            draw.rectangle([501, y, 1231, y + 70], fill=(15, 22, 36, 140))
        draw.text((544, y + 35), item, fill=WHITE, font=get_font(15, bold=True), anchor="lm")
        draw.text((680, y + 35), trad, fill=c1, font=get_font(14), anchor="lm")
        draw.text((1188, y + 35), zbd, fill=c2, font=get_font(15, bold=True), anchor="rm")
        draw.line([(524, y + 70), (1208, y + 70)], fill=(28, 40, 62))
        y += 72
        
    # 底部总结条
    draw.rectangle([501, 580, 1231, 647], fill=(15, 22, 36))
    draw.line([(501, 580), (1231, 580)], fill=(30, 44, 66))
    draw.text((866, 613), "降本：省去高昂人工薪资与试错成本   |   增效：全天候矩阵带货释放海量利润", fill=EMERALD, font=get_font(13, bold=True), anchor="mm")
    
    save_dual_posters(im, "11", "矩阵降本", "matrix")

# ==========================================
# 12 CTA 行动收束 (Closing & CTA)
# ==========================================
def render_poster_12():
    im, draw = create_base_16x9_canvas(12, glow_color=EMERALD)
    
    draw.text((48, 76), "● CLOSING · 开启智能直播新纪元", fill=EMERALD, font=get_font(13, bold=True))
    draw.text((48, 115), "开启您的 AI 智能", fill=WHITE, font=get_font(38, bold=True))
    draw.text((48, 168), "直播新纪元", fill=EMERALD, font=get_font(34, bold=True))
    draw.text((48, 218), "智播豆 · 立即部署 · 释放无限商业潜能", fill=CYAN, font=get_font(15, bold=True))
    
    # 左栏：一体化行动号召大卡
    draw.rounded_rectangle([48, 260, 470, 648], radius=16, fill=(15, 22, 36), outline=EMERALD, width=2)
    draw.text((259, 310), "● 抢占先机 · 开启全天候带货", fill=WHITE, font=get_font(19, bold=True), anchor="mm")
    draw.text((259, 350), "无需经验 · 现成方案 · 专属技术支持", fill=TEXT_MUTED, font=get_font(13), anchor="mm")
    
    # CTA 主行动按钮
    draw.rounded_rectangle([88, 395, 430, 465], radius=14, fill=EMERALD)
    draw.text((259, 430), "立即体验 · 预约演示", fill=WHITE, font=get_font(18, bold=True), anchor="mm")
    
    pros = [
        "· 完善的工程源码交付，开箱即用",
        "· 专属售后技术对接，一对一指导",
        "· 终身版本持续迭代，功能常用常新",
    ]
    y = 500
    for p in pros:
        draw.text((88, y), p, fill=TEXT_MUTED, font=get_font(13))
        y += 34
        
    # 右栏：6 大核心硬核能力矩阵 (2列 x 3行，卡片高度从容平衡)
    draw.rounded_rectangle([500, 76, 1232, 648], radius=14, fill=(19, 28, 45, 230), outline=(34, 49, 71))
    draw.text((524, 102), "● 智播豆 6 大硬核能力全景矩阵", fill=WHITE, font=get_font(17, bold=True))
    
    abilities = [
        ("1. 实时人数驱动", "进场人数动态驱动区间话术", CYAN),
        ("2. 记事本热重载", "01/02/03.txt 随改随存秒生效", EMERALD),
        ("3. VAD 智能接力", "纯算法语音监听，说完即换", VIOLET),
        ("4. DeepSeek 弹幕", "大模型意图过滤与礼物秒谢", AMBER),
        ("5. 纯算法声音避让", "WASAPI 闪避至25%，主次分明", CYAN),
        ("6. OBS 浏览器直推", "极轻量 HTTP 桥，一键拉流", EMERALD),
    ]
    bw = (732 - 48 - 20) // 2
    for i, (atitle, adesc, acolor) in enumerate(abilities):
        col = i % 2
        row = i // 2
        ax = 524 + col * (bw + 20)
        ay = 145 + row * 158
        draw.rounded_rectangle([ax, ay, ax + bw, ay + 140], radius=12, fill=(15, 22, 36), outline=(30, 44, 66))
        draw.text((ax + 20, ay + 26), atitle, fill=acolor, font=get_font(16, bold=True))
        draw.text((ax + 20, ay + 68), adesc, fill=TEXT_MUTED, font=get_font(13))
        draw.text((ax + 20, ay + 102), "● 自动化深度适配", fill=WHITE, font=get_font(11))
        
    save_dual_posters(im, "12", "CTA收束", "cta")

if __name__ == "__main__":
    print("Starting optimized widescreen rendering (calibrated layouts)...")
    render_poster_01()
    render_poster_02()
    render_poster_03()
    render_poster_04()
    render_poster_05()
    render_poster_06()
    render_poster_07()
    render_poster_08()
    render_poster_09()
    render_poster_10()
    render_poster_09_matrix()
    render_poster_12()
    print("All 12 calibrated widescreen posters successfully rendered!")
