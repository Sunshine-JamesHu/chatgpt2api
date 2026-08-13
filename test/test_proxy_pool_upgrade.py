from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.account_service import AccountService
from services.config import ConfigStore
from services.proxy_service import ProxySettingsStore
from services.storage.json_storage import JSONStorageBackend


class ProxyPoolUpgradeTests(unittest.TestCase):
    def test_old_config_and_account_proxy_are_preserved_after_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.json"
            accounts_path = root / "accounts.json"
            config_path.write_text(json.dumps({"auth-key": "test-key", "proxy": "http://global.example:8080"}), encoding="utf-8")
            accounts_path.write_text(json.dumps([{
                "access_token": "legacy-token",
                "proxy": "socks5://legacy-account.example:1080",
                "status": "正常",
            }]), encoding="utf-8")

            old_config = ConfigStore(config_path)
            account = AccountService(JSONStorageBackend(accounts_path)).get_account("legacy-token")

            self.assertEqual(old_config.get_proxy_pool(), [])
            self.assertIsNotNone(account)
            assert account is not None
            self.assertEqual(account["proxy"], "socks5://legacy-account.example:1080")
            self.assertIsNone(account["proxy_id"])
            kwargs = ProxySettingsStore(old_config).build_session_kwargs(account=account, upstream=True)
            self.assertEqual(kwargs["proxy"], "socks5h://legacy-account.example:1080")


if __name__ == "__main__":
    unittest.main()
