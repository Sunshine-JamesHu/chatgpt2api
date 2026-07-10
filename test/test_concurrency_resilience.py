from __future__ import annotations

import asyncio
import threading
import time
import unittest
from typing import Any
from pathlib import Path
from unittest import mock

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse

from services.concurrency import AIConcurrencyMiddleware, ConcurrencyRuntime
from services.concurrency import ExecutorSaturated
from services.account_service import AccountService
from services.log_service import LoggedCall


ROOT_DIR = Path(__file__).resolve().parents[1]


class MemoryStorage:
    def __init__(self, accounts: list[dict[str, Any]]) -> None:
        self.accounts = [dict(account) for account in accounts]

    def load_accounts(self) -> list[dict[str, Any]]:
        return [dict(account) for account in self.accounts]

    def save_accounts(self, accounts: list[dict[str, Any]]) -> None:
        self.accounts = [dict(account) for account in accounts]

    def load_auth_keys(self) -> list[dict[str, Any]]:
        return []

    def save_auth_keys(self, _auth_keys: list[dict[str, Any]]) -> None:
        return None

    def health_check(self) -> dict[str, Any]:
        return {"ok": True}

    def get_backend_info(self) -> dict[str, Any]:
        return {"type": "memory"}


class ConcurrencyResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = ConcurrencyRuntime(
            ai_max_concurrency=100,
            ai_workers=100,
            image_task_workers=2,
            image_task_queue=100,
            editable_task_workers=2,
            editable_task_queue=100,
            image_subtask_workers=4,
            image_subtask_queue=400,
        )

    async def asyncTearDown(self) -> None:
        self.runtime.shutdown(wait=True)

    async def _wait_for_count(self, get_count, expected: int, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if get_count() >= expected:
                return
            await asyncio.sleep(0.01)
        self.fail(f"timed out waiting for {expected} active calls; got {get_count()}")

    async def test_100_blocked_streams_keep_ui_responsive_and_reject_overflow(self) -> None:
        release = threading.Event()
        count_lock = threading.Lock()
        started = 0

        def blocked_stream():
            nonlocal started
            with count_lock:
                started += 1
            if not release.wait(timeout=10):
                raise TimeoutError("test stream release timed out")
            yield {"ok": True}

        def started_count() -> int:
            with count_lock:
                return started

        app = FastAPI()
        app.add_middleware(AIConcurrencyMiddleware, runtime=self.runtime)

        @app.get("/v1/hold")
        async def hold():
            call = LoggedCall(
                {"id": "load-test", "name": "load-test", "role": "user"},
                "/v1/hold",
                "test",
                "load test",
                runtime=self.runtime,
            )
            return await call.run(blocked_stream)

        @app.get("/version")
        async def version():
            return {"version": "test"}

        @app.get("/ui")
        async def ui():
            return FileResponse(ROOT_DIR / "VERSION")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            with mock.patch.object(LoggedCall, "log", return_value=None):
                blockers = [asyncio.create_task(client.get("/v1/hold")) for _ in range(100)]
                try:
                    await self._wait_for_count(started_count, 100)

                    started_at = time.perf_counter()
                    version_response, ui_response = await asyncio.gather(
                        client.get("/version"),
                        client.get("/ui"),
                    )
                    control_latency = time.perf_counter() - started_at

                    self.assertEqual(version_response.status_code, 200)
                    self.assertEqual(ui_response.status_code, 200)
                    self.assertLess(control_latency, 1.0)

                    overflow_started = time.perf_counter()
                    overflow = await client.get("/v1/hold")
                    overflow_latency = time.perf_counter() - overflow_started
                    self.assertEqual(overflow.status_code, 503)
                    self.assertEqual(overflow.headers.get("retry-after"), "1")
                    self.assertLess(overflow_latency, 0.5)
                finally:
                    release.set()
                    responses = await asyncio.gather(*blockers)

        self.assertTrue(all(response.status_code == 200 for response in responses))
        snapshot = self.runtime.snapshot()
        self.assertEqual(snapshot["ai"]["active"], 0)
        self.assertEqual(snapshot["ai"]["limit"], 100)
        self.assertGreaterEqual(snapshot["ai"]["rejected"], 1)

    async def test_background_executor_accepts_100_tasks_with_fixed_workers(self) -> None:
        release = threading.Event()

        def blocked_task() -> None:
            if not release.wait(timeout=10):
                raise TimeoutError("test task release timed out")

        futures = [self.runtime.image_tasks.submit(blocked_task) for _ in range(100)]
        await self._wait_for_count(
            lambda: self.runtime.image_tasks.snapshot()["active"],
            2,
        )
        snapshot = self.runtime.image_tasks.snapshot()
        self.assertEqual(snapshot["active"], 2)
        self.assertEqual(snapshot["queued"], 98)

        self.runtime.image_tasks.submit(blocked_task)
        self.runtime.image_tasks.submit(blocked_task)
        with self.assertRaises(ExecutorSaturated):
            self.runtime.image_tasks.submit(blocked_task)

        release.set()
        for future in futures:
            future.result(timeout=5)

    async def test_cancelled_sync_call_keeps_worker_slot_until_thread_finishes(self) -> None:
        runtime = ConcurrencyRuntime(
            ai_max_concurrency=1,
            ai_workers=1,
            image_task_workers=1,
            image_task_queue=1,
            editable_task_workers=1,
            editable_task_queue=1,
            image_subtask_workers=1,
            image_subtask_queue=1,
        )
        release = threading.Event()
        started = threading.Event()

        def blocked() -> None:
            started.set()
            release.wait(timeout=10)

        task = asyncio.create_task(runtime.run_ai(blocked))
        try:
            await asyncio.to_thread(started.wait, 5)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            self.assertEqual(runtime.snapshot()["ai"]["executor"]["active"], 1)
            with self.assertRaises(ExecutorSaturated):
                await runtime.run_ai(lambda: None)
        finally:
            release.set()
            runtime.shutdown(wait=True)

    async def test_token_refresh_is_per_account_and_single_flight(self) -> None:
        service = AccountService(MemoryStorage([
            {"access_token": "token-a", "refresh_token": "refresh-a", "email": "a@example.com"},
            {"access_token": "token-b", "refresh_token": "refresh-b", "email": "b@example.com"},
        ]))
        barrier = threading.Barrier(2)
        activity_lock = threading.Lock()
        active = 0
        max_active = 0

        def refresh_request(refresh_token: str, _account: dict[str, Any]) -> dict[str, str]:
            nonlocal active, max_active
            with activity_lock:
                active += 1
                max_active = max(max_active, active)
            barrier.wait(timeout=5)
            time.sleep(0.05)
            with activity_lock:
                active -= 1
            suffix = refresh_token.rsplit("-", 1)[-1]
            return {"access_token": f"new-{suffix}", "refresh_token": refresh_token, "id_token": ""}

        with (
            mock.patch.object(service, "_token_needs_refresh", side_effect=lambda token, force=False: token.startswith("token-")),
            mock.patch.object(service, "_request_access_token_refresh", side_effect=refresh_request) as request_refresh,
            mock.patch("services.account_service.log_service.add"),
        ):
            first, second = await asyncio.gather(
                asyncio.to_thread(service.refresh_access_token, "token-a"),
                asyncio.to_thread(service.refresh_access_token, "token-b"),
            )

        self.assertEqual({first, second}, {"new-a", "new-b"})
        self.assertEqual(request_refresh.call_count, 2)
        self.assertEqual(max_active, 2)

        single_service = AccountService(MemoryStorage([
            {"access_token": "token-a", "refresh_token": "refresh-a", "email": "a@example.com"},
        ]))
        same_account_calls = 0

        def single_refresh(refresh_token: str, _account: dict[str, Any]) -> dict[str, str]:
            nonlocal same_account_calls
            same_account_calls += 1
            time.sleep(0.05)
            return {"access_token": "new-a", "refresh_token": refresh_token, "id_token": ""}

        with (
            mock.patch.object(single_service, "_token_needs_refresh", side_effect=lambda token, force=False: token == "token-a"),
            mock.patch.object(single_service, "_request_access_token_refresh", side_effect=single_refresh),
            mock.patch("services.account_service.log_service.add"),
        ):
            results = await asyncio.gather(
                asyncio.to_thread(single_service.refresh_access_token, "token-a"),
                asyncio.to_thread(single_service.refresh_access_token, "token-a"),
            )

        self.assertEqual(results, ["new-a", "new-a"])
        self.assertEqual(same_account_calls, 1)


if __name__ == "__main__":
    unittest.main()
