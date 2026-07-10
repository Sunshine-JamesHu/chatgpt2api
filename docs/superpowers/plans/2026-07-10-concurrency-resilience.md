# 100-Request Concurrency Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the web UI and control APIs responsive while the service sustains 100 concurrent long-running AI requests.

**Architecture:** Put AI handlers and synchronous stream iteration on a dedicated 100-worker executor guarded by a process-wide 100-request admission gate. Keep Starlette's default worker pool available for static files and control APIs, and replace per-task and per-image thread creation with bounded shared executors. Replace the global OAuth refresh lock with per-account single-flight locks.

**Tech Stack:** Python 3.13, FastAPI/Starlette, asyncio, concurrent.futures, httpx ASGI tests, Next.js browser smoke tests.

---

### Task 1: Concurrency runtime and 100-request isolation test

**Files:**
- Create: `services/concurrency.py`
- Create: `test/test_concurrency_resilience.py`
- Modify: `api/app.py`

- [ ] Write an ASGI regression test that starts 100 blocking `/v1/*` requests and verifies a `FileResponse` plus `/version` complete within one second.
- [ ] Add a process-wide AI admission gate with a default limit of 100 and an ASGI middleware that returns HTTP 503 with `Retry-After: 1` when full.
- [ ] Add a dedicated 100-worker AI executor and async helpers for normal calls and iterator advancement.
- [ ] Register the middleware only for long-running `/v1/*` request paths, leaving `/api/*`, `/health`, `/version`, and static assets outside the gate.
- [ ] Run `uv run python -m unittest test.test_concurrency_resilience -v`; expect the saturation, overflow, and UI-isolation cases to pass.

### Task 2: Move long AI work off the shared Starlette pool

**Files:**
- Modify: `services/log_service.py`
- Modify: `api/ai.py`
- Modify: `api/image_tasks.py`
- Test: `test/test_concurrency_resilience.py`

- [ ] Change `LoggedCall.run` to execute handlers and stream `next()` calls through the dedicated executor.
- [ ] Return an async SSE iterator so `StreamingResponse` never advances upstream generators through AnyIO's default 40-token pool.
- [ ] Move content filtering and other long AI endpoint work to the dedicated executor.
- [ ] Add tests proving 100 blocked streaming calls do not delay a static file and that streams preserve their SSE payloads.

### Task 3: Bound background and nested image work

**Files:**
- Modify: `services/concurrency.py`
- Modify: `services/image_task_service.py`
- Modify: `services/editable_file_task_service.py`
- Modify: `services/protocol/conversation.py`
- Test: `test/test_concurrency_resilience.py`

- [ ] Add bounded executors with fixed worker and queue limits for image tasks, editable-file tasks, and multi-image subjobs.
- [ ] Replace every per-submission `threading.Thread` in those task services with bounded submission.
- [ ] Persist an explicit failed task result when a background queue is full and return HTTP 503 for a rejected submission.
- [ ] Replace per-request multi-image `ThreadPoolExecutor` construction with the shared bounded image executor.
- [ ] Test that 100 task submissions are accepted without creating 100 threads and that overflow is rejected without growing the queue.

### Task 4: Remove the cross-account refresh convoy and expose load state

**Files:**
- Modify: `services/account_service.py`
- Modify: `api/system.py`
- Modify: `services/config.py`
- Test: `test/test_concurrency_resilience.py`

- [ ] Replace `_token_refresh_lock` with a lock registry keyed by resolved account token and re-check token freshness after acquiring the per-account lock.
- [ ] Test that refreshes for two accounts execute concurrently while duplicate refreshes for one account remain single-flight.
- [ ] Include AI admission limit, active requests, rejected requests, and bounded executor queue state in `/health?format=json`.
- [ ] Run the focused account, image task, cache, API, and concurrency test modules.

### Task 5: Full verification and real UI test

**Files:**
- Modify: `README.md`
- Verify: backend and `web/`

- [ ] Document the 100-request limit, overload response, environment overrides, and the fact that limits are per process.
- [ ] Run the isolated unit-test module set; the repository's live `test_v1_*` scripts require a separately started service and real upstream accounts and are not part of unit discovery.
- [ ] Run `npm run build` and `npm run lint` in `web`; expect both commands to pass.
- [ ] Start the updated backend and frontend, load the login/settings/image pages in a browser, and confirm no console or network errors.
- [ ] Repeat the browser smoke test while 100 controlled AI requests hold the business executor; require page HTML/assets and `/version` to remain responsive.
