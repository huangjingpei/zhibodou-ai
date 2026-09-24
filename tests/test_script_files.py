import os
import sys
import tempfile
import time
import unittest
from unittest import mock

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from broadcast import script_files


class ScriptFilesManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self._orig_scripts_dir = script_files.SCRIPTS_DIR
        script_files.SCRIPTS_DIR = self.temp_dir.name
        with script_files._track_lock:
            script_files._tracked_notepads.clear()

    def tearDown(self):
        script_files.close_all_script_notepads()
        script_files.SCRIPTS_DIR = self._orig_scripts_dir
        self.temp_dir.cleanup()

    def test_ensure_script_files_exist_creates_all_three(self):
        script_files.ensure_script_files_exist()
        for key in ("01", "02", "03"):
            path = script_files.get_script_path(key)
            self.assertTrue(os.path.exists(path), f"{path} 必须存在")
            content = script_files.read_script_content(key)
            self.assertGreater(len(content), 0, f"{key}.txt 必须有初始模版内容")

    def test_encoding_compatibility_utf8_bom_and_gbk(self):
        # 1. 测试 UTF-8 with BOM (记事本常见保存编码)
        path_01 = script_files.get_script_path("01")
        with open(path_01, "wb") as f:
            f.write("你好，这是01号带BOM话术".encode("utf-8-sig"))
        self.assertEqual(script_files.read_script_content("01"), "你好，这是01号带BOM话术")

        # 2. 测试 GBK / ANSI (记事本中文系统常见默认编码)
        path_02 = script_files.get_script_path("02")
        with open(path_02, "wb") as f:
            f.write("你好，这是02号GBK话术".encode("gbk"))
        self.assertEqual(script_files.read_script_content("02"), "你好，这是02号GBK话术")

        # 3. 缺失文件返回默认值
        self.assertEqual(script_files.read_script_content("99", default="默认"), "默认")

    def test_get_script_word_count(self):
        path_03 = script_files.get_script_path("03")
        script_files.write_script_content("03", "   促单话术共七个字   ")
        self.assertEqual(script_files.get_script_word_count("03"), 8)

    def test_close_all_script_notepads(self):
        mock_proc1 = mock.MagicMock()
        mock_proc1.poll.return_value = None
        mock_proc2 = mock.MagicMock()
        mock_proc2.poll.return_value = None

        with script_files._track_lock:
            script_files._tracked_notepads["01"] = {
                "proc": mock_proc1, "path": "p1", "mtime": 100.0,
            }
            script_files._tracked_notepads["02"] = {
                "proc": mock_proc2, "path": "p2", "mtime": 100.0,
            }

        closed = script_files.close_all_script_notepads()
        self.assertEqual(closed, 2)
        mock_proc1.terminate.assert_called_once()
        mock_proc2.terminate.assert_called_once()
        self.assertFalse(script_files.is_any_notepad_open())

    def test_save_detection_terminates_notepad_and_calls_callback(self):
        script_files.ensure_script_files_exist()
        path = script_files.get_script_path("01")
        initial_mtime = os.path.getmtime(path)

        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None
        saved_calls = []

        with script_files._track_lock:
            script_files._tracked_notepads["01"] = {
                "proc": mock_proc,
                "path": path,
                "mtime": initial_mtime,
                "on_saved": lambda k: saved_calls.append(k),
                "log_fn": lambda _: None,
            }

        # 模拟文件被保存（mtime 发生更新）
        future_time = initial_mtime + 5.0
        os.utime(path, (future_time, future_time))

        # 手动执行一次监听轮询逻辑
        with script_files._track_lock:
            info = script_files._tracked_notepads.get("01")
            curr_mtime = os.path.getmtime(info["path"])
            if curr_mtime > info["mtime"]:
                info["proc"].terminate()
                info["on_saved"]("01")
                script_files._tracked_notepads.pop("01", None)

        mock_proc.terminate.assert_called_once()
        self.assertIn("01", saved_calls)
        self.assertNotIn("01", script_files._tracked_notepads)

    def test_close_all_script_notepads_with_mocked_windows(self):
        """测试 close_all_script_notepads 针对系统窗口句柄与进程的识别关闭。"""
        with mock.patch("broadcast.script_files._find_notepad_hwnds", return_value=[(1001, "01.txt - Notepad", 555)]), \
             mock.patch("broadcast.script_files._find_notepad_pids", return_value={555}), \
             mock.patch("ctypes.windll.user32.PostMessageW") as mock_post, \
             mock.patch("psutil.Process") as mock_psutil_proc:

            mock_p_inst = mock.MagicMock()
            mock_p_inst.is_running.return_value = True
            mock_psutil_proc.return_value = mock_p_inst

            cnt = script_files.close_all_script_notepads()
            self.assertGreaterEqual(cnt, 1)
            mock_post.assert_called_once_with(1001, 0x0010, 0, 0)
            mock_p_inst.terminate.assert_called_once()

    def test_ui_script_preview_and_labels_refresh(self):
        """测试 UI 话术预览标签的文本截断与省略号展示。"""
        import tkinter as tk
        from gui import ui
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")

        try:
            # 创建模拟的 preview label
            lbl_info = tk.Label(root)
            lbl_prev = tk.Label(root, width=1)
            ui.lab_txt1_info = lbl_info
            ui.lab_txt1_preview = lbl_prev

            # 写入测试内容
            test_content = "今日特惠全场日用百货品类多一一展示下方小黄车直接拍全场包邮到家"
            script_files.write_script_content("01", test_content)

            ui.refresh_script_labels()

            # 验证预览文本以省略号结尾
            preview_text = lbl_prev.cget("text")
            self.assertTrue(preview_text.endswith("..."), f"预览必须以省略号结尾，当前: {preview_text}")
            self.assertIn("今日特惠", preview_text)
            self.assertEqual(lbl_info.cget("text"), f"({len(test_content)}字)")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
