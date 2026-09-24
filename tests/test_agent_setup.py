import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from device import agent_setup
from core.paths import ZHIBODOU_AGENT_APK


class TestAgentSetup(unittest.TestCase):
    def test_parse_bounds(self):
        """测试 [left,top][right,bottom] 坐标解析"""
        self.assertEqual(agent_setup._parse_bounds("[100,200][300,400]"), (100, 200, 300, 400))
        self.assertIsNone(agent_setup._parse_bounds(""))
        self.assertIsNone(agent_setup._parse_bounds("[300,400][100,200]"))  # 反转无效
        self.assertIsNone(agent_setup._parse_bounds("invalid_bounds"))

    def test_find_node_by_keywords(self):
        """测试在 XML UI 树中按关键词匹配节点"""
        import xml.etree.ElementTree as ET
        xml_data = """<?xml version="1.0" encoding="utf-8"?>
        <hierarchy rotation="0">
            <node text="辅助功能" class="android.widget.TextView" bounds="[0,0][1080,200]" />
            <node text="已安装的应用程序" class="android.widget.TextView" bounds="[50,300][900,400]" />
            <node text="智博豆助手" content-desc="已关闭" class="android.widget.TextView" bounds="[50,500][900,600]" />
        </hierarchy>
        """
        root = ET.fromstring(xml_data)
        
        node = agent_setup._find_node_by_keywords(root, ["已安装的应用程序"])
        self.assertIsNotNone(node)
        self.assertEqual(node.get("text"), "已安装的应用程序")

        node2 = agent_setup._find_node_by_keywords(root, ["智博豆助手"])
        self.assertIsNotNone(node2)
        self.assertEqual(node2.get("text"), "智博豆助手")

        # 未匹配关键词
        node_none = agent_setup._find_node_by_keywords(root, ["不存在的按钮"])
        self.assertIsNone(node_none)

    def test_find_switch_node(self):
        """测试查找开关控件"""
        import xml.etree.ElementTree as ET
        xml_data = """<?xml version="1.0" encoding="utf-8"?>
        <hierarchy rotation="0">
            <node text="使用智博豆助手" class="android.widget.TextView" bounds="[50,200][600,300]" />
            <node text="关" class="android.widget.Switch" checked="false" bounds="[850,220][1000,280]" />
        </hierarchy>
        """
        root = ET.fromstring(xml_data)
        switch = agent_setup._find_switch_node(root)
        self.assertIsNotNone(switch)
        self.assertEqual(switch.get("bounds"), "[850,220][1000,280]")

    @patch("device.input_text._is_agent_alive", return_value=False)
    @patch("device.input_text._ensure_agent_forward", return_value=True)
    @patch("device.agent_setup._adb_exec")
    def test_is_accessibility_service_enabled(self, mock_adb, mock_fwd, mock_alive):
        """测试无障碍服务激活状态判定"""
        # 已开启
        mock_adb.side_effect = [
            ("com.zhibodou.agent/com.zhibodou.agent.DoubaoAccessibilityService", True),
            ("1", True),
        ]
        self.assertTrue(agent_setup.is_accessibility_service_enabled())

        # 未开启
        mock_adb.side_effect = [
            ("com.other.service/service", True),
            ("1", True),
        ]
        self.assertFalse(agent_setup.is_accessibility_service_enabled())

    @patch("device.adb_utils.adb_devices_online", return_value=["device-serial-001"])
    @patch("device.adb_utils.is_app_installed", return_value=False)
    @patch("device.agent_setup.ZHIBODOU_AGENT_APK", "mock_not_found.apk")
    def test_check_and_setup_apk_not_found(self, mock_installed, mock_devices):
        """测试 APK 不存在时的友好拦截提示"""
        ok, msg = agent_setup.check_and_setup_zhibodou_agent()
        self.assertFalse(ok)
        self.assertIn("未找到智博豆助手安装包", msg)

    @patch("device.adb_utils.adb_devices_online", return_value=["device-serial-001"])
    @patch("device.adb_utils.is_app_installed", return_value=True)
    @patch("device.agent_setup.is_accessibility_service_enabled", return_value=True)
    def test_check_and_setup_already_enabled(self, mock_acc, mock_installed, mock_devices):
        """测试无障碍服务已经激活时的快速通过"""
        ok, msg = agent_setup.check_and_setup_zhibodou_agent()
        self.assertTrue(ok)
        self.assertIn("已激活", msg)

    @patch("device.adb_utils.adb_devices_online", return_value=["device-serial-001"])
    @patch("device.adb_utils.is_app_installed", return_value=False)
    def test_check_and_open_doubao_not_installed(self, mock_installed, mock_devices):
        """测试未安装豆包时提示前往应用商店安装"""
        ok, msg = agent_setup.check_and_open_doubao()
        self.assertFalse(ok)
        self.assertIn("未安装「豆包」APP", msg)
        self.assertIn("应用商店", msg)

    @patch("device.adb_utils.adb_devices_online", return_value=["device-serial-001"])
    @patch("device.adb_utils.is_app_installed", return_value=True)
    @patch("device.adb_utils.doubao_in_foreground", return_value=True)
    @patch("device.agent_setup._adb_exec", return_value=("", True))
    def test_check_and_open_doubao_installed(self, mock_adb, mock_fg, mock_installed, mock_devices):
        """测试已安装豆包时自动唤起至前台"""
        ok, msg = agent_setup.check_and_open_doubao()
        self.assertTrue(ok)
        self.assertIn("就绪", msg)

    @patch("device.adb_utils.adb_devices_online", return_value=[])
    def test_run_prerun_offline(self, mock_devices):
        """测试无设备连接时的状态"""
        ok, problems = agent_setup.run_prerun_inspections(interactive=False)
        self.assertFalse(ok)
        self.assertTrue(any("手动模式" in p for p in problems))

    @patch("device.agent_setup._adb_exec", return_value=("", True))
    @patch("device.agent_setup._tap_bounds", return_value=True)
    @patch("device.agent_setup._dump_ui_hierarchy")
    @patch("device.agent_setup.is_accessibility_service_enabled", side_effect=[False, True])
    def test_activate_accessibility_ui_flow(self, mock_acc_enabled, mock_dump, mock_tap, mock_adb):
        """测试无障碍自动化引导点击完整流程"""
        import xml.etree.ElementTree as ET
        # 模拟设置界面
        xml_setting = """<?xml version="1.0" encoding="utf-8"?>
        <hierarchy rotation="0">
            <node text="👉 点击开启无障碍服务 (Accessibility)" bounds="[100,500][900,600]" />
            <node text="已安装的应用程序" bounds="[100,700][900,800]" />
            <node text="智博豆助手" bounds="[100,900][900,1000]" />
            <node text="关" class="android.widget.Switch" checked="false" bounds="[850,220][1000,280]" />
            <node text="允许" class="android.widget.Button" bounds="[600,1500][900,1600]" />
        </hierarchy>
        """
        mock_dump.return_value = ET.fromstring(xml_setting)

        res = agent_setup.activate_accessibility_ui_flow()
        self.assertTrue(res)
        self.assertTrue(mock_tap.called)

    @patch("device.adb_utils.adb_devices_online", return_value=["device-serial-001"])
    @patch("device.adb_utils.is_app_installed", return_value=True)
    @patch("device.adb_utils.doubao_in_foreground", side_effect=[False, True])
    @patch("device.agent_setup.check_and_open_doubao", return_value=(True, "OK"))
    def test_doubao_check_ready_auto_opens_doubao(self, mock_open, mock_fg, mock_inst, mock_online):
        """测试 doubao_check.check_doubao_ready 自动唤起豆包"""
        from device import doubao_check
        ok, problems, mode = doubao_check.check_doubao_ready()
        self.assertTrue(ok)
        self.assertEqual(len(problems), 0)
        self.assertTrue(mock_open.called)


if __name__ == "__main__":
    unittest.main()
