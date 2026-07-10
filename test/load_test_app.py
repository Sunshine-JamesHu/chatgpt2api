from __future__ import annotations

import os
import time

from fastapi.routing import APIRoute

from api import create_app
from services.log_service import LoggedCall


HOLD_SECONDS = max(1.0, float(os.getenv("CHATGPT2API_LOAD_TEST_HOLD_SECONDS", "30")))


def _blocked_stream():
    time.sleep(HOLD_SECONDS)
    yield {"held_seconds": HOLD_SECONDS}


async def hold_ai_request():
    call = LoggedCall(
        {"id": "load-test", "name": "load-test", "role": "user"},
        "/v1/load-test/hold",
        "load-test",
        "controlled load test",
    )
    return await call.run(_blocked_stream)


app = create_app()
# The production app ends with a catch-all web route, so the test-only route
# must be inserted before it. Docker images do not copy the test directory.
app.router.routes.insert(
    0,
    APIRoute("/v1/load-test/hold", hold_ai_request, methods=["GET"]),
)
