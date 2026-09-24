import json
import os
import queue
import random
import shutil
import subprocess
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

def cleanup_browser_profile(user_data_dir: str):
    """清理残留的占用该用户数据目录的 Chrome 进程及锁文件，防止 exitCode=21 导致崩溃。"""
    if not user_data_dir:
        return
    # 1. 终止占用该 profile 目录的孤儿 Chrome 进程
    try:
        norm_dir = os.path.normpath(user_data_dir)
        dir_name = os.path.basename(norm_dir)
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            f"Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe'\" | "
            f"Where-Object {{ $_.CommandLine -like '*{dir_name}*' }} | "
            f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
        ]
        subprocess.run(cmd, capture_output=True, timeout=3)
    except Exception:
        pass

    # 2. 清理残留锁文件
    if os.path.exists(user_data_dir):
        for lock_name in ("lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"):
            lp = os.path.join(user_data_dir, lock_name)
            if os.path.exists(lp):
                try:
                    os.remove(lp)
                except Exception:
                    pass


def should_abort_media_request(url: str, resource_type: str) -> bool:
    """判断当前请求是否属于视频/音频流切片，若是则应丢弃以降低 CPU 和带宽占用。"""
    if str(resource_type or "").lower() == "media":
        return True
    low_url = str(url or "").lower()
    return any(ext in low_url for ext in (".flv", ".m3u8", ".m4s", ".ts"))


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
        self._owner_thread_id = None
        self._action_queue = queue.Queue()
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
        self._owner_thread_id = threading.get_ident()
        result = checkChrome(self.chrome_path).check()
        self.PostMessage([CreatSystemMessage(result['tips'])])
        if not result['status']:
            return

        try:
            user_agent = None
            if 'v.kuaishou.com' in self.url:
                user_agent = "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36"
            cleanup_browser_profile(self.getUserData())
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

                self.page.on("websocket", self.wss)
                self.page.on("response", self.http)
                self.page.on("load", self.execute_js)

                self.page.goto(self.url, timeout=60000, wait_until="domcontentloaded")
                self.PostMessage([CreatSystemMessage(
                    ("采集页面已启动（headless 无头模式）" if self.headless else "采集页面已启动（可见模式）")
                    + f"：{self.page.url}"
                )])
                last_refresh = time.monotonic()
                auto_login_done = False
                auto_login_start = time.monotonic()
                auto_login_retries = 0

                while not self._stop_event.is_set():
                    self.page.wait_for_timeout(200)

                    # 处理跨线程派发的操作（确保 Playwright 所有调用均在同一工作线程）
                    while not self._action_queue.empty():
                        try:
                            fn, res_q = self._action_queue.get_nowait()
                            try:
                                res = fn()
                            except Exception as e:
                                res = {"success": False, "message": str(e)}
                            if res_q is not None:
                                res_q.put(res)
                        except queue.Empty:
                            break

                    if time.monotonic() - last_refresh >= 30 * 60:
                        self.page.reload(timeout=60000, wait_until="domcontentloaded")
                        last_refresh = time.monotonic()
                        auto_login_done = False
                        auto_login_start = time.monotonic()
                        auto_login_retries = 0

                    # 自动探测并调起扫码登录弹窗（开播后 1.5~15 秒内自动尝试）
                    if not auto_login_done and (time.monotonic() - auto_login_start >= 1.5):
                        try:
                            if self._is_login_modal_open_impl():
                                auto_login_done = True
                                self.log_fn("【弹幕助手】已为您自动弹出扫码登录窗口，请使用手机 APP 扫码登录！")
                            else:
                                status = self._check_login_status_impl()
                                if status.get("logged_in"):
                                    auto_login_done = True
                                    self.log_fn("【弹幕助手】检测到当前账号已处于登录状态，无需重复登录。")
                                else:
                                    res = self._trigger_login_impl()
                                    auto_login_retries += 1
                                    if res.get("success") and not res.get("already_logged_in"):
                                        self.page.wait_for_timeout(600)
                                        if self._is_login_modal_open_impl():
                                            auto_login_done = True
                                            self.log_fn("【弹幕助手】已为您自动点击并打开扫码登录弹窗，请使用手机 APP 扫码！")
                                    if auto_login_retries >= 8:
                                        auto_login_done = True
                                        self.log_fn("【弹幕助手】提示：若未看到登录弹窗，请直接在打开的浏览器窗口右上角点击【登录】")
                        except Exception as e:
                            auto_login_retries += 1
                            if auto_login_retries >= 8:
                                auto_login_done = True

        except Exception as error:
            if 'playwright install chrome' in str(error):
                self.PostMessage([CreatSystemMessage(content='请安装google')])
            else:
                self.PostMessage([CreatSystemMessage(content=f'采集器异常：{error}')])
        finally:
            # 清理剩余跨线程请求
            while not self._action_queue.empty():
                try:
                    _, res_q = self._action_queue.get_nowait()
                    if res_q is not None:
                        res_q.put({"success": False, "message": "采集器已关闭"})
                except queue.Empty:
                    break
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                pass
            self.browser = None
            self.page = None
            self._owner_thread_id = None

    def execute_js(self, _event=None):
        """页面保活与静音降载：保持页面活跃，检测弹窗，适度静音与暂停音视频以节省 CPU。

        注意：本函数挂在 page.on("load") 回调上，任何异常都会打崩 Playwright
        的同步事件循环（greenlet 损坏后 WS 帧回调全部失联，表现为采集器
        "在运行但永远收不到消息"），因此这里必须整体 try/except 兜底。
        """
        if self._stop_event.is_set() or self.page is None:
            return
        try:
            self.page.evaluate("document.title = '智播豆 · 弹幕采集中（请勿关闭）';")
        except Exception as error:
            self.log_fn(f"设置页面标题失败: {error}")

        try:
            self.page.evaluate("""
                (() => {
                    // 1. 自动点击"继续播放"确认弹窗，防止长时间未交互导致直播间断开
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

                    // 2. 定时静音与暂停音视频播放，降低 CPU 解码占用，且不破坏页面 DOM
                    setInterval(() => {
                        try {
                            document.querySelectorAll('video, audio').forEach(el => {
                                el.muted = true;
                                el.volume = 0;
                                if (!el.paused) {
                                    el.pause();
                                }
                            });
                        } catch (err) {}
                    }, 3000);
                })()
            """)
        except Exception as error:
            # 注入失败绝不能向外抛，否则事件循环被破坏、WS 帧全部收不到。
            self.log_fn(f"注入保活与静音 JS 失败: {error}")

    def _dispatch_to_owner_thread(self, fn, timeout=5.0):
        """将 Playwright 操作派发到创建它的工作线程执行，避免 greenlet 跨线程切换错误。"""
        if self._owner_thread_id is None or threading.get_ident() == self._owner_thread_id:
            return fn()
        if self._stop_event.is_set() or self.page is None:
            return {"success": False, "message": "采集器未运行或已停止"}
        res_queue = queue.Queue(maxsize=1)
        try:
            self._action_queue.put((fn, res_queue), timeout=1.0)
            return res_queue.get(timeout=timeout)
        except (queue.Full, queue.Empty):
            return {"success": False, "message": "操作超时或采集器繁忙"}

    def browser_close(self):
        """关闭浏览器与监听。

        注意：Playwright 对象（包括 browser.close）只能由创建它的同一个线程调用，
        绝不能在 Tkinter UI 主线程等外部线程跨线程调用，否则会触发
        greenlet.error: Cannot switch to a different thread 崩溃。
        外部线程只需调用 self._stop_event.set()，采集工作线程会在退出循环时
        在其自身线程的安全上下文中执行 finally -> browser.close()。
        """
        self._stop_event.set()
        if self._owner_thread_id is not None and threading.get_ident() == self._owner_thread_id:
            try:
                if self.browser is not None:
                    self.browser.close()
            except Exception:
                pass
            self.browser = None
            self.page = None

    def is_login_modal_open(self) -> bool:
        """检查页面上是否已经弹出了登录弹窗或二维码弹窗。"""
        res = self._dispatch_to_owner_thread(self._is_login_modal_open_impl, timeout=2.0)
        return bool(res) if isinstance(res, bool) else False

    def _is_login_modal_open_impl(self) -> bool:
        """检查页面上是否已经弹出了登录弹窗或二维码弹窗（属主线程内部执行）。"""
        if self._stop_event.is_set() or self.page is None:
            return False
        try:
            return bool(self.page.evaluate("""
                (() => {
                    const modalSelectors = [
                        '[class*="login-guide"]',
                        '[class*="login-mask"]',
                        '[class*="login-modal"]',
                        '[class*="passport-login"]',
                        '[class*="passport"]',
                        '[class*="qrcode"]',
                        'iframe[src*="passport"]',
                        '[class*="dialog-mask"]',
                        '[class*="modal-mask"]',
                    ];
                    for (const s of modalSelectors) {
                        const el = document.querySelector(s);
                        if (el && (el.offsetParent !== null || el.getClientRects().length > 0)) {
                            return true;
                        }
                    }
                    const texts = ['扫码登录', '抖音扫一扫', '快捷登录', '验证码登录', '手机号登录'];
                    for (const t of texts) {
                        const found = Array.from(document.querySelectorAll('div, span, p, h2, h3, a, button')).some(
                            e => (e.innerText || e.textContent || '').trim().includes(t) && (e.offsetParent !== null || e.getClientRects().length > 0)
                        );
                        if (found) return true;
                    }
                    return false;
                })()
            """))
        except Exception:
            return False

    def check_login_status(self) -> dict:
        """检查当前浏览器是否已登录平台账号（以抖音为主，同时支持通用平台探测）。

        返回字典：{"logged_in": bool, "user_name": str, "message": str}
        """
        res = self._dispatch_to_owner_thread(self._check_login_status_impl, timeout=3.0)
        if isinstance(res, dict):
            if "logged_in" not in res:
                res["logged_in"] = False
            return res
        return {"logged_in": False, "user_name": "", "message": str(res)}

    def _check_login_status_impl(self) -> dict:
        """检查当前浏览器是否已登录平台账号（属主线程内部执行）。

        返回字典：{"logged_in": bool, "user_name": str, "message": str}
        """
        if self._stop_event.is_set() or self.page is None:
            return {"logged_in": False, "user_name": "", "message": "浏览器未启动或页面未加载"}

        try:
            # 1. 优先尝试从 Cookie 验证关键认证凭据（抖音：sessionid / passport_csrf_token / uid_tt）
            if self.browser:
                try:
                    contexts = getattr(self.browser, "contexts", None)
                    ctx = contexts[0] if contexts else getattr(self.page, "context", None)
                    if ctx:
                        cookies = ctx.cookies()
                        login_cookie_names = {"sessionid", "sessionid_ss", "passport_csrf_token", "LOGIN_STATUS", "uid_tt"}
                        found = [c["name"] for c in cookies if c.get("name") in login_cookie_names and c.get("value")]
                        if any(name in ("sessionid", "sessionid_ss", "uid_tt") for name in found):
                            return {
                                "logged_in": True,
                                "user_name": "",
                                "message": f"Cookie 认证有效（已登录，检测到凭据: {', '.join(found)}）",
                            }
                except Exception:
                    pass

            # 2. 页面 DOM 检测
            res = self.page.evaluate("""
                (() => {
                    // 查找已登录用户头像或用户信息节点
                    const avatar = document.querySelector(
                        'header img[class*="avatar"], [class*="header"] [class*="avatar"], [data-e2e="user-info"], [class*="userAvatar"], [class*="avatar-box"]'
                    );

                    // 查找可见的登录按钮
                    const loginKeywords = ['登录', '登录后发弹幕', '立即登录', '扫码登录'];
                    const candidates = Array.from(document.querySelectorAll('button, a, div[role="button"], span'));
                    const loginBtn = candidates.find(el => {
                        const t = (el.innerText || el.textContent || '').trim();
                        return loginKeywords.includes(t) && (el.offsetParent !== null || el.getClientRects().length > 0);
                    });

                    // 检查输入框占位符
                    const inputs = Array.from(document.querySelectorAll('textarea, input[placeholder], div[contenteditable="true"]'));
                    let hasLoginPrompt = false;
                    for (const inp of inputs) {
                        const ph = (inp.getAttribute('placeholder') || inp.innerText || '').trim();
                        if (ph.includes('登录后') || ph.includes('登录即可') || ph.includes('需登录')) {
                            hasLoginPrompt = true;
                            break;
                        }
                    }

                    if (loginBtn) {
                        return {
                            logged_in: false,
                            user_name: '',
                            message: `页面显示登录入口【${(loginBtn.innerText || '').trim()}】，尚未登录`,
                        };
                    }

                    if (hasLoginPrompt) {
                        return {
                            logged_in: false,
                            user_name: '',
                            message: '弹幕输入框提示需登录后发弹幕',
                        };
                    }

                    if (avatar) {
                        return {
                            logged_in: true,
                            user_name: '',
                            message: '检测到登录用户头像，已登录',
                        };
                    }

                    return {
                        logged_in: false,
                        user_name: '',
                        message: '未检测到明确的用户登录标识',
                    };
                })()
            """)
            return res if isinstance(res, dict) else {"logged_in": False, "user_name": "", "message": str(res)}
        except Exception as error:
            return {"logged_in": False, "user_name": "", "message": f"检测登录态异常: {error}"}

    def trigger_login(self) -> dict:
        """主动触发平台登录弹窗（调出扫码登录界面）。

        主播可以在弹出的 Chrome 浏览器中直接使用 APP 扫码登录。
        登录后 Cookie 自动保存在持久化 profile 中，下次开播免登录。
        返回字典：{"success": bool, "message": str}
        """
        res = self._dispatch_to_owner_thread(self._trigger_login_impl, timeout=5.0)
        if isinstance(res, dict):
            return res
        return {"success": False, "message": str(res)}

    def _trigger_login_impl(self) -> dict:
        """主动触发平台登录弹窗（属主线程内部执行）。"""
        if self._stop_event.is_set() or self.page is None:
            return {"success": False, "message": "浏览器未启动或页面未加载"}

        try:
            status = self._check_login_status_impl()
            if status.get("logged_in"):
                return {"success": True, "already_logged_in": True, "message": "当前已处于登录状态，无需重复登录"}

            # 1. 优先使用 Playwright Locator 原生点击（支持 React 合成事件）
            selectors = [
                'button:has-text("登录后发弹幕")',
                'div:has-text("登录后发弹幕")',
                'span:has-text("登录后发弹幕")',
                'header button:has-text("登录")',
                'header div:has-text("登录")',
                '[data-e2e="header-login"]',
                '[class*="header-login"]',
                '[class*="login-button"]',
                '[class*="login-btn"]',
                'button:has-text("登录")',
                'a:has-text("登录")',
                'div[role="button"]:has-text("登录")',
                '[class*="chat-input"] [class*="login"]',
                '[class*="ChatInput"] [class*="login"]',
                '[class*="chat-input"]',
                '[class*="ChatInput"]',
                'textarea[placeholder*="登录"]',
            ]

            for sel in selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=200):
                        loc.click(timeout=800)
                        self.page.wait_for_timeout(300)
                        if self._is_login_modal_open_impl():
                            self.log_fn(f"已通过元素【{sel}】成功调起登录弹窗")
                            return {"success": True, "message": "已调起扫码登录弹窗，请使用手机 APP 扫码登录"}
                except Exception:
                    continue

            # 2. DOM evaluate 点击兜底
            clicked = self.page.evaluate("""
                (() => {
                    const texts = ['登录后发弹幕', '登录', '立即登录', '扫码登录'];
                    const candidates = Array.from(document.querySelectorAll('button, a, div[role="button"], span, div'));
                    for (const t of texts) {
                        const match = candidates.find(el => {
                            const text = (el.innerText || el.textContent || '').trim();
                            return text === t && (el.offsetParent !== null || el.getClientRects().length > 0);
                        });
                        if (match) {
                            match.click();
                            return { clicked: true, text: t };
                        }
                    }

                    const chat = document.querySelector('[class*="chat-input"], [class*="ChatInput"], textarea');
                    if (chat && (chat.offsetParent !== null || chat.getClientRects().length > 0)) {
                        chat.click();
                        return { clicked: true, text: '聊天室输入区' };
                    }

                    return { clicked: false, text: '未找到登录入口' };
                })()
            """)

            if clicked.get("clicked"):
                self.log_fn(f"已触发平台登录入口：{clicked.get('text')}，请在浏览器中扫码登录")
                return {
                    "success": True,
                    "message": f"已成功点击【{clicked.get('text')}】，请在浏览器窗口中使用 APP 扫码登录",
                }
            else:
                return {
                    "success": False,
                    "message": "未在页面中找到可点击的登录按钮，请直接在浏览器窗口右上角点击【登录】",
                }
        except Exception as error:
            self.log_fn(f"调起登录弹窗失败: {error}")
            return {"success": False, "message": f"调起登录弹窗失败: {error}"}

    def send_danmu_reply(self, text: str) -> dict:
        """使用 Playwright 定位直播间弹幕输入框，输入内容并按回车发送回复。

        :param text: 要发送的弹幕回复内容
        :return: {"success": bool, "message": str}
        """
        text = str(text or "").strip()
        if not text:
            return {"success": False, "message": "回复文本内容为空"}
        res = self._dispatch_to_owner_thread(lambda: self._send_danmu_reply_impl(text), timeout=6.0)
        if isinstance(res, dict):
            return res
        return {"success": False, "message": str(res)}

    def _send_danmu_reply_impl(self, text: str) -> dict:
        """使用 Playwright 定位直播间弹幕输入框发送回复（属主线程内部执行）。"""
        if self._stop_event.is_set() or self.page is None:
            return {"success": False, "message": "浏览器未启动或页面已关闭"}

        try:
            # 1. 登录前置检查
            login_info = self._check_login_status_impl()
            if not login_info.get("logged_in") and "登录后发弹幕" in login_info.get("message", ""):
                return {
                    "success": False,
                    "need_login": True,
                    "message": "尚未登录平台账号（弹幕区提示需登录后发弹幕），请先扫码登录",
                }

            # 2. 定位输入框
            candidate_selectors = [
                'textarea[placeholder*="弹幕"]',
                'textarea[placeholder*="聊聊"]',
                'textarea[placeholder*="说点什么"]',
                'textarea[placeholder*="发个弹幕"]',
                '[class*="chat-input"] textarea',
                '[class*="ChatInput"] textarea',
                '[class*="input-area"] textarea',
                '[class*="interactive-input"] textarea',
                '[class*="chat_input"] textarea',
                '[class*="editor"] textarea',
                'div[contenteditable="true"][class*="chat"]',
                'div[contenteditable="true"][class*="input"]',
                'div[contenteditable="true"]',
                'input[placeholder*="弹幕"]',
                'input[placeholder*="聊聊"]',
                'input[placeholder*="说点什么"]',
                'textarea',
            ]

            input_locator = None
            for sel in candidate_selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=500):
                        input_locator = loc
                        break
                except Exception:
                    continue

            # 3. 成功获取 Locator
            if input_locator is not None:
                input_locator.click()
                self.page.wait_for_timeout(100)

                try:
                    input_locator.fill(text)
                except Exception:
                    input_locator.type(text)

                self.page.wait_for_timeout(100)
                input_locator.press("Enter")

                try:
                    send_btn = self.page.locator(
                        'button:has-text("发送"), [class*="send-btn"], [class*="sendBtn"], [class*="send-button"]'
                    ).first
                    if send_btn.is_visible(timeout=300):
                        send_btn.click()
                except Exception:
                    pass

                self.log_fn(f"【弹幕回复】已在输入框提交回复: {text}")
                return {"success": True, "message": f"弹幕已成功输入并按回车发送: {text}"}

            # 4. DOM 原生注入兜底
            res = self.page.evaluate("""
                (msgText) => {
                    const inputs = Array.from(document.querySelectorAll(
                        'textarea, input[type="text"], div[contenteditable="true"]'
                    )).filter(el => {
                        const style = window.getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
                    });

                    if (inputs.length === 0) {
                        return { success: false, message: '未找到可见的弹幕输入框' };
                    }

                    const target = inputs[inputs.length - 1];
                    target.focus();
                    if (target.isContentEditable) {
                        target.innerText = msgText;
                    } else {
                        target.value = msgText;
                    }
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                    target.dispatchEvent(new Event('change', { bubbles: true }));

                    target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                    target.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));

                    const sendBtn = Array.from(document.querySelectorAll('button, div[role="button"], span')).find(el => {
                        const t = (el.innerText || el.textContent || '').trim();
                        return (t === '发送' || t === '发送弹幕') && el.offsetParent !== null;
                    });
                    if (sendBtn) {
                        sendBtn.click();
                    }

                    return { success: true, message: '通过 DOM 事件输入并回车发送' };
                }
            """, text)

            if isinstance(res, dict) and res.get("success"):
                self.log_fn(f"【弹幕回复】(DOM兜底) 已提交回复: {text}")
                return {"success": True, "message": f"弹幕已输入并按回车发送: {text}"}
            else:
                msg = res.get("message") if isinstance(res, dict) else str(res)
                return {"success": False, "message": f"定位弹幕输入框失败: {msg}"}

        except Exception as error:
            self.log_fn(f"【弹幕回复】发送弹幕异常: {error}")
            return {"success": False, "message": f"发送弹幕异常: {error}"}

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
            elif ('douyin.com' in ws_url and ('im/push' in ws_url or 'webcast' in ws_url)) or (self.platform == 'douyin' and ('im' in ws_url or 'webcast' in ws_url or 'push' in ws_url)):
                self.log_fn(f"已捕获抖音 WebSocket 弹幕连接: {websocket.url[:70]}")
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
            if isinstance(framereceived, str):
                return
            messages = douyin_pb(data=framereceived)
            if messages:
                self.PostMessage(messages)
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
