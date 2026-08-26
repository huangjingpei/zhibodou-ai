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
from live_plate.tiktok.tk import tiktok_pb
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
    ):
        super().__init__()
        self.platform = str(platform or "douyin").strip().lower()
        self.url = str(url or "").strip().strip("'\"")
        self.headless = bool(headless)
        self.user_data_dir = user_data_dir
        self.chrome_path = chrome_path
        self.message_callback = message_callback
        self.log_fn = log_fn
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
                        ],
                    }
                    if self.chrome_path and result.get('path'):
                        launch_options["executable_path"] = result['path']
                    elif result.get('path'):
                        # Playwright 官方支持 branded Chrome channel；比把自动发现的
                        # chrome.exe 当作任意 executable_path 更稳定。
                        launch_options["channel"] = "chrome"
                    self.browser = pw.chromium.launch_persistent_context(**launch_options)

                except Exception as error:
                    self.PostMessage([CreatSystemMessage(f"浏览器启动失败：{error}")])
                    return

                pages = self.browser.pages
                self.page = pages[0] if pages else self.browser.new_page()
                self.page.on("websocket", self.wss)
                self.page.on("response", self.http)
                self.page.on("load", self.execute_js)

                self.page.goto(self.url, timeout=60000, wait_until="domcontentloaded")
                self.PostMessage([CreatSystemMessage(
                    ("采集页面已启动（headless）" if self.headless else "采集页面已启动（可见模式）")
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
        if self._stop_event.is_set() or self.page is None:
            return
        self.page.evaluate(f"document.title = '请勿关闭';")
        if 'douyin' in self.page.url:
            self.page.evaluate("""
                    setInterval(checkElement, 5000);
                    setInterval(clickElementByText, 5000);
                    checkElement()

                    function checkElement() {

                    const roomInfoBarOuterElements = document.querySelectorAll('.__hasOptionBar');
                    console.log('-----',roomInfoBarOuterElements)
                    roomInfoBarOuterElements.forEach((element) => {
                        element.remove();
                    });


                        // 查找元素
                        var playButton = document.querySelector('.JL05k7eS.OG51D9OO');

                        // 检查元素是否存在
                        if (playButton) {
                            // 创建一个新的点击事件
                            var clickEvent = new MouseEvent('click', {
                                'view': window,
                                'bubbles': true,
                                'cancelable': true
                            });

                            // 触发点击事件
                            playButton.dispatchEvent(clickEvent);
                            location.reload();

                            console.log("点击了播放按钮");
                        } else {
                            console.log("元素不存在");
                        }
                    }
                    
                    
                    
                    function clickElementByText() {
                        const allElements = document.getElementsByTagName('*');
                        for (let i = 0; i < allElements.length; i++) {
                            const element = allElements[i];
                            if (element.textContent.trim() === "继续播放") {
                                element.click();
                                break;
                            }
                        }
                        console.log("不存在")
                    }

                    
                """)

    def browser_close(self):
        """
        # =====================================
        # 关闭浏览器，失效
        # =====================================
        :param response:
        :return:
        """
        # Playwright 同步对象必须由创建它的线程关闭；这里只发停止信号，
        # browser_launch() 的 finally 会在采集线程完成资源释放。
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
                res = douyin_pb2(data=response.body())
                self.PostMessage(res)
            if '/live/msg' in response.url:
                msg = ParseVxMessage(response.json())
                self.PostMessage(msg)
            if 'mtop.taobao.iliad.comment.query' in response.url or 'mtop.taobao.iliad.live.user.assistant.data.get' in response.url:
                msg = self.ParseTbMessage(response.text())
                self.PostMessage(msg)

            if 'mtop.taobao.dreamweb.live.list.query' in response.url:
                data = response.text()
                data = data[data.find('{'): data.rfind('}') + 1]
                data = json.loads(data)
                for live in data['data']['data']:
                    if live['roomStatus'] == '1':
                        self.page.goto(
                            f'https://liveplatform.taobao.com/restful/index/live/control?liveId={live["id"]}')

        except Exception as error:
            print(error)
            traceback.print_exc()

    def wss(self, websocket):

        """
        # =====================================
        # 启动浏览器,进行监听websocket
        # =====================================
        :param websocket: websocket响应
        :return:
        """
        try:
            if 'kuaishou.com' in websocket.url:
                websocket.on('framereceived', self.ks_onmessage)
            elif 'douyin.com/webcast/im/push/' in websocket.url:
                websocket.on('framereceived', self.dy_onmessage)
            elif 'tiktok' in websocket.url and "fetch" in websocket.url:
                websocket.on('framereceived', self.tk_onemssage)
            elif 'live-comet' in websocket.url:
                websocket.on('framereceived', self.bili_onemssage)
            elif 'ws.master.live' in websocket.url:
                websocket.on('framereceived', self.nimo_onmessage)

            elif 'pinduoduo.com' in websocket.url or 'yangkeduo.com' in websocket.url:
                websocket.on('framereceived', self.pdd_onmessage2)

            elif 'facebook.com/ws/realtime' in websocket.url:
                websocket.on('framereceived', self.facebook_onmessage)


            elif 'longlink' in websocket.url:
                websocket.on('framereceived', self.xhs_onmessage)

            elif 'rwp' in websocket.url:
                websocket.on('framereceived', self.xhs_shop_onmessage)

        except Exception as error:
            print(json.dumps({
                "type": "SystemMessage",
                "content": f"监听websocket出错了{error}"

            }, ensure_ascii=False), flush=True)

    def xhs_onmessage(self, framereceived):
        try:

            res = self.ParseXhsMessage(framereceived)
            self.PostMessage(res)
        except Exception as error:
            print('xhs_onmessage error', error)

    def xhs_shop_onmessage(self, framereceived):
        try:
            res = self.ParseXhsShopMessage(framereceived)
            self.PostMessage(res)

        except Exception as error:
            print(error)

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
            res = decode_packet(framereceived)
            if 'listmessage' in res:
                self.PostMessage(res['listmessage'])

        except Exception as e:
            print(e)
            print('出错', framereceived)

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
            candidates.append(os.path.abspath(os.path.expandvars(self.preferred_path)))
        which_chrome = shutil.which("chrome") or shutil.which("chrome.exe")
        if which_chrome:
            candidates.append(which_chrome)
        key_paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        ]
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key_path in key_paths:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        path, _ = winreg.QueryValueEx(key, "")
                        candidates.append(path)
                except OSError:
                    pass
        candidates.extend([
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ])
        seen = set()
        for path in candidates:
            normalized = os.path.normcase(os.path.abspath(path))
            if normalized in seen or not os.path.isfile(path):
                continue
            seen.add(normalized)
            chrome_info_list.append((path, "已安装"))
        return chrome_info_list

    def check(self):
        chrome_list = self.get_chrome_info()
        if chrome_list:
            path, version = chrome_list[0]
            return {
                'status': True,
                'path': path,
                'version': version,
                'tips': f"使用浏览器：{path}"
            }
        if self.preferred_path:
            return {'status': False, 'tips': f"配置的 Chrome 不存在：{self.preferred_path}"}
        return {
            'status': True,
            'path': None,
            'version': 'Playwright Chromium',
            'tips': "未找到本机 Chrome，将尝试 Playwright Chromium"
        }


# 兼容原独立脚本的类名。
driver1 = DanmuBrowserCollector


if __name__ == '__main__':
    driver = DanmuBrowserCollector(headless=False)
    driver.browser_launch()
