import json
import os
import random
import shutil
import sys
import threading
import time
import traceback
import winreg
from pathlib import Path

from playwright.sync_api import sync_playwright as playwright

# 兼容“python src/danma/main.py”与客户端内“import danma.main”两种入口。
_DANMA_DIR = os.path.dirname(os.path.abspath(__file__))
if _DANMA_DIR not in sys.path:
    sys.path.insert(0, _DANMA_DIR)

from live_plate.Message import CreatSystemMessage
from live_plate.bili.bilili import decode_packet
from live_plate.douyin.dy import douyin_pb, douyin_pb2
from live_plate.kuaishou.ks import kuaishou_pb
from live_plate.nimo.nimo_tars import nimo_tars
from live_plate.tiktok.tk import tiktok_pb, tiktok_pb2
from live_plate.facebook.facebook import ParseFaceBookComment
from live_plate.pdd.pdd import pdd_pb,Pdd
from live_plate.vx.vx import ParseVxMessage
from live_plate.xhs.xhs import Xhs
from live_plate.tb.tb import Tb

class DanmuBrowserCollector:
    def __init__(
        self,
        platform="douyin",
        url="",
        headless=True,
        user_data_dir=None,
        chrome_path=None,
        message_callback=None,
        log_fn=print,
        online_only=False,
    ):
        super().__init__()
        self.platform = str(platform or "douyin").strip().lower()
        self.url = str(url or "").strip().strip("'\"")
        self.headless = bool(headless)
        self.user_data_dir = user_data_dir
        self.chrome_path = chrome_path
        self.message_callback = message_callback
        self.log_fn = log_fn
        # 仅统计指标模式（打开浏览器但不采弹幕文本）：浏览器照常打开并保持
        # WS/HTTP 监听，在 PostMessage 统一出口处丢弃弹幕文本类消息
        # （Chat/Member/Social），只放行三个统计指标：
        # RoomMessage(实时在线) / LikeMessage(累计点赞) / GiftMessage(礼物互动)
        # 以及 SystemMessage/CollectorStatus（状态流转必需）。
        self.online_only = bool(online_only)
        self._stop_event = threading.Event()
        self.browser = None
        self.page = None
        self.lock = threading.RLock()
        self.vx_gift_count = {}
        self.vx_person = {}
        self.vx_person_url = {}
        self.ParseTbMessage = Tb().ParseTbComment
        self.ParsePddMessage = Pdd().pdd_pb
        self.ParseXhsMessage = Xhs().ParseXhsComment
        self.ParseXhsShopMessage = Xhs().ParseXhsShopComment

    def getUserData(self):
        if self.user_data_dir:
            return os.path.abspath(os.path.expandvars(self.user_data_dir))
        local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home())
        return os.path.join(local_app_data, "Zhibodou", "DanmuBrowserProfile")

    def browser_launch(self):
        """
        # =====================================
        # 启动浏览器,进行监听
        # =====================================
        :param url:直播间地址
        :return
        """
        if not self.url:
            self.PostMessage([CreatSystemMessage("未配置直播间地址")])
            return
        self._stop_event.clear()
        result = checkChrome(self.chrome_path).check()
        self.PostMessage([CreatSystemMessage(result['tips'])])
        if not result['status']:
            return

        try:
            user_agent = None
            if 'v.kuaishou.com' in self.url:
                user_agent = "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36"
            with playwright() as pw:

                try:
                    launch_options = {
                        "user_data_dir": self.getUserData(),
                        "user_agent": user_agent,
                        "headless": self.headless,
                        "viewport": {"width": 1280, "height": 720} if self.headless else None,
                        "args": [
                            "--disable-blink-features=AutomationControlled",
                            "--autoplay-policy=no-user-gesture-required",
                            "--mute-audio",
                            "--disable-dev-shm-usage",
                        ],
                    }
                    if self.headless:
                        launch_options["args"].append("--disable-gpu")
                    if result.get('path'):
                        launch_options["executable_path"] = result['path']
                    self.browser = pw.chromium.launch_persistent_context(**launch_options)

                except Exception as error:
                    self.PostMessage([CreatSystemMessage(f"浏览器启动失败：{error}")])
                    return

                pages = self.browser.pages
                self.page = pages[0] if pages else self.browser.new_page()

                # 拦截媒体流与重型静态资源，避免无头浏览器解码 4K/1080P 视频导致 CPU 飙升与带宽浪费
                def block_heavy_resources(route):
                    try:
                        req = route.request
                        res_type = req.resource_type
                        low_url = req.url.lower()
                        if res_type in ("image", "media", "font"):
                            route.abort()
                            return
                        if any(ext in low_url for ext in (
                            ".flv", ".m3u8", ".ts", ".mp4", ".m4s", ".webm",
                            ".aac", ".mp3", ".wav", ".woff", ".woff2", ".ttf", ".otf"
                        )):
                            route.abort()
                            return
                        route.continue_()
                    except Exception:
                        try:
                            route.continue_()
                        except Exception:
                            pass

                self.page.route("**/*", block_heavy_resources)
                self.page.on("websocket", self.wss)
                self.page.on("response", self.http)
                self.page.on("load", self.execute_js)

                self.page.goto(self.url, timeout=60000, wait_until="domcontentloaded")
                self.PostMessage([CreatSystemMessage(
                    ("采集页面已启动（headless 无头模式）" if self.headless else "采集页面已启动（可见模式）")
                    + f"：{self.page.url}"
                )])
                last_refresh = time.monotonic()
                while not self._stop_event.is_set():
                    self.page.wait_for_timeout(500)
                    if time.monotonic() - last_refresh >= 30 * 60:
                        self.page.reload(timeout=60000, wait_until="domcontentloaded")
                        last_refresh = time.monotonic()

        except Exception as error:
            if 'playwright install chrome' in str(error):
                self.PostMessage([CreatSystemMessage(content='请安装google')])
            else:
                self.PostMessage([CreatSystemMessage(content=f'采集器异常：{error}')])
        finally:
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                pass
            self.browser = None
            self.page = None
    def execute_js(self, _event=None):
        """页面保活：移除遮罩、自动点播放/继续播放。

        注意：本函数挂在 page.on("load") 回调上，任何异常都会打崩 Playwright
        的同步事件循环（greenlet 损坏后 WS 帧回调全部失联，表现为采集器
        "在运行但永远收不到消息"），因此这里必须整体 try/except 兜底。
        """
        if self._stop_event.is_set() or self.page is None:
            return
        try:
            self.page.evaluate("document.title = '请勿关闭';")
        except Exception as error:
            self.log_fn(f"设置页面标题失败: {error}")
        if 'douyin' in (self.page.url or ''):
            try:
                self.page.evaluate("""
                    (() => {
                        setInterval(() => {
                            try {
                                document.querySelectorAll('.__hasOptionBar').forEach((e) => e.remove());
                            } catch (err) {}
                        }, 5000);

                        // 自动点击播放按钮（autoplay 被拦时的兜底）
                        setInterval(() => {
                            try {
                                const playButton = document.querySelector('.JL05k7eS.OG51D9OO');
                                if (playButton) {
                                    playButton.dispatchEvent(new MouseEvent('click', {
                                        view: window, bubbles: true, cancelable: true,
                                    }));
                                }
                            } catch (err) {}
                        }, 5000);

                        // 自动点击"继续播放"弹窗
                        setInterval(() => {
                            try {
                                const all = document.getElementsByTagName('*');
                                for (let i = 0; i < all.length; i++) {
                                    if (all[i].textContent && all[i].textContent.trim() === '继续播放') {
                                        all[i].click();
                                        break;
                                    }
                                }
                            } catch (err) {}
                        }, 5000);
                    })()
                """)
            except Exception as error:
                # 注入失败绝不能向外抛，否则事件循环被破坏、WS 帧全部收不到。
                self.log_fn(f"注入保活 JS 失败: {error}")

    def browser_close(self):
        """
        关闭浏览器，失效
        """
        self._stop_event.set()

    def http(self, response):
        """
        # =====================================
        # 启动浏览器,进行监听http
        # =====================================
        :param response:http响应
        :return:
        """
        try:
            if 'webcast/im/fetch' in response.url:
                is_tk = 'tiktok' in response.url or self.platform == 'tiktok' or (self.page and 'tiktok.com' in (self.page.url or ''))
                if is_tk:
                    try:
                        res = tiktok_pb2(data=response.body())
                        self.PostMessage(res)
                    except Exception as e:
                        self.log_fn(f"TikTok HTTP 弹幕解析异常: {e}")
                else:
                    try:
                        res = douyin_pb2(data=response.body())
                        self.PostMessage(res)
                    except Exception as e:
                        self.log_fn(f"抖音 HTTP 弹幕解析异常: {e}")
            elif '/live/msg' in response.url:
                msg = ParseVxMessage(response.json())
                self.PostMessage(msg)
            elif 'mtop.taobao.iliad.comment.query' in response.url or 'mtop.taobao.iliad.live.user.assistant.data.get' in response.url:
                msg = self.ParseTbMessage(response.text())
                self.PostMessage(msg)
        except Exception as error:
            self.log_fn(f"HTTP 响应拦截处理异常: {error}")

    def wss(self, websocket):

        """
        # =====================================
        # 启动浏览器,进行监听websocket
        # =====================================
        :param websocket: websocket响应
        :return:
        """
        try:
            ws_url = websocket.url.lower()
            if self.platform == 'kuaishou' or any(d in ws_url for d in ('kuaishou.com', 'yximgs.com', 'gifshow.com', 'kwai.com', 'kskwai.com')):
                self.log_fn(f"已捕获快手 WebSocket 连接: {websocket.url[:70]}")
                websocket.on('framereceived', self.ks_onmessage)
            elif 'douyin.com/webcast/im/push/' in ws_url or (self.platform == 'douyin' and 'im/push' in ws_url):
                websocket.on('framereceived', self.dy_onmessage)
            elif 'tiktok' in ws_url or 'byteoversea' in ws_url or (self.platform == 'tiktok' and 'im' in ws_url):
                websocket.on('framereceived', self.tk_onemssage)
            elif (
                'live-comet' in ws_url
                or 'broadcastlv' in ws_url
                or (self.platform == 'bilibili' and ('/sub' in ws_url or 'broadcast' in ws_url))
            ) and 'tracker' not in ws_url and 'p2p' not in ws_url and 'stun' not in ws_url:
                self.log_fn(f"已捕获 Bilibili 弹幕 WebSocket 连接: {websocket.url[:70]}")
                websocket.on('framereceived', self.bili_onemssage)
            elif 'ws.master.live' in ws_url:
                websocket.on('framereceived', self.nimo_onmessage)
            elif 'pinduoduo.com' in ws_url or 'yangkeduo.com' in ws_url:
                websocket.on('framereceived', self.pdd_onmessage2)
            elif 'facebook.com/ws/realtime' in ws_url:
                websocket.on('framereceived', self.facebook_onmessage)
            elif 'longlink' in websocket.url:
                websocket.on('framereceived', self.xhs_onmessage)
            elif 'rwp' in websocket.url:
                websocket.on('framereceived', self.xhs_shop_onmessage)
        except Exception as error:
            self.log_fn(f"监听 websocket 出错: {error}")

    def xhs_onmessage(self, framereceived):
        try:
            res = self.ParseXhsMessage(framereceived)
            self.PostMessage(res)
        except Exception as error:
            self.log_fn(f"小红书弹幕解析失败: {error}")

    def xhs_shop_onmessage(self, framereceived):
        try:
            res = self.ParseXhsShopMessage(framereceived)
            self.PostMessage(res)
        except Exception as error:
            self.log_fn(f"小红书商城消息解析失败: {error}")

    def facebook_onmessage(self, framereceived):
        try:
            self.PostMessage(ParseFaceBookComment(framereceived))
        except Exception as error:
            self.log_fn(f"Facebook 弹幕解析失败：{error}")

    def nimo_onmessage(self, framereceived):
        try:
            self.PostMessage(nimo_tars(framereceived))
        except Exception as error:
            self.log_fn(f"Nimo 弹幕解析失败：{error}")

    def bili_onemssage(self, framereceived):
        try:
            if isinstance(framereceived, str):
                # 忽略 WebRTC / P2P 握手控制文本帧
                return
            res = decode_packet(framereceived)
            if res and 'listmessage' in res and res['listmessage']:
                self.PostMessage(res['listmessage'])
        except Exception as e:
            self.log_fn(f"Bilibili 弹幕解析异常: {e}")

    def ks_onmessage(self, framereceived):
        try:
            self.PostMessage(kuaishou_pb(data=framereceived))
        except Exception as error:
            self.log_fn(f"快手弹幕解析失败：{error}")

    def dy_onmessage(self, framereceived):
        try:
            if not self.headless and self.page is not None:
                random_x = random.randint(100, 1000)
                random_y = random.randint(100, 700)
                self.page.mouse.move(random_x, random_y)
            self.PostMessage(douyin_pb(data=framereceived))
        except Exception as error:
            self.log_fn(f"抖音弹幕解析失败：{error}")

    def tk_onemssage(self, framereceived):
        try:
            self.PostMessage(tiktok_pb(data=framereceived))
        except Exception as error:
            self.log_fn(f"TikTok 弹幕解析失败：{error}")

    def pdd_onmessage(self, framereceived):
        try:
            self.PostMessage(pdd_pb(data=framereceived))
        except Exception as error:
            self.log_fn(f"PDD 弹幕解析失败：{error}")
    def pdd_onmessage2(self, framereceived):
        try:
            self.PostMessage(self.ParsePddMessage(data=framereceived))
        except Exception as error:
            self.log_fn(f"PDD 弹幕解析失败：{error}")
    def PostMessage(self, data):
        if not data:
            return
        if self.online_only:
            # 仅统计指标模式：所有平台解码器的输出都经过这里，
            # 在唯一出口统一过滤：丢弹幕文本（Chat/Member/Social），
            # 放行三个统计指标（在线人数/点赞/礼物）与系统状态消息。
            _KEEP_TYPES = ("RoomMessage", "LikeMessage", "GiftMessage",
                           "SystemMessage", "CollectorStatus")
            items = data if isinstance(data, (list, tuple)) else [data]
            filtered = [
                m for m in items
                if isinstance(m, dict)
                and str(m.get("type") or "") in _KEEP_TYPES
            ]
            if not filtered:
                return
            data = filtered
        if self.message_callback:
            try:
                self.message_callback(data)
                return
            except Exception as error:
                self.log_fn(f"弹幕回调失败：{error}")
                return
        print(json.dumps(data, ensure_ascii=False), flush=True)

class checkChrome:
    def __init__(self, preferred_path=None):
        self.preferred_path = preferred_path

    def get_chrome_info(self):
        chrome_info_list = []
        candidates = []
        if self.preferred_path:
            candidates.append((os.path.abspath(os.path.expandvars(self.preferred_path)), "配置的浏览器"))

        # 1. 探测 Google Chrome
        for bin_name in ("chrome", "chrome.exe"):
            w = shutil.which(bin_name)
            if w:
                candidates.append((w, "Chrome"))

        chrome_keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        ]
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key_path in chrome_keys:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        path, _ = winreg.QueryValueEx(key, "")
                        candidates.append((path, "Chrome"))
                except OSError:
                    pass

        candidates.extend([
            (os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"), "Chrome"),
            (os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"), "Chrome"),
            (os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"), "Chrome"),
        ])

        # 2. 探测 Microsoft Edge（Windows 10/11 预装 Chromium 内核）
        for bin_name in ("msedge", "msedge.exe"):
            w = shutil.which(bin_name)
            if w:
                candidates.append((w, "Edge"))

        edge_keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        ]
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key_path in edge_keys:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        path, _ = winreg.QueryValueEx(key, "")
                        candidates.append((path, "Edge"))
                except OSError:
                    pass

        candidates.extend([
            (os.path.expandvars(r"%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe"), "Edge"),
            (os.path.expandvars(r"%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe"), "Edge"),
            (os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"), "Edge"),
        ])

        seen = set()
        for path, bname in candidates:
            if not path:
                continue
            normalized = os.path.normcase(os.path.abspath(path))
            if normalized in seen or not os.path.isfile(path):
                continue
            seen.add(normalized)
            chrome_info_list.append((path, f"{bname} 已安装"))
        return chrome_info_list

    def check(self):
        chrome_list = self.get_chrome_info()
        if chrome_list:
            path, version = chrome_list[0]
            return {
                'status': True,
                'path': path,
                'version': version,
                'tips': f"使用宿主浏览器：{path} ({version})"
            }
        if self.preferred_path:
            return {'status': False, 'tips': f"配置的浏览器不存在：{self.preferred_path}"}
        return {
            'status': True,
            'path': None,
            'version': 'Playwright Chromium',
            'tips': "未找到本机 Chrome 或 Edge，将尝试 Playwright Chromium"
        }


# 兼容原独立脚本的类名。
driver1 = DanmuBrowserCollector


if __name__ == '__main__':
    import argparse

    # 平台识别已抽到独立模块（danmu.py 也会复用，避免 UI 线程拖入 playwright）
    try:
        from danma.platform_detect import detect_platform
    except ImportError:          # 直接以脚本方式运行本文件时的回退
        from platform_detect import detect_platform

    parser = argparse.ArgumentParser(
        description="StreamGet 独立弹幕采集调试脚本 (支持抖音、B站、快手、TikTok、小红书等平台)"
    )
    parser.add_argument("url", nargs="?", default="", help="直播间网页 URL 地址")
    parser.add_argument("-u", "--url", dest="url_opt", help="直播间网页 URL 地址")
    parser.add_argument("-p", "--platform", help="直播平台名称 (默认根据 URL 自动识别)")
    parser.add_argument("--headless", action="store_true", help="启用无头模式 (默认使用可见窗口，建议可见窗口以便绕过反爬验证)")
    parser.add_argument("--json", action="store_true", help="直接输出原始 JSON 格式数据")
    parser.add_argument("--chrome", help="自定义 Chrome 或 Edge 可执行文件路径")

    args = parser.parse_args()
    target_url = args.url_opt or args.url

    if not target_url:
        print("=" * 65)
        print("💡 StreamGet 独立弹幕采集调试器")
        print("用法示例:")
        print('  python sidecar/danma/main.py "https://live.douyin.com/758123456"')
        print('  python sidecar/danma/main.py "https://live.bilibili.com/21452505"')
        print('  python sidecar/danma/main.py "https://live.kuaishou.com/u/xxx" --headless')
        print("=" * 65)
        try:
            target_url = input("请输入要调试的直播间 URL: ").strip().strip("'\"")
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

    if not target_url:
        print("未输入有效直播间地址，退出。")
        sys.exit(1)

    platform = args.platform or detect_platform(target_url)
    headless = args.headless

    def pretty_print_message(items):
        if not items:
            return
        if not isinstance(items, list):
            items = [items]
        for item in items:
            if not isinstance(item, dict):
                continue
            if args.json:
                print(json.dumps(item, ensure_ascii=False))
                continue

            msg_type = item.get("type") or item.get("msg_type") or "未知"
            content = item.get("content") or item.get("text") or item.get("msg") or ""
            user_obj = item.get("user") if isinstance(item.get("user"), dict) else {}
            user = (
                item.get("name")
                or item.get("userName")
                or item.get("nickname")
                or item.get("senderName")
                or item.get("author_name")
                or user_obj.get("nickname")
                or user_obj.get("userName")
                or user_obj.get("name")
                or "匿名用户"
            )

            if msg_type in ("ChatMessage", "comment", "chat"):
                print(f"💬 [弹幕] {user}: {content}")
            elif msg_type in ("GiftMessage", "gift"):
                gift_name = item.get("giftName") or item.get("gift_name") or "礼物"
                count = item.get("giftCount") or item.get("count") or 1
                print(f"🎁 [礼物] {user} 送出 {gift_name} x {count}")
            elif msg_type in ("LikeMessage", "like"):
                count = item.get("count") or 1
                print(f"❤️ [点赞] {user} 点赞了直播间 (x{count})")
            elif msg_type in ("MemberMessage", "enter"):
                print(f"🚪 [进场] {user} 进入了直播间")
            elif msg_type in ("SocialMessage", "follow"):
                print(f"⭐ [关注] {user} 关注了主播")
            elif msg_type == "SystemMessage":
                print(f"🔔 [系统] {content}")
            else:
                print(f"📦 [{msg_type}] {json.dumps(item, ensure_ascii=False)}")

    print(f"\n🚀 启动弹幕采集器: 平台={platform}, 模式={'无头模式(headless)' if headless else '可见窗口(headful)'}")
    print(f"🎯 目标地址: {target_url}\n")

    collector = DanmuBrowserCollector(
        platform=platform,
        url=target_url,
        headless=headless,
        chrome_path=args.chrome,
        message_callback=pretty_print_message,
        log_fn=lambda msg: print(f"[Log] {msg}"),
    )
    try:
        collector.browser_launch()
    except KeyboardInterrupt:
        print("\n🛑 用户手动停止弹幕采集。")
        collector.browser_close()
