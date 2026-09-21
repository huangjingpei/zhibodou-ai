import os
import sys
import unittest
from unittest import mock

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from audio.vad import VAD_ENDED, VAD_START_TIMEOUT, VAD_AUDIO_ERROR
from core import state
from broadcast import live


class ResultMonitor:
    def __init__(self, result):
        self.result = result

    def wait_for_doubao_speech_cycle(self, **_kwargs):
        return self.result

    def close(self):
        pass


class LiveDispatchAndVadSafetyTests(unittest.TestCase):
    def setUp(self):
        live._live_generation = 0
        live._current_monitor = None
        live.can_next_speak = False
        state.is_broadcasting = True
        state.online_num = 0

    def tearDown(self):
        state.is_broadcasting = False

    @staticmethod
    def _cfg():
        return {"wait_start": 25.0, "silence_hold": 4.0}

    def test_start_timeout_continues_without_halting_broadcast(self):
        """超时未开口时，记录日志并自动放行下一轮，绝不能中止直播"""
        with mock.patch.object(live.ui, "log_screen"), \
                mock.patch.object(live.ui, "reset_volume_meter"):
            live.wait_next_round_worker(
                ResultMonitor(VAD_START_TIMEOUT), 0, None, self._cfg()
            )
        self.assertTrue(state.is_broadcasting, "直播状态必须保持运行，不可自动停播")
        self.assertTrue(live.can_next_speak, "必须放行下一轮以继续轮询")

    def test_audio_error_recovers_without_halting_broadcast(self):
        """音频临时异常时，自动恢复并放行下一轮，绝不能中止直播"""
        with mock.patch.object(live.ui, "log_screen"), \
                mock.patch.object(live.ui, "reset_volume_meter"), \
                mock.patch("time.sleep"):
            live.wait_next_round_worker(
                ResultMonitor(VAD_AUDIO_ERROR), 0, None, self._cfg()
            )
        self.assertTrue(state.is_broadcasting, "直播状态必须保持运行")
        self.assertTrue(live.can_next_speak, "必须放行下一轮")

    def test_only_confirmed_end_releases_next_script(self):
        """播报完成确认静音后，放行下一轮"""
        with mock.patch.object(live.ui, "log_screen"), \
                mock.patch.object(live.ui, "reset_volume_meter"):
            live.wait_next_round_worker(ResultMonitor(VAD_ENDED), 0, None, self._cfg())
        self.assertTrue(live.can_next_speak)

    def test_every_doubao_prompt_is_constrained_to_host_speech(self):
        with mock.patch.object(
            live.config,
            "load_config",
            return_value={"doubao_host_prompt": "只输出主播口播，不要对话。"},
        ):
            prompt = live.build_doubao_host_prompt("介绍这款日用品")
        self.assertIn("只输出主播口播，不要对话。", prompt)
        self.assertIn("介绍这款日用品", prompt)

    def test_doubao_prompt_fuses_product_name_desc_and_pre_meet(self):
        mock_ctx = {
            "product_name": "智能温显保温杯",
            "product_desc": "原价99元今日特惠29.9包邮，48小时顺丰发货，假一赔三",
            "pre_meet_text": "全场现货直接拍，下方小黄车1号链接",
        }
        with mock.patch.object(live, "_get_product_context", return_value=mock_ctx), \
                mock.patch.object(live.config, "load_config", return_value={}):
            prompt = live.build_doubao_host_prompt("留人话术要求500字")
        self.assertIn("智能温显保温杯", prompt)
        self.assertIn("原价99元今日特惠29.9包邮，48小时顺丰发货，假一赔三", prompt)
        self.assertIn("全场现货直接拍，下方小黄车1号链接", prompt)
        self.assertIn("留人话术要求500字", prompt)

    def test_select_script_by_online_count_range_01(self):
        """在线人数 15 人，命中区间 01 (0~30)"""
        state.online_num = 15
        mock_cfg = {
            "r1_min": "0", "r1_max": "30", "cmd1": "话术01内容",
            "r2_min": "30", "r2_max": "100", "cmd2": "话术02内容",
            "r3_min": "100", "r3_max": "9999", "cmd3": "话术03内容",
        }
        with mock.patch.object(live, "_get_active_script_config", return_value=mock_cfg):
            label, text, cnt, rng = live.select_script_by_online_count()
        self.assertEqual(label, "区间01")
        self.assertEqual(text, "话术01内容")
        self.assertEqual(cnt, 15)

    def test_select_script_by_online_count_range_02(self):
        """在线人数 50 人，命中区间 02 (30~100)"""
        state.online_num = 50
        mock_cfg = {
            "r1_min": "0", "r1_max": "30", "cmd1": "话术01内容",
            "r2_min": "30", "r2_max": "100", "cmd2": "话术02内容",
            "r3_min": "100", "r3_max": "9999", "cmd3": "话术03内容",
        }
        with mock.patch.object(live, "_get_active_script_config", return_value=mock_cfg):
            label, text, cnt, rng = live.select_script_by_online_count()
        self.assertEqual(label, "区间02")
        self.assertEqual(text, "话术02内容")
        self.assertEqual(cnt, 50)

    def test_select_script_by_online_count_range_03(self):
        """在线人数 180 人，命中区间 03 (100~9999)"""
        state.online_num = 180
        mock_cfg = {
            "r1_min": "0", "r1_max": "30", "cmd1": "话术01内容",
            "r2_min": "30", "r2_max": "100", "cmd2": "话术02内容",
            "r3_min": "100", "r3_max": "9999", "cmd3": "话术03内容",
        }
        with mock.patch.object(live, "_get_active_script_config", return_value=mock_cfg):
            label, text, cnt, rng = live.select_script_by_online_count()
        self.assertEqual(label, "区间03")
        self.assertEqual(text, "话术03内容")
        self.assertEqual(cnt, 180)

    def test_select_script_by_online_count_overflow_range_03(self):
        """在线人数 20000 人（超过 r3_max），依然命中最高区间 03"""
        state.online_num = 20000
        mock_cfg = {
            "r1_min": "0", "r1_max": "30", "cmd1": "话术01内容",
            "r2_min": "30", "r2_max": "100", "cmd2": "话术02内容",
            "r3_min": "100", "r3_max": "9999", "cmd3": "话术03内容",
        }
        with mock.patch.object(live, "_get_active_script_config", return_value=mock_cfg):
            label, text, cnt, rng = live.select_script_by_online_count()
        self.assertEqual(label, "区间03")
        self.assertEqual(text, "话术03内容")
        self.assertEqual(cnt, 20000)

    def test_select_script_empty_fallback(self):
        """命中的区间话术为空时，自动兜底到其他非空区间话术"""
        state.online_num = 50  # 命中区间 02
        mock_cfg = {
            "r1_min": "0", "r1_max": "30", "cmd1": "话术01兜底文本",
            "r2_min": "30", "r2_max": "100", "cmd2": "",  # 空
            "r3_min": "100", "r3_max": "9999", "cmd3": "",
        }
        with mock.patch.object(live, "_get_active_script_config", return_value=mock_cfg):
            label, text, cnt, rng = live.select_script_by_online_count()
        self.assertIn("区间02", label)
        self.assertEqual(text, "话术01兜底文本")

    def test_stop_live_invokes_silence_phone_and_cancels_vad(self):
        """点击停止直播时，必须触发 silence_phone_playback、取消 VAD 并停止广播"""
        with mock.patch.object(live, "silence_phone_playback") as mock_silence, \
                mock.patch.object(live.danmu, "stop_danmu_capture"), \
                mock.patch.object(live.capture, "stop_capture"), \
                mock.patch.object(live.ui, "set_status"), \
                mock.patch.object(live.ui, "log_screen"):
            live.stop_live()
            mock_silence.assert_called_once()
            self.assertFalse(state.is_broadcasting)
            self.assertFalse(state.live_running)

    def test_start_live_closes_all_script_notepads(self):
        """开播时必须自动关闭所有打开的话术记事本，确保最新编辑内容落盘"""
        state.system_power = True
        state.is_broadcasting = False
        with mock.patch("broadcast.script_files.close_all_script_notepads") as mock_close, \
                mock.patch.object(live.danmu, "start_danmu_capture"), \
                mock.patch.object(live.capture, "start_capture"), \
                mock.patch.object(live.ui, "set_status"), \
                mock.patch.object(live.ui, "log_screen"), \
                mock.patch.object(live.ui, "reset_volume_meter"), \
                mock.patch("threading.Thread"):
            live.start_live()
            mock_close.assert_called_once()
            self.assertTrue(state.is_broadcasting)

    def test_get_active_script_config_reads_from_txt_files(self):
        """_get_active_script_config 必须直接从 01.txt, 02.txt, 03.txt 读取话术"""
        with mock.patch("broadcast.script_files.read_script_content", side_effect=lambda k: f"来自{k}.txt的脚本"):
            cfg = live._get_active_script_config()
            self.assertEqual(cfg["cmd1"], "来自01.txt的脚本")
            self.assertEqual(cfg["cmd2"], "来自02.txt的脚本")
            self.assertEqual(cfg["cmd3"], "来自03.txt的脚本")


if __name__ == "__main__":
    unittest.main()
