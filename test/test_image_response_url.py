import asyncio
import unittest
from unittest import mock

from services.log_service import LoggedCall


PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


class ImageResponseUrlTests(unittest.TestCase):
    def _run_logged_call(self, *, include_url: bool):
        call = LoggedCall(
            {"id": "key-id", "name": "test", "role": "user"},
            "/v1/images/generations",
            "gpt-image-2",
            "image",
            request_text="draw",
        )

        def handler():
            return {
                "created": 1,
                "data": [{
                    "b64_json": PNG_B64,
                    "url": "https://public.example/images/fake.png",
                    "revised_prompt": "draw",
                }],
            }

        with mock.patch("services.log_service.config") as fake_config, mock.patch(
            "services.log_service.log_service.add"
        ) as add:
            fake_config.image_response_include_url = include_url
            response = asyncio.run(call.run(handler))
            logged_detail = add.call_args.args[2]
        return response, logged_detail

    def test_final_image_response_omits_url_when_disabled(self):
        response, logged_detail = self._run_logged_call(include_url=False)

        self.assertEqual(response["data"][0]["b64_json"], PNG_B64)
        self.assertNotIn("url", response["data"][0])
        self.assertEqual(logged_detail["urls"], ["https://public.example/images/fake.png"])

    def test_final_image_response_keeps_url_when_enabled(self):
        response, logged_detail = self._run_logged_call(include_url=True)

        self.assertEqual(response["data"][0]["url"], "https://public.example/images/fake.png")
        self.assertEqual(logged_detail["urls"], ["https://public.example/images/fake.png"])


if __name__ == "__main__":
    unittest.main()
