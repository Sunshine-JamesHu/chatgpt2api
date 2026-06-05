from __future__ import annotations

import unittest
from unittest import mock

from services.openai_backend_api import ImageContentPolicyError
from services.protocol import conversation
from services.protocol.conversation import ConversationRequest, ImageGenerationError, ImageOutput
from utils.helper import UpstreamHTTPError


class FakeAccountService:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.requested_exclusions: list[set[str]] = []
        self.results: list[tuple[str, bool]] = []

    def get_available_access_token(self, **kwargs):
        excluded = set(kwargs.get("excluded_tokens") or set())
        self.requested_exclusions.append(excluded)
        for token in self.tokens:
            if token not in excluded:
                return token
        raise RuntimeError("no available image quota")

    def get_account(self, token: str):
        return {"access_token": token, "email": f"{token}@example.test", "status": "正常", "quota": 3}

    def mark_image_result(self, token: str, success: bool):
        self.results.append((token, success))
        return self.get_account(token)

    def refresh_access_token(self, token: str, force: bool = False, event: str = ""):
        return token

    def remove_invalid_token(self, token: str, event: str):
        return None


class ImageAccountRetryTests(unittest.TestCase):
    def run_with(self, service: FakeAccountService, side_effects, max_retries: int = 3):
        request = ConversationRequest(model="gpt-image-2", prompt="draw", response_format="b64_json")
        original_retries = conversation.config.data.get("image_max_account_retries")

        def fake_stream(_backend, _request, index=1, total=1):
            effect = side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            yield ImageOutput(kind="result", model="gpt-image-2", index=index, total=total, data=[{"b64_json": "ZmFrZQ=="}])

        try:
            conversation.config.data["image_max_account_retries"] = max_retries
            with (
                mock.patch.object(conversation, "account_service", service),
                mock.patch.object(conversation, "stream_image_outputs", fake_stream),
                mock.patch.object(conversation, "OpenAIBackendAPI", lambda access_token="": object()),
            ):
                return list(conversation._generate_single_image(request, 1, 1))
        finally:
            if original_retries is None:
                conversation.config.data.pop("image_max_account_retries", None)
            else:
                conversation.config.data["image_max_account_retries"] = original_retries

    def test_recoverable_failure_switches_account_and_succeeds(self):
        service = FakeAccountService(["token-one", "token-two"])
        outputs = self.run_with(
            service,
            [ImageGenerationError("No image result found in response"), "ok"],
            max_retries=1,
        )

        self.assertEqual(outputs[0].kind, "result")
        self.assertEqual(service.results, [("token-one", False), ("token-two", True)])
        self.assertEqual(service.requested_exclusions[1], {"token-one"})

    def test_zero_retries_returns_first_recoverable_error(self):
        service = FakeAccountService(["token-one", "token-two"])

        with self.assertRaises(ImageGenerationError):
            self.run_with(service, [ImageGenerationError("No image result found in response")], max_retries=0)

        self.assertEqual(service.results, [("token-one", False)])
        self.assertEqual(len(service.requested_exclusions), 1)

    def test_content_policy_does_not_switch_account(self):
        service = FakeAccountService(["token-one", "token-two"])

        with self.assertRaises(ImageGenerationError) as ctx:
            self.run_with(service, [ImageContentPolicyError("blocked")], max_retries=3)

        self.assertEqual(ctx.exception.code, "content_policy_violation")
        self.assertEqual(service.results, [("token-one", False)])
        self.assertEqual(len(service.requested_exclusions), 1)

    def test_recoverable_upstream_5xx_switches_account(self):
        service = FakeAccountService(["token-one", "token-two"])
        outputs = self.run_with(
            service,
            [UpstreamHTTPError("/backend-api/test", 503, {"error": "busy"}), "ok"],
            max_retries=1,
        )

        self.assertEqual(outputs[0].kind, "result")
        self.assertEqual(service.results, [("token-one", False), ("token-two", True)])

    def test_unrecoverable_upstream_400_does_not_switch_account(self):
        service = FakeAccountService(["token-one", "token-two"])

        with self.assertRaises(ImageGenerationError):
            self.run_with(service, [UpstreamHTTPError("/backend-api/test", 400, {"error": "bad"})], max_retries=3)

        self.assertEqual(service.results, [("token-one", False)])
        self.assertEqual(len(service.requested_exclusions), 1)


if __name__ == "__main__":
    unittest.main()
