from __future__ import annotations

import unittest
from unittest.mock import patch

from services.oauth_login_service import OAuthLoginError, OAuthLoginService
from services.proxy_pool_service import ProxyPoolError
from services.proxy_service import ProxyResolutionError, ProxySettingsStore
from services.account_service import account_service


class FakeConfig:
    def __init__(self, legacy_proxy: str = "") -> None:
        self.legacy_proxy = legacy_proxy

    def get_proxy_settings(self) -> str:
        return self.legacy_proxy

    def get_proxy_runtime_settings(self) -> dict[str, object]:
        return {"enabled": True, "egress_mode": "single_proxy", "proxy_url": "http://runtime.example:8080"}


class ProxyPoolOAuthTests(unittest.TestCase):
    def test_account_proxy_id_wins_over_runtime_global_and_legacy_proxy(self) -> None:
        store = ProxySettingsStore(FakeConfig("http://legacy.example:8080"))
        with patch("services.proxy_pool_service.proxy_pool_service.get_url", return_value="socks5h://selected.example:1080") as get_url:
            kwargs = store.build_session_kwargs(account={"proxy_id": "proxy-1", "proxy": "http://old.example:8080"}, upstream=True)

        self.assertEqual(kwargs["proxy"], "socks5h://selected.example:1080")
        get_url.assert_called_once_with("proxy-1")

    def test_missing_account_proxy_id_does_not_fall_back_to_any_other_proxy(self) -> None:
        store = ProxySettingsStore(FakeConfig("http://legacy.example:8080"))
        with patch("services.proxy_pool_service.proxy_pool_service.get_url", side_effect=ProxyPoolError("代理不存在")):
            with self.assertRaises(ProxyResolutionError):
                store.build_session_kwargs(account={"proxy_id": "missing"}, upstream=True)

    def test_oauth_exchange_uses_proxy_url_snapshotted_when_session_started(self) -> None:
        service = OAuthLoginService()
        with patch("services.proxy_pool_service.proxy_pool_service.get_url", return_value="http://selected.example:8080"):
            started = service.start(proxy_id="proxy-1")

        with patch.object(service, "_exchange_code", return_value={"access_token": "a", "refresh_token": "r", "id_token": "i"}) as exchange:
            result = service.finish(started["session_id"], "authorization-code")

        self.assertEqual(result["proxy_id"], "proxy-1")
        self.assertEqual(exchange.call_args.args[3], "http://selected.example:8080")

    def test_oauth_selected_proxy_bypasses_runtime_proxy_precedence(self) -> None:
        class FakeSession:
            kwargs: dict[str, object] = {}

            def __init__(self, **kwargs: object) -> None:
                type(self).kwargs = kwargs

            def post(self, *args: object, **kwargs: object) -> object:
                raise RuntimeError("stop after session creation")

            def close(self) -> None:
                pass

        with patch("services.oauth_login_service.requests.Session", FakeSession):
            with self.assertRaises(OAuthLoginError):
                OAuthLoginService._exchange_code("code", "verifier", "https://callback", "http://selected.example:8080")

        self.assertEqual(FakeSession.kwargs["proxy"], "http://selected.example:8080")

    def test_password_relogin_uses_the_account_proxy_id(self) -> None:
        account = {"proxy_id": "proxy-1", "proxy": "http://legacy-account.example:8080"}

        with patch("services.proxy_pool_service.proxy_pool_service.get_url", return_value="socks5h://selected.example:1080") as get_url:
            with patch("curl_cffi.requests.Session") as session:
                session.return_value.close.return_value = None
                session.return_value.get.side_effect = RuntimeError("stop after session creation")
                with self.assertRaises(RuntimeError):
                    account_service._login_with_password("user@example.com", "password", account)

        self.assertEqual(session.call_args.kwargs["proxy"], "socks5h://selected.example:1080")
        get_url.assert_called_once_with("proxy-1")

    def test_password_relogin_does_not_fall_back_when_account_proxy_is_missing(self) -> None:
        account = {"proxy_id": "missing", "proxy": "http://legacy-account.example:8080"}

        with patch("services.proxy_pool_service.proxy_pool_service.get_url", side_effect=ProxyPoolError("proxy missing")):
            with patch("curl_cffi.requests.Session") as session:
                with self.assertRaises(ProxyResolutionError):
                    account_service._login_with_password("user@example.com", "password", account)

        session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
