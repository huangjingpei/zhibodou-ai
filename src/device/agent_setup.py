"""智博豆运行前设备自检与自动化引导模块 (Agent & Doubao Pre-run Setup)

核心功能：
1. 检查并安装 E:\\zhibodou-ai\\zhibodou\\android_agent\\app\\release\\app-release.apk (智博豆助手)；
2. 启动智博豆助手，探测无障碍服务状态；
3. 若无障碍服务未开启，执行原生 ADB UI 自动化流：
   - 自动点击「👉 点击开启无障碍服务 (Accessibility)」；
   - 自动进入系统「辅助功能」->「已安装的应用程序」(或已安装的服务)；
   - 自动点击进入「智博豆助手」；
   - 自动将「关」的开关切换为开启，并确认系统安全授权弹窗（「允许」/「确定」/「开启」）；
   - 开启后自动退出助手程序，返回桌面；
4. 检查手机是否安装豆包 APP (com.larus.nova)；
   - 若未安装：提示用户前往手机应用商店安装；
   - 若已安装：自动将豆包唤醒打开至前台对话界面，确保后续直播/预演话术交互畅通无阻。
"""

from __future__ import annotations

import os
import sys
import re
import time
import subprocess
import xml.etree.ElementTree as ET
from typing import Callable, Optional

from core.paths import ADB_EXE, ZHIBODOU_AGENT_APK
from core.doubao import DOUBAO_PKG
from device import adb_utils

AGENT_PKG = "com.zhibodou.agent"
AGENT_ACTIVITY = "com.zhibodou.agent/.MainActivity"
AGENT_SERVICE = "com.zhibodou.agent/com.zhibodou.agent.DoubaoAccessibilityService"
AGENT_RPC_PORT = 12051

_ADB_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _log(msg: str, log_fn: Optional[Callable[[str], None]] = None):
    try:
        print(f"[PreRunSetup] {msg}")
    except UnicodeEncodeError:
        try:
            safe_msg = msg.encode(sys.stdout.encoding or "gbk", errors="replace").decode(sys.stdout.encoding or "gbk", errors="ignore")
            print(f"[PreRunSetup] {safe_msg}")
        except Exception:
            pass
    except Exception:
        pass

    if log_fn:
        try:
            log_fn(msg)
        except Exception:
            pass


def _adb_exec(args: list[str], serial: Optional[str] = None, timeout: int = 8) -> tuple[str, bool]:
    """执行底层 adb 命令，返回 (stdout_str, ok)"""
    cmd = [ADB_EXE]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=_ADB_FLAGS,
        )
        return res.stdout.decode("utf-8", "ignore"), (res.returncode == 0)
    except Exception as exc:
        return str(exc), False


def _parse_bounds(bounds_str: str) -> Optional[tuple[int, int, int, int]]:
    """解析 [left,top][right,bottom] 格式的坐标范围"""
    m = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str or "")
    if not m:
        return None
    l, t, r, b = map(int, m.groups())
    if r <= l or b <= t:
        return None
    return l, t, r, b


def _dump_ui_hierarchy(serial: Optional[str] = None) -> Optional[ET.Element]:
    """通过 uiautomator dump 抓取当前屏幕 UI 树并解析为 ElementTree"""
    remote_path = "/sdcard/zbd_setup_dump.xml"
    # 1. dump
    _adb_exec(["shell", "uiautomator", "dump", remote_path], serial=serial, timeout=8)
    # 2. 读取 xml
    xml_str, ok = _adb_exec(["exec-out", "cat", remote_path], serial=serial, timeout=4)
    if not ok or "<hierarchy" not in xml_str:
        # 回退: adb shell cat
        xml_str, ok = _adb_exec(["shell", "cat", remote_path], serial=serial, timeout=4)
    if "<hierarchy" not in xml_str:
        return None
    try:
        return ET.fromstring(xml_str)
    except Exception:
        return None


def _find_node_by_keywords(
    root: Optional[ET.Element],
    keywords: list[str],
    class_filter: Optional[str] = None,
) -> Optional[dict]:
    """在 UI 树中按文本或描述关键词查找匹配的控件属性"""
    if root is None:
        return None

    for node in root.iter("node"):
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        cls_name = (node.attrib.get("class") or "").strip()
        bounds = _parse_bounds(node.attrib.get("bounds") or "")
        if not bounds:
            continue

        if class_filter and class_filter.lower() not in cls_name.lower():
            continue

        combined = f"{text} {desc}"
        for kw in keywords:
            if kw.lower() in combined.lower():
                return node.attrib

    return None


def _find_switch_node(root: Optional[ET.Element]) -> Optional[dict]:
    """查找屏幕上的无障碍服务主开关控件 (排除'快捷方式'开关，优先匹配关状态的主开关)"""
    if root is None:
        return None

    # 1. 优先查找三星 OneUI / 定制 ROM 的 SwitchBar (如 sesl_switchbar_switch 或 sesl_switchbar_container)
    for node in root.iter("node"):
        res_id = (node.attrib.get("resource-id") or "").lower()
        desc = (node.attrib.get("content-desc") or "").strip()
        text = (node.attrib.get("text") or "").strip()
        bounds = _parse_bounds(node.attrib.get("bounds") or "")
        if not bounds:
            continue
        if "sesl_switchbar" in res_id or "switch_bar" in res_id:
            # 若已有状态显示为 "开" / "ON"，说明已开启，无需再点
            if desc in ["开", "开启", "ON", "on"] or text in ["开", "开启", "ON", "on"]:
                return None
            # 优先返回可点击的 switch 或 container
            if "switch" in res_id or node.attrib.get("clickable") == "true":
                return node.attrib

    # 2. 查找标注 "关" / "OFF" / "关闭" 的控件或开关（排除快捷方式）
    off_keywords = ["关", "off", "关闭", "未开启"]
    for node in root.iter("node"):
        text = (node.attrib.get("text") or "").strip().lower()
        desc = (node.attrib.get("content-desc") or "").strip().lower()
        cls_name = (node.attrib.get("class") or "").lower()
        bounds = _parse_bounds(node.attrib.get("bounds") or "")
        if not bounds:
            continue

        if "快捷方式" in desc or "快捷方式" in text or "shortcut" in desc or "shortcut" in text:
            continue

        if any(k == text or k == desc for k in off_keywords):
            return node.attrib

        if "switch" in cls_name or "compoundbutton" in cls_name:
            if node.attrib.get("checked") == "false" or text in off_keywords:
                return node.attrib

    # 3. 兜底查找非快捷方式的 Switch 控件（且未处于 checked 状态）
    for node in root.iter("node"):
        cls_name = (node.attrib.get("class") or "").lower()
        desc = (node.attrib.get("content-desc") or "").strip()
        text = (node.attrib.get("text") or "").strip()
        bounds = _parse_bounds(node.attrib.get("bounds") or "")
        if bounds and ("switch" in cls_name or "compoundbutton" in cls_name):
            if "快捷方式" in desc or "快捷方式" in text or "shortcut" in desc:
                continue
            if node.attrib.get("checked") != "true" and desc not in ["开", "开启", "ON", "on"]:
                return node.attrib

    return None


def _tap_bounds(bounds_str: str, serial: Optional[str] = None) -> bool:
    """根据 bounds 字符串点击中心坐标"""
    bounds = _parse_bounds(bounds_str)
    if not bounds:
        return False
    l, t, r, b = bounds
    cx = (l + r) // 2
    cy = (t + b) // 2
    _, ok = _adb_exec(["shell", "input", "tap", str(cx), str(cy)], serial=serial, timeout=3)
    return ok


def _swipe_up(serial: Optional[str] = None):
    """向上滑动屏幕 (内容向下滚动)"""
    _adb_exec(["shell", "input", "swipe", "500", "1500", "500", "800", "300"], serial=serial, timeout=3)
    time.sleep(0.6)


def is_accessibility_service_enabled(serial: Optional[str] = None) -> bool:
    """检查智博豆无障碍服务是否已激活"""
    out, ok = _adb_exec(["shell", "settings", "get", "secure", "enabled_accessibility_services"], serial=serial)
    if ok and AGENT_PKG in out:
        # 再确认全局开关
        out_en, _ = _adb_exec(["shell", "settings", "get", "secure", "accessibility_enabled"], serial=serial)
        if "0" not in out_en.strip():
            return True

    # 尝试端口转发探测存活
    try:
        from device import input_text
        input_text._ensure_agent_forward(serial, port=AGENT_RPC_PORT)
        if input_text._is_agent_alive(port=AGENT_RPC_PORT):
            return True
    except Exception:
        pass

    return False


def activate_accessibility_ui_flow(
    serial: Optional[str] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    全自动执行进入无障碍设置、点击已安装应用、找到智博豆助手、打开开关并确认授权的完整流程。
    保证不重复误点关闭开关，且退出时绝不执行 am force-stop 以免系统强制关闭服务。
    """
    _log("【智博豆助手】检测到无障碍服务未开启，开始自动导航激活流程...", log_fn)

    # 0. 快速通道：若系统允许 settings put，先尝试底层激活
    try:
        _adb_exec(["shell", "settings", "put", "secure", "enabled_accessibility_services", AGENT_SERVICE], serial=serial)
        _adb_exec(["shell", "settings", "put", "secure", "accessibility_enabled", "1"], serial=serial)
        time.sleep(0.6)
        if is_accessibility_service_enabled(serial=serial):
            _log("【智博豆助手】✅ 通过底层安全配置快速激活无障碍服务成功！", log_fn)
            return True
    except Exception:
        pass

    # 1. 确保智博豆助手处于前台
    _adb_exec(["shell", "am", "start", "-n", AGENT_ACTIVITY], serial=serial)
    time.sleep(1.2)

    # 2. 点击「👉 点击开启无障碍服务 (Accessibility)」按钮
    tree = _dump_ui_hierarchy(serial=serial)
    btn_node = _find_node_by_keywords(tree, ["开启无障碍服务", "Accessibility", "点击开启"])
    clicked_btn = False
    if btn_node and _tap_bounds(btn_node.get("bounds", ""), serial=serial):
        _log("【智博豆助手】已点击「开启无障碍服务」引导按钮", log_fn)
        clicked_btn = True
        time.sleep(1.5)

    if not clicked_btn:
        # 直接通过 Intent 跳转辅助功能设置页
        _log("【智博豆助手】直接唤起系统辅助功能设置页 (android.settings.ACCESSIBILITY_SETTINGS)", log_fn)
        _adb_exec(["shell", "am", "start", "-a", "android.settings.ACCESSIBILITY_SETTINGS"], serial=serial)
        time.sleep(1.5)

    # 3. 在辅助功能列表查找「已安装的应用程序」或「已安装的服务」
    tree = _dump_ui_hierarchy(serial=serial)
    installed_node = _find_node_by_keywords(
        tree,
        ["已安装的应用程序", "已安装的应用", "已安装的服务", "已下载的服务", "已下载的应用", "Installed apps", "Installed services"],
    )

    if not installed_node:
        # 尝试滑动屏幕再次寻找
        _swipe_up(serial=serial)
        tree = _dump_ui_hierarchy(serial=serial)
        installed_node = _find_node_by_keywords(
            tree,
            ["已安装的应用程序", "已安装的应用", "已安装的服务", "已下载的服务", "已下载的应用", "Installed apps", "Installed services"],
        )

    if installed_node:
        _log("【智博豆助手】发现「已安装的应用程序」分类，点击进入...", log_fn)
        _tap_bounds(installed_node.get("bounds", ""), serial=serial)
        time.sleep(1.2)
    else:
        _log("【智博豆助手】当前设备辅助功能页直接列出服务，直接查找助手项目...", log_fn)

    # 4. 查找「智博豆助手」或「智播豆助手」服务项并点击
    tree = _dump_ui_hierarchy(serial=serial)
    agent_node = _find_node_by_keywords(tree, ["智播豆助手", "智博豆助手", "Zhibodou"])
    if not agent_node:
        _swipe_up(serial=serial)
        tree = _dump_ui_hierarchy(serial=serial)
        agent_node = _find_node_by_keywords(tree, ["智播豆助手", "智博豆助手", "Zhibodou"])

    if agent_node:
        _log("【智博豆助手】找到「智播豆助手」服务项，点击进入详情设置...", log_fn)
        _tap_bounds(agent_node.get("bounds", ""), serial=serial)
        time.sleep(1.2)
    else:
        _log("【智博豆助手】⚠️ 未在列表中识别到「智播豆助手」文本节点", log_fn)

    # 5. 查找详情页中的主开关并打开
    tree = _dump_ui_hierarchy(serial=serial)
    switch_node = _find_switch_node(tree)
    clicked_switch_bounds = None
    if switch_node:
        clicked_switch_bounds = switch_node.get("bounds", "")
        _log("【智博豆助手】找到服务主开关控件，点击切换为开启...", log_fn)
        _tap_bounds(clicked_switch_bounds, serial=serial)
        time.sleep(1.0)
    else:
        _log("【智博豆助手】未检测到关闭状态的主开关（可能已处于开启状态）", log_fn)

    # 6. 处理系统弹出的安全授权对话框（「允许」/「确定」/「开启」/ button1）
    time.sleep(0.5)
    tree = _dump_ui_hierarchy(serial=serial)
    confirm_node = None
    if tree is not None:
        for node in tree.iter("node"):
            res_id = (node.attrib.get("resource-id") or "").lower()
            text = (node.attrib.get("text") or "").strip()
            cls_name = (node.attrib.get("class") or "").lower()
            bounds = node.attrib.get("bounds", "")
            # 严格防止将刚刚点击的开关误判为确认按钮！
            if not bounds or bounds == clicked_switch_bounds:
                continue

            # 优先匹配标准确认按钮 android:id/button1
            if res_id.endswith(":id/button1"):
                confirm_node = node.attrib
                break

            # 匹配文字明确为确认/允许的 Button
            if ("button" in cls_name or node.attrib.get("clickable") == "true") and text in ["允许", "确定", "开启", "好的", "Allow", "OK", "Turn on", "确认"]:
                confirm_node = node.attrib
                break

    if confirm_node:
        _log("【智博豆助手】侦测到系统权限安全确认弹窗，自动点击授权允许...", log_fn)
        _tap_bounds(confirm_node.get("bounds", ""), serial=serial)
        time.sleep(1.0)

    # 7. 辅助强化：再次尝试通过 Settings Secure 固化
    try:
        _adb_exec(["shell", "settings", "put", "secure", "enabled_accessibility_services", AGENT_SERVICE], serial=serial)
        _adb_exec(["shell", "settings", "put", "secure", "accessibility_enabled", "1"], serial=serial)
    except Exception:
        pass

    # 8. 退出设置页，返回桌面（绝不能执行 am force-stop，否则系统会强杀无障碍服务并自动关闭开关！）
    _log("【智博豆助手】授权交互完成，退出设置页返回桌面...", log_fn)
    _adb_exec(["shell", "input", "keyevent", "4"], serial=serial)  # KEYCODE_BACK
    time.sleep(0.3)
    _adb_exec(["shell", "input", "keyevent", "4"], serial=serial)  # KEYCODE_BACK
    time.sleep(0.3)
    _adb_exec(["shell", "input", "keyevent", "3"], serial=serial)  # KEYCODE_HOME
    time.sleep(0.8)

    # 9. 最终状态校验
    success = is_accessibility_service_enabled(serial=serial)
    if success:
        _log("【智博豆助手】✅ 无障碍服务已成功开启并激活！", log_fn)
    else:
        _log("【智博豆助手】⚠️ 未能自动检测到激活状态（建议人工在手机上核实）", log_fn)
    return success


def check_and_setup_zhibodou_agent(
    serial: Optional[str] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """
    【条件 1 入口】
    检查 E:\\zhibodou-ai\\zhibodou\\android_agent\\app\\release\\app-release.apk 安装状态、
    打开智博豆助手并自检无障碍服务；若未开启则全自动点击引导开启。
    """
    online = adb_utils.adb_devices_online()
    if not online:
        return False, "未检测到在线 ADB 手机设备，请连接手机并开启 USB 调试"

    # 1. 检查是否安装
    installed = adb_utils.is_app_installed(AGENT_PKG)
    if installed is False:
        apk_path = ZHIBODOU_AGENT_APK
        if not os.path.exists(apk_path):
            return False, f"未找到智博豆助手安装包: {apk_path}"

        _log(f"【智博豆助手】手机尚未安装助手，正在通过 ADB 安装 {os.path.basename(apk_path)}...", log_fn)
        out, ok = _adb_exec(["install", "-r", apk_path], serial=serial, timeout=30)
        if not ok or "Success" not in out:
            return False, f"智博豆助手安装失败: {out.strip()}"
        _log("【智博豆助手】✅ APK 安装成功！", log_fn)
        time.sleep(1.0)

    # 2. 检查无障碍服务状态：优先底层尝试快速激活
    if not is_accessibility_service_enabled(serial=serial):
        try:
            _adb_exec(["shell", "settings", "put", "secure", "enabled_accessibility_services", AGENT_SERVICE], serial=serial)
            _adb_exec(["shell", "settings", "put", "secure", "accessibility_enabled", "1"], serial=serial)
            time.sleep(0.6)
        except Exception:
            pass

    if is_accessibility_service_enabled(serial=serial):
        _log("【智博豆助手】✅ 无障碍服务已处于开启激活状态", log_fn)
        return True, "智博豆助手无障碍服务已激活"

    # 3. 执行自动引导开启流程
    ok = activate_accessibility_ui_flow(serial=serial, log_fn=log_fn)
    if ok:
        return True, "智博豆助手无障碍服务自动开启成功"
    else:
        return False, "无障碍服务自动开启未完全完成，请在手机辅助功能设置中人工核对"


def check_and_open_doubao(
    serial: Optional[str] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """
    【条件 2 入口】
    检查系统是否安装豆包 (com.larus.nova)：
    - 若没有：返回 False 并提示上应用商店安装；
    - 若已安装：直接打开豆包，并确保手机停留在豆包界面，方便后续话术交互。
    """
    online = adb_utils.adb_devices_online()
    if not online:
        return False, "未检测到在线 ADB 手机设备，无法检测豆包"

    # 1. 检查豆包是否安装
    installed = adb_utils.is_app_installed(DOUBAO_PKG)
    if installed is False:
        msg = "❌ 手机尚未安装「豆包」APP！请前往手机应用商店搜索并安装「豆包」后再启动直播。"
        _log(f"【豆包自检】{msg}", log_fn)
        return False, msg

    # 2. 豆包已安装，唤起打开
    _log("【豆包就绪】手机已安装豆包，正在唤醒并切换至前台...", log_fn)
    # 优先使用 monkey 启动对应 launcher 意图
    _adb_exec(["shell", "monkey", "-p", DOUBAO_PKG, "-c", "android.intent.category.LAUNCHER", "1"], serial=serial, timeout=5)
    _adb_exec(["shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", DOUBAO_PKG], serial=serial, timeout=5)

    # 3. 循环探测是否已成功置顶前台
    for _ in range(8):
        time.sleep(0.5)
        if adb_utils.doubao_in_foreground():
            _log("【豆包就绪】✅ 豆包已在前台打开，手机停留在豆包对话界面，话术交互链路畅通", log_fn)
            return True, "✅ 豆包已打开并在前台就绪"

    _log("【豆包就绪】已发送打开指令，豆包正在加载中", log_fn)
    return True, "豆包已唤起"


def run_prerun_inspections(
    serial: Optional[str] = None,
    log_fn: Optional[Callable[[str], None]] = None,
    interactive: bool = True,
) -> tuple[bool, list[str]]:
    """
    【运行前总检统一入口】
    串联执行：
    1. 智博豆助手无障碍安装/开启检测与自动引导；
    2. 豆包安装检测与自动打开。
    """
    problems = []

    online = adb_utils.adb_devices_online()
    if not online:
        problems.append("ℹ️ 未检测到在线 ADB 设备（处于手动模式）")
        return False, problems

    _log("========== 运行前设备先决条件全自动自检开始 ==========", log_fn)

    # 1. 智博豆助手无障碍
    ok1, msg1 = check_and_setup_zhibodou_agent(serial=serial, log_fn=log_fn)
    if not ok1:
        problems.append(msg1)

    # 2. 豆包检测与打开
    ok2, msg2 = check_and_open_doubao(serial=serial, log_fn=log_fn)
    if not ok2:
        problems.append(msg2)
        if interactive:
            try:
                import tkinter.messagebox as mb
                mb.showwarning("缺少豆包 APP", msg2)
            except Exception:
                pass

    _log("========== 运行前设备先决条件自检结束 ==========", log_fn)
    return (len(problems) == 0), problems
