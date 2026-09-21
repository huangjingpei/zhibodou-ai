# ====================== 直播平台域名识别 ======================
# 平台类型由 URL 域名自动判断（danma 采集器内部同样按域名分流），
# 因此 UI 不再需要"弹幕平台"下拉框，只保留直播间地址输入。
# 本模块保持零重依赖，可安全在 UI 主线程导入。
def detect_platform(url: str) -> str:
    """根据直播间 URL 域名推断平台标识；无法识别时回退 douyin。"""
    low = (url or "").lower()
    if "douyin.com" in low:
        return "douyin"
    if "bilibili.com" in low or "b23.tv" in low:
        return "bilibili"
    if "kuaishou.com" in low:
        return "kuaishou"
    if "tiktok.com" in low:
        return "tiktok"
    if "xiaohongshu.com" in low or "xhslink.com" in low:
        return "xhs"
    if "taobao.com" in low:
        return "tb"
    if "pinduoduo.com" in low or "yangkeduo.com" in low:
        return "pdd"
    if "facebook.com" in low:
        return "facebook"
    if "nimo.tv" in low:
        return "nimo"
    if "channels.weixin.qq.com" in low:
        return "shipinhao"
    return "douyin"
