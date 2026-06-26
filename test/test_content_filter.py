import unittest
from unittest.mock import patch

from fastapi import HTTPException

from services import content_filter


class FakeConfig:
    sensitive_words: list[str] = []

    def __init__(self, ai_review: dict[str, object] | None = None, prompt_guard: dict[str, object] | None = None):
        self.ai_review = ai_review or {}
        self.prompt_guard = prompt_guard or {}


class FakeResponse:
    status_code = 200
    text = "{}"

    def __init__(self, data: dict[str, object]):
        self._data = data

    def json(self) -> dict[str, object]:
        return self._data


class ContentFilterTests(unittest.TestCase):
    def test_prompt_guard_disabled_skips_moderation_request(self) -> None:
        fake_config = FakeConfig(
            prompt_guard={
                "enabled": False,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(content_filter.requests, "post") as post:
            content_filter.check_request("hello")

        post.assert_not_called()

    def test_prompt_review_runs_before_prompt_guard(self) -> None:
        calls: list[str] = []

        def fake_post(url: str, **kwargs: object) -> FakeResponse:
            calls.append(url)
            if url.endswith("/v1/chat/completions"):
                return FakeResponse({"choices": [{"message": {"content": "ALLOW"}}]})
            return FakeResponse({"results": [{"flagged": False}]})

        fake_config = FakeConfig(
            ai_review={
                "enabled": True,
                "base_url": "https://review.example",
                "api_key": "review-key",
                "model": "review-model",
            },
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(content_filter.requests, "post", side_effect=fake_post):
            content_filter.check_request("hello")

        self.assertEqual(
            calls,
            [
                "https://review.example/v1/chat/completions",
                "https://guard.example/v1/moderations",
            ],
        )

    def test_ai_review_rejects_chinese_policy_denial_without_prompt_guard_call(self) -> None:
        calls: list[str] = []

        def fake_post(url: str, **_kwargs: object) -> FakeResponse:
            calls.append(url)
            return FakeResponse({"choices": [{"message": {"content": "本站不支持违规内容的生成。"}}]})

        fake_config = FakeConfig(
            ai_review={
                "enabled": True,
                "base_url": "https://review.example",
                "api_key": "review-key",
                "model": "review-model",
            },
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(content_filter.requests, "post", side_effect=fake_post):
            with self.assertRaises(HTTPException) as raised:
                content_filter.check_request("blocked prompt")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(calls, ["https://review.example/v1/chat/completions"])

    def test_prompt_guard_sends_each_image_with_text(self) -> None:
        sent_payloads: list[dict[str, object]] = []

        def fake_post(_url: str, **kwargs: object) -> FakeResponse:
            sent_payloads.append(kwargs["json"])  # type: ignore[index]
            return FakeResponse({"results": [{"flagged": False}, {"flagged": False}]})

        fake_config = FakeConfig(
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )
        images = [
            (b"png-one", "one.png", "image/png"),
            (b"jpeg-two", "two.jpg", "image/jpeg"),
        ]

        with patch.object(content_filter, "config", fake_config), patch.object(content_filter.requests, "post", side_effect=fake_post):
            content_filter.check_request("inspect these", images)

        moderation_input = sent_payloads[0]["input"]
        self.assertIsInstance(moderation_input, list)
        self.assertEqual(len(moderation_input), 2)
        for item in moderation_input:
            content = item["content"]  # type: ignore[index]
            self.assertEqual(content[0], {"type": "text", "text": "inspect these"})  # type: ignore[index]
            self.assertEqual(content[1]["type"], "image_url")  # type: ignore[index]
            self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/"))  # type: ignore[index]

    def test_prompt_guard_sends_image_without_text(self) -> None:
        sent_payloads: list[dict[str, object]] = []

        def fake_post(_url: str, **kwargs: object) -> FakeResponse:
            sent_payloads.append(kwargs["json"])  # type: ignore[index]
            return FakeResponse({"results": [{"flagged": False}]})

        fake_config = FakeConfig(
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(content_filter.requests, "post", side_effect=fake_post):
            content_filter.check_request("", [(b"png-one", "one.png", "image/png")])

        moderation_input = sent_payloads[0]["input"]
        self.assertIsInstance(moderation_input, list)
        self.assertEqual(len(moderation_input), 1)
        content = moderation_input[0]["content"]  # type: ignore[index]
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["type"], "image_url")  # type: ignore[index]
        self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/png;base64,"))  # type: ignore[index]

    def test_prompt_guard_extracts_multimodal_message_images(self) -> None:
        sent_payloads: list[dict[str, object]] = []

        def fake_post(_url: str, **kwargs: object) -> FakeResponse:
            sent_payloads.append(kwargs["json"])  # type: ignore[index]
            return FakeResponse({"results": [{"flagged": False}, {"flagged": False}]})

        fake_config = FakeConfig(
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "inspect these"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,ZmFrZS0x"}},
                    {"type": "input_image", "image_url": "https://example.com/fake-2.png"},
                ],
            },
        ]

        with patch.object(content_filter, "config", fake_config), patch.object(content_filter.requests, "post", side_effect=fake_post):
            content_filter.check_request("inspect these", messages)

        moderation_input = sent_payloads[0]["input"]
        self.assertIsInstance(moderation_input, list)
        self.assertEqual(len(moderation_input), 2)
        urls = [item["content"][1]["image_url"]["url"] for item in moderation_input]  # type: ignore[index]
        self.assertEqual(urls, ["data:image/png;base64,ZmFrZS0x", "https://example.com/fake-2.png"])

    def test_prompt_guard_rejects_when_any_image_input_is_flagged(self) -> None:
        fake_config = FakeConfig(
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(
            content_filter.requests,
            "post",
            return_value=FakeResponse({"results": [{"flagged": False}, {"flagged": True}]}),
        ):
            with self.assertRaises(HTTPException) as raised:
                content_filter.check_request("inspect these", [(b"one", "one.png", "image/png"), (b"two", "two.png", "image/png")])

        self.assertEqual(raised.exception.status_code, 400)

    def test_prompt_guard_rejects_flagged_result(self) -> None:
        fake_config = FakeConfig(
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(
            content_filter.requests,
            "post",
            return_value=FakeResponse({"results": [{"flagged": True}]}),
        ):
            with self.assertRaises(HTTPException) as raised:
                content_filter.check_request("blocked prompt")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, {"error": "护栏审核未通过，拒绝本次任务"})

    def test_prompt_guard_fail_open_allows_upstream_failure_by_default(self) -> None:
        fake_config = FakeConfig(
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(
            content_filter.requests,
            "post",
            side_effect=RuntimeError("network down"),
        ):
            content_filter.check_request("allowed when guard is down")

    def test_prompt_guard_fail_closed_rejects_upstream_failure(self) -> None:
        fake_config = FakeConfig(
            prompt_guard={
                "enabled": True,
                "base_url": "https://guard.example",
                "auth_token": "guard-token",
                "fail_open": False,
            },
        )

        with patch.object(content_filter, "config", fake_config), patch.object(
            content_filter.requests,
            "post",
            side_effect=RuntimeError("network down"),
        ):
            with self.assertRaises(HTTPException) as raised:
                content_filter.check_request("strict guard")

        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
