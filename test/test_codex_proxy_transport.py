from __future__ import annotations

import json
import unittest
from unittest import mock

from services.openai_backend_api import OpenAIBackendAPI


class FakeResponse:
    status_code = 200
    headers = {"content-type": "text/event-stream"}
    text = ""

    def __init__(self, events: list[dict]):
        lines = [f"data: {json.dumps(event)}\n" for event in events]
        self.content = ("\n".join(lines) + "\n").encode("utf-8")

    def json(self):
        return json.loads(self.content.decode("utf-8"))


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


class CodexProxyTransportTests(unittest.TestCase):
    def test_codex_responses_uses_configured_session_transport(self):
        response = FakeResponse([
            {"type": "image_generation_call", "result": "ZmFrZQ=="},
        ])
        session = FakeSession(response)
        backend = object.__new__(OpenAIBackendAPI)
        backend.access_token = "token"
        backend.base_url = "https://chatgpt.com"
        backend.session = session

        with (
            mock.patch.object(backend, "_ensure_codex_source_account"),
            mock.patch("services.openai_backend_api.account_service.get_account", return_value={"source_type": "codex"}),
            mock.patch("services.openai_backend_api.account_service._decode_jwt_payload", return_value={}),
        ):
            events = list(backend.iter_codex_image_response_events("draw a square"))

        self.assertEqual(events, [{"type": "image_generation_call", "result": "ZmFrZQ=="}])
        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["url"], "https://chatgpt.com/backend-api/codex/responses")
        self.assertEqual(call["timeout"], 1200)
        self.assertEqual(call["headers"]["Authorization"], "Bearer token")
        self.assertEqual(call["json"]["stream"], True)


if __name__ == "__main__":
    unittest.main()
