"""多平台直播流解析服务 (基于 StreamGet 引擎)。

集成 ihmily/streamget 开源库，支持国内外 40+ 主流直播平台：
- 国内：抖音、快手、哔哩哔哩、虎牙直播、斗鱼直播、小红书、YY、淘宝直播、京东直播、微博直播、网易CC等
- 国际：TikTok、Twitch、YouTube、SOOP (AfreecaTV)、CHZZK、ShowRoom、LiveMe等

支持解析多种清晰度（原画 OD、超清 UHD、高清 HD、标清 SD、流畅 LD）与流格式（FLV / M3U8）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 确保优先加载本地 src/streamget 源码
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
_streamget_local_dir = os.path.join(_project_root, "streamget")
if os.path.isdir(_streamget_local_dir) and _streamget_local_dir not in sys.path:
    sys.path.insert(0, _streamget_local_dir)

try:
    import streamget
    from streamget import (
        AcfunLiveStream,
        BaiduLiveStream,
        BigoLiveStream,
        BilibiliLiveStream,
        BluedLiveStream,
        ChangliaoLiveStream,
        ChzzkLiveStream,
        DouyinLiveStream,
        DouyuLiveStream,
        FaceitLiveStream,
        FlexTVLiveStream,
        HaixiuLiveStream,
        HuajiaoLiveStream,
        HuamaoLiveStream,
        HuyaLiveStream,
        InkeLiveStream,
        JDLiveStream,
        KugouLiveStream,
        KwaiLiveStream,
        LaixiuLiveStream,
        LangLiveStream,
        LehaiLiveStream,
        LianJieLiveStream,
        LiveMeLiveStream,
        LookLiveStream,
        MaoerLiveStream,
        MiguLiveStream,
        NeteaseLiveStream,
        PandaLiveStream,
        PiaopaioLiveStream,
        PicartoLiveStream,
        PopkonTVLiveStream,
        QiandureboLiveStream,
        RedNoteLiveStream,
        ShopeeLiveStream,
        ShowRoomLiveStream,
        SixRoomLiveStream,
        SoopLiveStream,
        StreamData,
        TaobaoLiveStream,
        TikTokLiveStream,
        TwitCastingLiveStream,
        TwitchLiveStream,
        VVXQLiveStream,
        WeiboLiveStream,
        WinkTVLiveStream,
        XindongreboLiveStream,
        YYLiveStream,
        YinboLiveStream,
        YiqiLiveStream,
        YoutubeLiveStream,
        ZhihuLiveStream,
    )
    _STREAMGET_AVAILABLE = True
except Exception as e:
    logger.warning(f"导入 streamget 模块失败: {e}")
    _STREAMGET_AVAILABLE = False


# 平台路由表：(匹配正则/关键词列表, 中文名, 平台类)
PLATFORM_ROUTERS: List[Tuple[List[str], str, Any]] = []

if _STREAMGET_AVAILABLE:
    PLATFORM_ROUTERS = [
        (["douyin.com", "iesdouyin.com", "v.douyin.com"], "抖音直播", DouyinLiveStream),
        (["kuaishou.com", "gifshow.com", "kwai.com", "v.kuaishou.com"], "快手直播", KwaiLiveStream),
        (["bilibili.com", "b23.tv", "live.bilibili.com"], "哔哩哔哩", BilibiliLiveStream),
        (["huya.com"], "虎牙直播", HuyaLiveStream),
        (["douyu.com"], "斗鱼直播", DouyuLiveStream),
        (["xiaohongshu.com", "xhslink.com"], "小红书直播", RedNoteLiveStream),
        (["tiktok.com"], "TikTok", TikTokLiveStream),
        (["twitch.tv"], "Twitch", TwitchLiveStream),
        (["youtube.com", "youtu.be"], "YouTube Live", YoutubeLiveStream),
        (["yy.com"], "YY直播", YYLiveStream),
        (["taobao.com", "tb.cn"], "淘宝直播", TaobaoLiveStream),
        (["jd.com"], "京东直播", JDLiveStream),
        (["weibo.com", "weibo.cn", "yizhibo.com"], "微博直播", WeiboLiveStream),
        (["cc.163.com"], "网易CC直播", NeteaseLiveStream),
        (["look.163.com"], "Look直播", LookLiveStream),
        (["acfun.cn"], "AcFun直播", AcfunLiveStream),
        (["live.baidu.com", "baidu.com"], "百度直播", BaiduLiveStream),
        (["bigo.tv"], "Bigo Live", BigoLiveStream),
        (["blued.cn", "blued.com"], "Blued直播", BluedLiveStream),
        (["huajiao.com"], "花椒直播", HuajiaoLiveStream),
        (["inke.cn"], "映客直播", InkeLiveStream),
        (["fanxing.kugou.com", "kugou.com"], "酷狗繁星", KugouLiveStream),
        (["6.cn"], "六间房直播", SixRoomLiveStream),
        (["liveme.com"], "LiveMe", LiveMeLiveStream),
        (["missevan.com"], "猫耳FM", MaoerLiveStream),
        (["showroom-live.com"], "ShowRoom", ShowRoomLiveStream),
        (["sooplive.co.kr", "afreecatv.com"], "SOOP (AfreecaTV)", SoopLiveStream),
        (["chzzk.naver.com"], "CHZZK", ChzzkLiveStream),
        (["zhihu.com"], "知乎直播", ZhihuLiveStream),
        (["flextv.co.kr"], "FlexTV", FlexTVLiveStream),
        (["popkontv.com"], "PopkonTV", PopkonTVLiveStream),
        (["twitcasting.tv"], "TwitCasting", TwitCastingLiveStream),
        (["shopee.com", "shopee.tw", "shopee.vn", "shopee.th"], "Shopee Live", ShopeeLiveStream),
        (["faceit.com"], "FACEIT", FaceitLiveStream),
        (["haixiu.com"], "嗨秀直播", HaixiuLiveStream),
        (["huamao.tv"], "花猫直播", HuamaoLiveStream),
        (["laixiu.com"], "来秀直播", LaixiuLiveStream),
        (["lang.live"], "浪Live", LangLiveStream),
        (["lehaitv.com"], "乐嗨直播", LehaiLiveStream),
        (["lianjie.com"], "连接直播", LianJieLiveStream),
        (["pandalive.co.kr"], "PandaTV", PandaLiveStream),
        (["picarto.tv"], "Picarto", PicartoLiveStream),
        (["vvxq.com"], "VV星球", VVXQLiveStream),
        (["yinbo365.com"], "音播直播", YinboLiveStream),
        (["17.live"], "17Live", YiqiLiveStream),
        (["changliao.com"], "畅聊直播", ChangliaoLiveStream),
    ]

# 清晰度标准代码与中文映射
QUALITY_NAMES = {
    "OD": "原画 (OD)",
    "UHD": "超清 (UHD)",
    "HD": "高清 (HD)",
    "SD": "标清 (SD)",
    "LD": "流畅 (LD)",
}


def detect_platform(url: str) -> Tuple[Optional[str], Optional[Any]]:
    """根据 URL 自动识别平台中文名与对应的解析类。"""
    if not url:
        return None, None
    low_url = url.lower().strip()
    for patterns, name, cls in PLATFORM_ROUTERS:
        for p in patterns:
            if p in low_url:
                return name, cls
    return None, None


async def async_parse_stream(url: str, cookies: str = None, proxy: str = None) -> Dict[str, Any]:
    """异步解析直播间各清晰度流地址。

    :param url: 直播间网页地址或分享链接
    :param cookies: 可选的自定义 Cookie
    :param proxy: 可选的代理地址
    :return: 解析结果字典
    """
    if not _STREAMGET_AVAILABLE:
        return {
            "success": False,
            "message": "StreamGet 模块未正确安装或导入失败，请检查环境依赖",
        }

    url = (url or "").strip()
    if not url:
        return {"success": False, "message": "请输入有效的直播间地址"}

    platform_name, stream_cls = detect_platform(url)
    if stream_cls is None:
        return {
            "success": False,
            "message": f"未能识别该直播间所属平台（已支持 40+ 主流平台，请检查链接格式）: {url}",
        }

    try:
        handler = stream_cls(proxy_addr=proxy, cookies=cookies)
        # 获取直播间基础数据
        raw_data = await handler.fetch_web_stream_data(url)
        if not raw_data:
            return {
                "success": False,
                "platform": platform_name,
                "message": f"获取【{platform_name}】直播间信息返回为空，主播可能未开播或链接已失效",
            }

        # 归一化主播名与标题
        anchor_name = (
            raw_data.get("anchor_name")
            or raw_data.get("nickname")
            or raw_data.get("uname")
            or raw_data.get("anchor")
            or "未知主播"
        )
        title = raw_data.get("title") or raw_data.get("room_title") or "（无直播标题）"
        is_live = bool(raw_data.get("is_live", raw_data.get("live_status", False)))

        # 抖音平台状态判定特殊处理（status==2 为直播中）
        if "status" in raw_data and isinstance(raw_data["status"], int):
            is_live = (raw_data["status"] == 2)

        streams: Dict[str, Dict[str, str]] = {}
        target_qualities = ["OD", "UHD", "HD", "SD", "LD"]

        # 遍历解析各清晰度
        for q in target_qualities:
            try:
                stream_obj = await handler.fetch_stream_url(raw_data, q)
                if stream_obj is None:
                    continue

                flv = getattr(stream_obj, "flv_url", None)
                m3u8 = getattr(stream_obj, "m3u8_url", None)

                # 如果返回的是 dict 结构
                if isinstance(stream_obj, dict):
                    flv = stream_obj.get("flv_url")
                    m3u8 = stream_obj.get("m3u8_url")

                if flv or m3u8:
                    streams[q] = {
                        "flv": str(flv) if flv else "",
                        "m3u8": str(m3u8) if m3u8 else "",
                    }
                    if not is_live:
                        # 若成功提取到了流地址，则实质上已在直播
                        is_live = True
            except Exception as q_err:
                logger.debug(f"解析清晰度 {q} 失败: {q_err}")
                continue

        if not streams and not is_live:
            return {
                "success": True,
                "platform": platform_name,
                "anchor_name": anchor_name,
                "title": title,
                "is_live": False,
                "streams": {},
                "available_qualities": [],
                "available_formats": [],
                "default_url": "",
                "message": f"【{platform_name}】主播当前未开播",
            }

        if not streams:
            return {
                "success": False,
                "platform": platform_name,
                "anchor_name": anchor_name,
                "title": title,
                "is_live": is_live,
                "message": f"【{platform_name}】未能提取到可用流地址，可能需要特定 Cookie 或平台流协议加密",
            }

        # 提取可用清晰度与可用格式
        available_qualities = [q for q in target_qualities if q in streams]
        has_flv = any(bool(s.get("flv")) for s in streams.values())
        has_m3u8 = any(bool(s.get("m3u8")) for s in streams.values())
        available_formats = []
        if has_flv:
            available_formats.append("FLV")
        if has_m3u8:
            available_formats.append("M3U8")

        # 默认流：优先选择原画 OD 或第一个可用清晰度，格式优先 FLV (更低延迟) 否则 M3U8
        first_q = available_qualities[0] if available_qualities else "OD"
        def_stream = streams.get(first_q, {})
        default_url = def_stream.get("flv") or def_stream.get("m3u8") or ""

        return {
            "success": True,
            "platform": platform_name,
            "anchor_name": anchor_name,
            "title": title,
            "is_live": is_live,
            "streams": streams,
            "available_qualities": available_qualities,
            "available_formats": available_formats,
            "default_quality": first_q,
            "default_format": "FLV" if def_stream.get("flv") else "M3U8",
            "default_url": default_url,
            "message": f"成功解析【{platform_name}】直播流，共 {len(available_qualities)} 个清晰度档位",
        }

    except Exception as e:
        logger.exception(f"解析直播流异常: {e}")
        return {
            "success": False,
            "platform": platform_name,
            "message": f"解析失败: {e}",
        }


def parse_stream(url: str, cookies: str = None, proxy: str = None) -> Dict[str, Any]:
    """同步阻塞解析直播间流地址（内部启动事件循环），安全供后台线程调用。"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(async_parse_stream(url, cookies=cookies, proxy=proxy))
        finally:
            loop.close()
    except Exception as e:
        return {"success": False, "message": f"运行解析器发生错误: {e}"}
