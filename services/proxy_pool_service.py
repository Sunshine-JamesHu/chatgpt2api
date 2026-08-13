from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from services.config import config
from services.proxy_service import normalize_proxy_url


class ProxyPoolError(ValueError):
    pass


class ProxyPoolService:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_url(value: object) -> str:
        url = normalize_proxy_url(str(value or ""))
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https", "socks4", "socks4a", "socks5", "socks5h"} or not parsed.hostname:
            raise ProxyPoolError("代理地址必须是带协议和主机的 HTTP(S) 或 SOCKS 地址")
        return url

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "url": str(item.get("url") or ""),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }

    def _items_locked(self) -> list[dict[str, Any]]:
        return [dict(item) for item in config.get_proxy_pool() if isinstance(item, dict)]

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._public(item) for item in self._items_locked()]

    def get_url(self, proxy_id: object) -> str:
        wanted = str(proxy_id or "").strip()
        if not wanted:
            return ""
        with self._lock:
            for item in self._items_locked():
                if str(item.get("id") or "") == wanted:
                    return self._normalize_url(item.get("url"))
        raise ProxyPoolError("所选代理不存在或已被删除")

    def create(self, name: object, url: object) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ProxyPoolError("代理名称不能为空")
        clean_url = self._normalize_url(url)
        with self._lock:
            items = self._items_locked()
            if any(str(item.get("name") or "").strip().lower() == clean_name.lower() for item in items):
                raise ProxyPoolError("代理名称已存在")
            now = self._now()
            item = {"id": uuid.uuid4().hex, "name": clean_name, "url": clean_url, "created_at": now, "updated_at": now}
            items.append(item)
            config.save_proxy_pool(items)
            return self._public(item)

    def update(self, proxy_id: object, name: object, url: object) -> dict[str, Any]:
        wanted = str(proxy_id or "").strip()
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ProxyPoolError("代理名称不能为空")
        clean_url = self._normalize_url(url)
        with self._lock:
            items = self._items_locked()
            for item in items:
                if str(item.get("id") or "") == wanted:
                    item.update({"name": clean_name, "url": clean_url, "updated_at": self._now()})
                    config.save_proxy_pool(items)
                    return self._public(item)
        raise ProxyPoolError("代理不存在")

    def delete(self, proxy_id: object, referenced_count: int) -> None:
        wanted = str(proxy_id or "").strip()
        if referenced_count:
            raise ProxyPoolError(f"该代理仍被 {referenced_count} 个账号使用，不能删除")
        with self._lock:
            items = self._items_locked()
            next_items = [item for item in items if str(item.get("id") or "") != wanted]
            if len(next_items) == len(items):
                raise ProxyPoolError("代理不存在")
            config.save_proxy_pool(next_items)


proxy_pool_service = ProxyPoolService()
