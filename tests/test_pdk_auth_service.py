import os
import sys
import unittest
from unittest.mock import patch

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from pdk import auth_service  # noqa: E402
from pdk.pdk_client import PdkClientError  # noqa: E402


class FakeClient:
    def __init__(self, _base_url, app_id, phone="", **_kwargs):
        self.app_id = app_id
        self.phone = phone
        self.logged_in = False
        self.closed = False
        self.logout_count = 0
        self.calls = []
        self.timeout = None

    @property
    def is_logged_in(self):
        return self.logged_in

    def fetch_public_config(self):
        self.calls.append("fetch_public_config")
        return {"encryptionMode": "force", "kid": "v1"}

    def business_info(self):
        self.calls.append("business_info")
        return {
            "bizCode": "ZHIBO_LIVE",
            "authorizationMode": "DEVICE_LICENSE",
            "effectiveStatus": "AVAILABLE",
            "configuredStatus": "ACTIVE",
        }

    def login(self, password, **kwargs):
        self.calls.append(("login", password, kwargs.get("card_key", "")))
        self.logged_in = True
        return {"tokenName": "satoken", "tokenValue": "secret", "appId": self.app_id}

    def verify_session(self):
        self.calls.append("verify_session")
        return {
            "sessionValid": True,
            "operationAllowedHint": True,
            "authorizationMode": "DEVICE_LICENSE",
            "bizCode": "ZHIBO_LIVE",
            "status": "ACTIVE",
            "expireAt": "2099-12-31T23:59:59",
        }

    def profile(self):
        self.calls.append("profile")
        return {"remainingCalls": 12, "status": "ACTIVE"}

    def device_license_current(self):
        self.calls.append("device_license_current")
        return {"status": "ACTIVE", "expireAt": "2099-12-31T23:59:59"}

    def logout(self):
        self.calls.append("logout")
        self.logout_count += 1
        self.logged_in = False
        return "ok"

    def clear_session(self):
        self.logged_in = False

    def close(self):
        self.closed = True


class SubscriptionClient(FakeClient):
    def business_info(self):
        info = super().business_info()
        info["authorizationMode"] = "USER_SUBSCRIPTION"
        return info

    def verify_session(self):
        result = super().verify_session()
        result["authorizationMode"] = "USER_SUBSCRIPTION"
        return result


class DisabledSessionClient(FakeClient):
    def verify_session(self):
        result = super().verify_session()
        result["operationAllowedHint"] = False
        result["status"] = "EXPIRED"
        return result


class DisabledLicenseClient(FakeClient):
    def device_license_current(self):
        self.calls.append("device_license_current")
        return {"status": "EXPIRED", "expireAt": "2026-01-01T00:00:00"}


SETTINGS = auth_service.PdkSettings(
    base_url="https://pdk.example.test",
    app_id=3,
    public_key_pin="fingerprint",
    require_https=True,
)


class PdkAuthServiceTests(unittest.TestCase):
    def tearDown(self):
        try:
            auth_service.logout()
        except Exception:
            pass

    def test_device_license_login_calls_complete_contract(self):
        created = []

        def factory(*args, **kwargs):
            client = FakeClient(*args, **kwargs)
            created.append(client)
            return client

        result = auth_service.authenticate(
            "13800138000", "password", "CARD-KEY", settings=SETTINGS,
            client_factory=factory,
        )

        self.assertTrue(auth_service.is_authenticated())
        self.assertEqual("DEVICE_LICENSE", result.authorization_mode)
        self.assertEqual(12, result.remaining_calls)
        self.assertEqual("138****8000", result.masked_phone)
        self.assertIn("device_license_current", created[0].calls)
        self.assertIn(("login", "password", "CARD-KEY"), created[0].calls)

    def test_subscription_login_does_not_call_device_license_endpoint(self):
        created = []

        def factory(*args, **kwargs):
            client = SubscriptionClient(*args, **kwargs)
            created.append(client)
            return client

        result = auth_service.authenticate(
            "13800138000", "password", settings=SETTINGS, client_factory=factory,
        )

        self.assertEqual("USER_SUBSCRIPTION", result.authorization_mode)
        self.assertNotIn("device_license_current", created[0].calls)

    def test_invalid_session_is_logged_out_closed_and_not_published(self):
        created = []

        def factory(*args, **kwargs):
            client = DisabledSessionClient(*args, **kwargs)
            created.append(client)
            return client

        with self.assertRaises(PdkClientError) as ctx:
            auth_service.authenticate(
                "13800138000", "password", settings=SETTINGS, client_factory=factory,
            )

        self.assertEqual(40381, ctx.exception.code)
        self.assertFalse(auth_service.is_authenticated())
        self.assertEqual(1, created[0].logout_count)
        self.assertTrue(created[0].closed)

    def test_invalid_current_device_license_cannot_enter_application(self):
        created = []

        def factory(*args, **kwargs):
            client = DisabledLicenseClient(*args, **kwargs)
            created.append(client)
            return client

        with self.assertRaises(PdkClientError) as ctx:
            auth_service.authenticate(
                "13800138000", "password", settings=SETTINGS, client_factory=factory,
            )

        self.assertEqual(40381, ctx.exception.code)
        self.assertFalse(auth_service.is_authenticated())
        self.assertEqual(1, created[0].logout_count)
        self.assertTrue(created[0].closed)

    def test_logout_clears_runtime_even_when_remote_logout_fails(self):
        class LogoutFailureClient(FakeClient):
            def logout(self):
                raise PdkClientError(0, "network down")

        created = []

        def factory(*args, **kwargs):
            client = LogoutFailureClient(*args, **kwargs)
            created.append(client)
            return client

        auth_service.authenticate(
            "13800138000", "password", "CARD", settings=SETTINGS,
            client_factory=factory,
        )
        with self.assertRaises(PdkClientError):
            auth_service.logout()

        self.assertFalse(auth_service.is_authenticated())
        self.assertTrue(created[0].closed)

    @patch.dict(os.environ, {
        "PDK_BASE_URL": "https://license.example.com",
        "PDK_APP_ID": "9",
        "PDK_REQUIRE_HTTPS": "true",
        "PDK_VERIFY_TLS": "false",
        "PDK_BIZ_CODE": "ZHIBO_LIVE",
    }, clear=False)
    def test_settings_are_loaded_from_environment(self):
        settings = auth_service.PdkSettings.from_env()
        self.assertEqual("https://license.example.com", settings.base_url)
        self.assertEqual(9, settings.app_id)
        self.assertTrue(settings.require_https)
        self.assertFalse(settings.verify_tls)

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_match_pdk_client_demo(self):
        settings = auth_service.PdkSettings.from_env()
        self.assertEqual("http://127.0.0.1:8080", settings.base_url)
        self.assertEqual(2, settings.app_id)
        self.assertEqual("", settings.expected_biz_code)


if __name__ == "__main__":
    unittest.main()
