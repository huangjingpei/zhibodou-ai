import os
import sys
import unittest
import tkinter as tk
from unittest.mock import patch, MagicMock

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from gui.settings_dialog import SettingsDialog, open_settings_dialog
from settings import config
from pdk import auth_service as pdk_auth


class TestSettingsDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception:
            cls.root = None

    @classmethod
    def tearDownClass(cls):
        if cls.root:
            try:
                cls.root.destroy()
            except Exception:
                pass

    def setUp(self):
        if self.root is None:
            self.skipTest("Tkinter display not available")

    def test_settings_dialog_initialization(self):
        """测试设置对话框正常初始化、包含扁平纵向导航与四个主面板。"""
        dlg = SettingsDialog(self.root)
        try:
            self.assertIsNotNone(dlg.dialog)
            self.assertIn("系统设置中心", dlg.dialog.title())
            self.assertIsNotNone(dlg.nav_buttons)

            # 验证扁平纵向导航项存在
            self.assertIn("ai", dlg.nav_buttons)
            self.assertIn("license", dlg.nav_buttons)
            self.assertIn("audio", dlg.nav_buttons)
            self.assertIn("version", dlg.nav_buttons)

            # 验证四个面板均已注册
            self.assertIn("ai", dlg.panels)
            self.assertIn("license", dlg.panels)
            self.assertIn("audio", dlg.panels)
            self.assertIn("version", dlg.panels)
        finally:
            dlg._on_close()

    def test_navigation_switching(self):
        """测试点击纵向导航按钮切换不同面板及高亮状态。"""
        dlg = SettingsDialog(self.root)
        try:
            # 切换到 license 面板
            dlg._on_nav_click("license")
            self.assertEqual(dlg.current_panel_name, "license")

            # 切换到 audio 面板
            dlg._on_nav_click("audio")
            self.assertEqual(dlg.current_panel_name, "audio")

            # 切换到 version 面板
            dlg._on_nav_click("version")
            self.assertEqual(dlg.current_panel_name, "version")

            # 切换回 ai 面板
            dlg._on_nav_click("ai")
            self.assertEqual(dlg.current_panel_name, "ai")
        finally:
            dlg._on_close()

    def test_license_panel_display(self):
        """测试许可证面板在有有效授权和无授权时的呈现。"""
        dlg = SettingsDialog(self.root)
        try:
            # 模拟有效授权
            mock_auth = MagicMock()
            mock_auth.masked_phone = "139****1234"
            mock_auth.authorization_mode = "DEVICE_LICENSE"
            mock_auth.remaining_calls = 888
            mock_auth.expire_at = "2028-12-31"
            mock_auth.business = {"bizCode": "test_live_biz"}
            mock_auth.session = {}

            with patch.object(pdk_auth, "current_auth", return_value=mock_auth):
                dlg._refresh_license_display()
                self.assertIn("授权有效", dlg.lab_lic_badge.cget("text"))
                self.assertEqual(dlg.lic_fields["phone"].cget("text"), "139****1234")
                self.assertEqual(dlg.lic_fields["biz_code"].cget("text"), "test_live_biz")
                self.assertEqual(dlg.lic_fields["remaining"].cget("text"), "888 次")

            # 模拟未登录/无授权
            with patch.object(pdk_auth, "current_auth", return_value=None):
                dlg._refresh_license_display()
                self.assertIn("未授权", dlg.lab_lic_badge.cget("text"))
        finally:
            dlg._on_close()

    def test_save_settings_persistence(self):
        """测试保存设置能够更新配置并持久化。"""
        dlg = SettingsDialog(self.root)
        try:
            dlg.ent_deepseek_key.delete(0, tk.END)
            dlg.ent_deepseek_key.insert(0, "sk-test-mock-key-12345")
            dlg.var_deepseek_model.set("deepseek-reasoner")
            dlg.slider_duck.set(35)
            dlg._on_duck_slider_change(35)
            dlg.ent_obs_port.delete(0, tk.END)
            dlg.ent_obs_port.insert(0, "8555")
            dlg.ent_vad_silence.delete(0, tk.END)
            dlg.ent_vad_silence.insert(0, "3.5")
            dlg.var_danmu_metrics_only.set(True)
            dlg.var_danmu_mode.set("【自适应】MOSS-TTS-Nano 轻量语音 (显存4-8G)")

            with patch("tkinter.messagebox.showinfo") as mock_info, \
                 patch("core.paths.CONFIG_JSON", "test_temp_config.json"):
                dlg._save_settings()
                mock_info.assert_called_once()

                # 读取验证临时保存的文件
                if os.path.exists("test_temp_config.json"):
                    import json
                    with open("test_temp_config.json", "r", encoding="utf-8") as f:
                        saved = json.load(f)
                    self.assertEqual(saved.get("deepseek_api_key"), "sk-test-mock-key-12345")
                    self.assertEqual(saved.get("deepseek_model"), "deepseek-reasoner")
                    self.assertAlmostEqual(saved.get("audio_duck_ratio"), 0.35)
                    self.assertEqual(saved.get("obs_audio_port"), 8555)
                    self.assertAlmostEqual(saved.get("vad_silence_hold_sec"), 3.5)
                    self.assertTrue(saved.get("danmu_metrics_only"))
                    self.assertEqual(saved.get("danmu_mode"), "【自适应】MOSS-TTS-Nano 轻量语音 (显存4-8G)")
                    os.remove("test_temp_config.json")
        finally:
            dlg._on_close()

    def test_duck_slider_interaction(self):
        """测试声音闪避比例水平滑动条与快捷档位的交互。"""
        dlg = SettingsDialog(self.root)
        try:
            self.assertIsNotNone(dlg.slider_duck)
            # 测试滑动变动
            dlg._on_duck_slider_change(15)
            self.assertEqual(dlg.var_duck_pct.get(), 15)
            self.assertIn("15%", dlg.lab_duck_val.cget("text"))

            # 测试快捷档位触发
            dlg._set_duck_preset(50)
            self.assertEqual(dlg.var_duck_pct.get(), 50)
            self.assertIn("50%", dlg.lab_duck_val.cget("text"))
        finally:
            dlg._on_close()

    def test_open_settings_dialog_helper(self):
        """测试 open_settings_dialog 快捷入口。"""
        dlg = open_settings_dialog(self.root)
        try:
            self.assertIsInstance(dlg, SettingsDialog)
            self.assertTrue(dlg.dialog.winfo_exists())
        finally:
            dlg._on_close()


if __name__ == "__main__":
    unittest.main()
