import json
import os
import random
import sys
import threading
import time
import traceback
import winreg

from configobj import ConfigObj
from playwright.sync_api import sync_playwright as playwright
from concurrent.futures import ThreadPoolExecutor

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

import requests


class driver1:
    def __init__(self):
        super().__init__()
        self.flag_close = False
        self.browser = None
        self.page = None
        self.flag = True
        self.lock = threading.RLock()
        self.config = None
        self.vx_gift_count = {}
        self.vx_person = {}
        self.vx_person_url = {}
        self.session = requests.Session()
        self.pool = ThreadPoolExecutor(max_workers=100)
        self.ParseTbMessage = Tb().ParseTbComment
        self.ParsePddMessage = Pdd().pdd_pb
        self.ParseXhsMessage = Xhs().ParseXhsComment
        self.ParseXhsShopMessage = Xhs().ParseXhsShopComment



    def getUserData(self):

        return os.path.join(os.getenv("LOCALAPPDATA"), "AiCommentSdk")

    def browser_launch(self):
        """
        # =====================================
        # 启动浏览器,进行监听
        # =====================================
        :param url:直播间地址
        :return
        """
        current_path = os.path.abspath(sys.argv[0])
        current_directory = os.path.dirname(current_path)
        ini_path = os.path.join(current_directory, 'setting', 'setting.ini')

        self.config = ConfigObj(ini_path, encoding='UTF8')
        plat = self.config['broadcast']['plat']
        self.url = self.config['broadcast'][plat]
        self.message_list = []
        self.message_list2 = []
        self.flag_close = False
        self.vx_seq = []
        self.flag = True
        result = checkChrome().check()
        self.PostMessage([CreatSystemMessage(result['tips'])])
        if not result['status']:
            return

        try:
            user_agent = None
            if 'v.kuaishou.com' in self.url:
                user_agent = "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36"
            with playwright() as pw:

                try:
                    self.browser = pw.chromium.launch_persistent_context(
                        user_data_dir=self.getUserData(),
                        executable_path=result['path'],
                        user_agent=user_agent,
                        headless=False,
                        no_viewport=True,
                        slow_mo=10,
                        args=['--disable-blink-features=AutomationControlled', '--enable-automation']
                    )

                except Exception as error:
                    print(json.dumps({
                        "type": "SystemMessage",
                        "content": "浏览器启动失败,请检查设置中的谷歌exe路径"

                    }), flush=True)

                self.page = self.browser.new_page()
                self.page.on("websocket", self.wss)
                self.page.on("response", self.http)
                self.page.on("load", self.execute_js)

                self.page.goto(self.url, timeout=0)

                pages = self.browser.pages
                if pages:
                    first_page = pages[0]
                    first_page.close()
                while True:
                    self.page.wait_for_timeout(1000 * 30 * 60)
                    self.page.goto(self.page.url, timeout=0)

        except Exception as error:

            if 'playwright install chrome' in str(error):
                self.PostMessage([CreatSystemMessage(content='请安装google')])
            else:
                self.PostMessage([CreatSystemMessage(content='请关闭google再启动')])
            print(json.dumps({
                "type": "SystemMessage",
                "content": f"出错{error}"

            }, ensure_ascii=False), flush=True)

    def execute_js(self, text):
        self.page.evaluate(f"document.title = '请勿关闭';")
        if 'douyin' in self.page.url:
            self.page.evaluate("""
                    setInterval(checkElement, 5000);
                    setInterval(clickElementByText, 5000);
                    setInterval(() => {
                        // 刷新当前页面
                        location.reload();
                    },  30*60 * 1000);
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
        pass

    def http(self, response):
        """
        # =====================================
        # 启动浏览器,进行监听http
        # =====================================
        :param response:http响应
        :return:
        """
        if not self.flag:
            self.browser.close()
        try:
            if 'webcast/im/fetch' in response.url:
                res = douyin_pb2(data=response.body())
                self.PostMessage(res)
            if '/live/msg' in response.url:
                msg = ParseVxMessage(response.json())
                self.PostMessage(msg)
            if 'mtop.taobao.iliad.comment.query' in response.url or 'mtop.taobao.iliad.live.user.assistant.data.get' in response.url:
                msg = Tb().ParseTbComment(response.text())
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
            if 'tiktok' in websocket.url and "fetch" in websocket.url:
                websocket.on('framereceived', self.tk_onemssage)

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

            elif 'pinduoduo.com' in websocket.url or 'duo' in websocket.url:
                websocket.on('framereceived', self.pdd_onmessage2)

            elif 'acebook.com/ws/realtime' in websocket.url:
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
        res = ParseFaceBookComment(framereceived)
        self.PostMessage(res)

    def nimo_onmessage(self, framereceived):
        res = nimo_tars(framereceived)
        for msg in res:
            self.PostMessage(res)

    def bili_onemssage(self, framereceived):
        try:
            res = decode_packet(framereceived)
            if 'listmessage' in res:
                self.PostMessage(res['listmessage'])

        except Exception as e:
            print(e)
            print('出错', framereceived)

    def ks_onmessage(self, framereceived):
        res = kuaishou_pb(data=framereceived)
        self.PostMessage(res)

    def dy_onmessage(self, framereceived):
        random_x = random.randint(100, 1000)
        random_y = random.randint(100, 1000)
        print(random_x, random_y)
        self.page.mouse.move(random_x, random_y)

        res = douyin_pb(data=framereceived)
        self.PostMessage(res)

    def tk_onemssage(self, framereceived):
        res = tiktok_pb(data=framereceived)
        self.PostMessage(res)

    def pdd_onmessage(self, framereceived):
        res = pdd_pb(data=framereceived)
        self.PostMessage(res)


    def pdd_onmessage2(self, framereceived):
        res = self.ParsePddMessage(data=framereceived)
        self.PostMessage(res)

    def PostMessage(self, data):
        if len(data) > 0:
            self.a = threading.Thread(target=self.send_msg, args=(data,))
            self.a.start()

    def send_msg(self, data):
        try:
            print("开始推送数据")
            self.session.post(url='http://127.0.0.1:7979/biz/danmaku/live/msg', json=data)
        except Exception as error:
            print("推送出错")
            print(error)


class checkChrome:
    def __init__(self):
        pass

    def get_chrome_info(self):
        chrome_info_list = []
        try:
            # 打开注册表中 Chrome 相关的键
            key_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
            ]
            for key_path in key_paths:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    # 获取执行路径
                    path, _ = winreg.QueryValueEx(key, "")
                    # 尝试从版本信息注册表中获取版本号
                    version_key_path = r"SOFTWARE\Google\Chrome\BLBeacon"
                    try:
                        version_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, version_key_path)
                        version, _ = winreg.QueryValueEx(version_key, "version")
                        chrome_info_list.append((path, version))
                        winreg.CloseKey(version_key)
                    except (FileNotFoundError, OSError):
                        # 如果无法从上述注册表项获取版本号，尝试从文件属性获取
                        try:
                            import win32api
                            info = win32api.GetFileVersionInfo(path, '\\')
                            ms = info['FileVersionMS']
                            ls = info['FileVersionLS']
                            version = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
                            chrome_info_list.append((path, version))
                        except Exception:
                            pass
                    winreg.CloseKey(key)
                except FileNotFoundError:
                    pass
        except Exception as e:
            print(f"An error occurred: {e}")
        return chrome_info_list

    def compare_versions(self, version1, version2):
        # 将版本号拆分为数字列表
        v1_parts = list(map(int, version1.split('.')))
        v2_parts = list(map(int, version2.split('.')))
        # 比较每个部分
        for i in range(max(len(v1_parts), len(v2_parts))):
            num1 = v1_parts[i] if i < len(v1_parts) else 0
            num2 = v2_parts[i] if i < len(v2_parts) else 0
            if num1 > num2:
                return 1
            elif num1 < num2:
                return -1
        return 0

    def get_highest_version_info(self, chrome_info_list):
        if not chrome_info_list:
            return None
        highest_version_info = chrome_info_list[0]
        for info in chrome_info_list[1:]:
            if self.compare_versions(info[1], highest_version_info[1]) > 0:
                highest_version_info = info
        return highest_version_info

    def check(self):
        chrome_list = self.get_chrome_info()
        if chrome_list:
            highest_version_info = self.get_highest_version_info(chrome_list)
            return {
                'status': True,
                'path': highest_version_info[0],
                'version': highest_version_info[1],
                'tips': f"版本号为{highest_version_info[1]}"
            }

        return {
            'status': False,
            'tips': "未找到google"
        }


if __name__ == '__main__':
    driver = driver1()
    driver.browser_launch()
