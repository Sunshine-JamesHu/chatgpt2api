from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from typing import Any, AsyncIterator, Callable, Iterator, TypeVar

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


T = TypeVar("T")


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class ExecutorSaturated(RuntimeError):
    pass


class _AdmissionGate:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self._semaphore = threading.BoundedSemaphore(self.limit)
        self._lock = threading.Lock()
        self._active = 0
        self._rejected = 0

    def try_acquire(self) -> bool:
        if not self._semaphore.acquire(blocking=False):
            with self._lock:
                self._rejected += 1
            return False
        with self._lock:
            self._active += 1
        return True

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
        self._semaphore.release()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "limit": self.limit,
                "active": self._active,
                "available": max(0, self.limit - self._active),
                "rejected": self._rejected,
            }


class _ReleaseOnce:
    def __init__(self, semaphore: threading.BoundedSemaphore) -> None:
        self._semaphore = semaphore
        self._lock = threading.Lock()
        self._released = False

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._semaphore.release()


class BoundedExecutor:
    def __init__(self, name: str, max_workers: int, max_queue: int) -> None:
        self.name = name
        self.max_workers = max(1, int(max_workers))
        self.max_queue = max(0, int(max_queue))
        self._slots = threading.BoundedSemaphore(self.max_workers + self.max_queue)
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix=name)
        self._lock = threading.Lock()
        self._queued = 0
        self._active = 0
        self._rejected = 0

    def submit(self, func: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T]:
        if not self._slots.acquire(blocking=False):
            with self._lock:
                self._rejected += 1
            raise ExecutorSaturated(f"{self.name} queue is full")

        release_once = _ReleaseOnce(self._slots)
        with self._lock:
            self._queued += 1

        def run() -> T:
            with self._lock:
                self._queued = max(0, self._queued - 1)
                self._active += 1
            try:
                return func(*args, **kwargs)
            finally:
                with self._lock:
                    self._active = max(0, self._active - 1)
                release_once.release()

        try:
            future = self._executor.submit(run)
        except BaseException:
            with self._lock:
                self._queued = max(0, self._queued - 1)
            release_once.release()
            raise

        def release_cancelled(done: Future[T]) -> None:
            if not done.cancelled():
                return
            with self._lock:
                self._queued = max(0, self._queued - 1)
            release_once.release()

        future.add_done_callback(release_cancelled)
        return future

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "workers": self.max_workers,
                "queue_limit": self.max_queue,
                "active": self._active,
                "queued": self._queued,
                "rejected": self._rejected,
            }

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


class ConcurrencyRuntime:
    def __init__(
        self,
        *,
        ai_max_concurrency: int = 100,
        ai_workers: int = 100,
        image_task_workers: int = 32,
        image_task_queue: int = 256,
        editable_task_workers: int = 16,
        editable_task_queue: int = 128,
        image_subtask_workers: int = 64,
        image_subtask_queue: int = 400,
    ) -> None:
        self.ai_gate = _AdmissionGate(ai_max_concurrency)
        self.ai_workers = max(ai_max_concurrency, ai_workers)
        self.ai_requests = BoundedExecutor("ai-request", self.ai_workers, 0)
        self.image_tasks = BoundedExecutor("image-task", image_task_workers, image_task_queue)
        self.editable_tasks = BoundedExecutor("editable-task", editable_task_workers, editable_task_queue)
        self.image_subtasks = BoundedExecutor("image-subtask", image_subtask_workers, image_subtask_queue)

    async def run_ai(self, func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
        future = self.ai_requests.submit(partial(func, *args, **kwargs))
        return await asyncio.wrap_future(future)

    async def next_ai(self, iterator: Iterator[T]) -> tuple[bool, T | None]:
        def next_item() -> tuple[bool, T | None]:
            try:
                return True, next(iterator)
            except StopIteration:
                return False, None

        return await self.run_ai(next_item)

    async def iterate_ai(self, iterator: Iterator[T]) -> AsyncIterator[T]:
        while True:
            has_item, item = await self.next_ai(iterator)
            if not has_item:
                return
            yield item  # type: ignore[misc]

    def snapshot(self) -> dict[str, object]:
        return {
            "ai": {
                **self.ai_gate.snapshot(),
                "workers": self.ai_workers,
                "executor": self.ai_requests.snapshot(),
            },
            "executors": {
                "image_tasks": self.image_tasks.snapshot(),
                "editable_tasks": self.editable_tasks.snapshot(),
                "image_subtasks": self.image_subtasks.snapshot(),
            },
        }

    def shutdown(self, wait: bool = True) -> None:
        self.ai_requests.shutdown(wait=wait)
        self.image_tasks.shutdown(wait=wait)
        self.editable_tasks.shutdown(wait=wait)
        self.image_subtasks.shutdown(wait=wait)


concurrency_runtime = ConcurrencyRuntime(
    ai_max_concurrency=_env_int("CHATGPT2API_AI_MAX_CONCURRENCY", 100),
    ai_workers=_env_int("CHATGPT2API_AI_WORKERS", 100),
    image_task_workers=_env_int("CHATGPT2API_IMAGE_TASK_WORKERS", 32),
    image_task_queue=_env_int("CHATGPT2API_IMAGE_TASK_QUEUE", 256, minimum=0),
    editable_task_workers=_env_int("CHATGPT2API_EDITABLE_TASK_WORKERS", 16),
    editable_task_queue=_env_int("CHATGPT2API_EDITABLE_TASK_QUEUE", 128, minimum=0),
    image_subtask_workers=_env_int("CHATGPT2API_IMAGE_SUBTASK_WORKERS", 64),
    image_subtask_queue=_env_int("CHATGPT2API_IMAGE_SUBTASK_QUEUE", 400, minimum=0),
)


class AIConcurrencyMiddleware:
    def __init__(self, app: ASGIApp, runtime: ConcurrencyRuntime = concurrency_runtime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path") or "")
        is_ai_request = scope.get("type") == "http" and (path == "/v1" or path.startswith("/v1/"))
        if not is_ai_request:
            await self.app(scope, receive, send)
            return

        if not self.runtime.ai_gate.try_acquire():
            response = JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "message": "server is at the concurrent AI request limit",
                        "type": "server_overloaded",
                        "code": "concurrency_limit_exceeded",
                    }
                },
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except ExecutorSaturated:
            response = JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "message": "server AI workers are still busy",
                        "type": "server_overloaded",
                        "code": "worker_capacity_exceeded",
                    }
                },
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send)
        finally:
            self.runtime.ai_gate.release()
