import unittest
from unittest import mock

from services.log_service import LoggedCall, _strip_internal_response_fields


class LogImageRetryInfoTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
