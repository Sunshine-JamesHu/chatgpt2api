import unittest
import asyncio
from unittest import mock

from services.log_service import LoggedCall, _response_hidden_keys, _strip_internal_response_fields


class LogImageRetryInfoTests(unittest.TestCase):
    def test_logged_call_run_strips_urls_from_image_response(self):
        call = LoggedCall(
            {"id": "key-id", "name": "test", "role": "user"},
            "/v1/images/generations",
            "gpt-image-2",
            "文生图",
            request_text="draw",
        )

        def handler():
            return {
                "created": 1,
                "data": [{"url": "https://example.test/image.png"}],
                "urls": ["https://example.test/image.png"],
            }

        with mock.patch("services.log_service.log_service.add") as add:
            response = asyncio.run(call.run(handler))

        self.assertEqual(response["data"], [{"url": "https://example.test/image.png"}])
        self.assertNotIn("urls", response)
        self.assertEqual(add.call_args.args[2]["urls"], ["https://example.test/image.png"])

    def test_logged_call_records_image_retry_info(self):
        captured = {}
        call = LoggedCall(
            {"id": "key-id", "name": "test", "role": "user"},
            "/v1/images/generations",
            "gpt-image-2",
            "文生图",
            request_text="draw",
        )
        result = {
            "created": 1,
            "data": [{"url": "https://example.test/image.png"}],
            "_image_retry_count": 2,
            "_image_attempted_accounts": 3,
            "_image_retry_reasons": ["text_reply", "upstream_http"],
        }

        with mock.patch("services.log_service.log_service.add") as add:
            call.log("调用完成", result)
            captured.update(add.call_args.args[2])

        self.assertEqual(captured["image_retry_count"], 2)
        self.assertEqual(captured["image_attempted_accounts"], 3)
        self.assertEqual(captured["image_retry_reasons"], ["text_reply", "upstream_http"])

    def test_internal_retry_fields_are_stripped_from_response(self):
        response = _strip_internal_response_fields({
            "data": [{"url": "https://example.test/image.png"}],
            "_image_retry_count": 1,
            "_image_attempted_accounts": 2,
            "_image_retry_reasons": ["text_reply"],
        })

        self.assertEqual(response, {"data": [{"url": "https://example.test/image.png"}]})

    def test_image_response_strips_top_level_urls_but_keeps_data_url(self):
        response = _strip_internal_response_fields(
            {
                "created": 1,
                "data": [{"url": "https://example.test/image.png"}],
                "urls": ["https://example.test/image.png"],
            },
            _response_hidden_keys("/v1/images/generations"),
        )

        self.assertEqual(response, {"created": 1, "data": [{"url": "https://example.test/image.png"}]})


if __name__ == "__main__":
    unittest.main()
