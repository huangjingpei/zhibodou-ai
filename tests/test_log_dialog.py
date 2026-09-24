"""运行日志独立窗口与日志缓冲区单元测试。"""
import os
import sys
import tkinter as tk
import unittest

sys.path.insert(0, os.path.abspath("src"))

from gui.log_dialog import LogDialog, get_active_log_dialog, open_log_dialog
from gui.ui import get_log_history, log_screen


class TestLogDialog(unittest.TestCase):
    """测试 LogDialog 弹窗与日志追加、复制、清空功能。"""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_log_screen_buffers_history(self):
        """验证 log_screen 会把日志追加到全局历史缓冲区。"""
        log_screen("【测试日志】单元测试日志条目 1")
        history = get_log_history()
        self.assertIn("【测试日志】单元测试日志条目 1", history)

    def test_log_dialog_lifecycle(self):
        """验证 LogDialog 创建、追加日志与单例激活。"""
        dlg = open_log_dialog(self.root, initial_logs="初始测试日志\n")
        self.assertIsNotNone(dlg)
        self.assertEqual(get_active_log_dialog(), dlg)

        # 追加新日志
        dlg.append_log("追加日志条目")
        content = dlg.txt_log.get(1.0, tk.END)
        self.assertIn("初始测试日志", content)
        self.assertIn("追加日志条目", content)

        # 清空日志
        dlg._clear_logs()
        cleared_content = dlg.txt_log.get(1.0, tk.END).strip()
        self.assertEqual(cleared_content, "")

        # 关闭弹窗
        dlg.close()
        self.assertIsNone(get_active_log_dialog())


if __name__ == "__main__":
    unittest.main()
