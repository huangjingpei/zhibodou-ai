import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


class TestLoginAndUIUpdates(unittest.TestCase):
    def test_login_notice_only_shows_on_error(self):
        from gui.login import LoginWindow

        parent = MagicMock()
        window = LoginWindow.__new__(LoginWindow)
        window.parent = parent

        with patch("gui.login.messagebox.showerror") as mock_err, \
             patch("gui.login.messagebox.showinfo") as mock_info:
            # error=False: should NOT show any messagebox
            window._notice("登录成功", error=False)
            mock_err.assert_not_called()
            mock_info.assert_not_called()

            # error=True: should call showerror
            window._notice("网络超时", error=True)
            mock_err.assert_called_once()
            mock_info.assert_not_called()

    def test_login_auth_succeeded_transitions_without_popup(self):
        from gui.login import LoginWindow

        parent = MagicMock()
        window = LoginWindow.__new__(LoginWindow)
        window.parent = parent
        window._auth_busy = True
        window.on_success = MagicMock()
        window._remember_hint_var = MagicMock()
        window._saved_creds = {}

        with patch("gui.login.credential_store.save", return_value=True), \
             patch("gui.login.credential_store.load", return_value={"phone": "13800000000"}), \
             patch("gui.login.messagebox.showinfo") as mock_info, \
             patch("gui.login.messagebox.showerror") as mock_err:
            window._auth_succeeded({"ok": True}, phone="13800000000", password="pass")

            self.assertFalse(window._auth_busy)
            mock_info.assert_not_called()
            mock_err.assert_not_called()
            # Verify after(50, self.on_success) was called
            parent.after.assert_called_with(50, window.on_success)

    def test_ui_controls_no_audio_mode_button(self):
        from gui import ui
        self.assertFalse(hasattr(ui, "btn_audio_mode") and ui.btn_audio_mode is not None,
                         "ui should not have an active btn_audio_mode")

    def test_live_has_no_toggle_audio_mode(self):
        from broadcast import live
        self.assertFalse(hasattr(live, "toggle_audio_mode"),
                         "live module should not have toggle_audio_mode")
        self.assertFalse(hasattr(live, "inner_audio_mode"),
                         "live module should not have inner_audio_mode")


if __name__ == "__main__":
    unittest.main()
