import base64
import unittest
from types import SimpleNamespace
from unittest import mock

from services.protocol import conversation


PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


class ImageResponseUrlTests(unittest.TestCase):
    def _format(self, *, include_url: bool, base_url: str | None, response_format: str = "b64_json"):
        fake_config = SimpleNamespace(
            image_response_include_url=include_url,
            base_url="",
        )
        fake_storage = SimpleNamespace(
            save=mock.Mock(return_value=SimpleNamespace(url=f"{base_url or 'http://internal.test'}/images/fake.png"))
        )
        with mock.patch.object(conversation, "config", fake_config), mock.patch.object(
            conversation,
            "image_storage_service",
            fake_storage,
        ):
            return conversation.format_image_result(
                [{"b64_json": PNG_B64}],
                "draw",
                response_format,
                base_url,
                created=1,
            )

    def test_omits_url_when_response_url_disabled(self):
        result = self._format(include_url=False, base_url="https://public.example")

        self.assertEqual(result["data"][0]["b64_json"], PNG_B64)
        self.assertNotIn("url", result["data"][0])

    def test_returns_url_when_enabled_without_base_url(self):
        result = self._format(include_url=True, base_url=None)

        self.assertEqual(result["data"][0]["b64_json"], PNG_B64)
        self.assertEqual(result["data"][0]["url"], "http://internal.test/images/fake.png")

    def test_returns_url_when_enabled_with_base_url(self):
        result = self._format(include_url=True, base_url="https://public.example")

        self.assertEqual(result["data"][0]["url"], "https://public.example/images/fake.png")

    def test_url_response_format_still_omits_url_when_disabled(self):
        result = self._format(include_url=False, base_url="https://public.example", response_format="url")

        self.assertEqual(result["data"], [{"revised_prompt": "draw"}])


if __name__ == "__main__":
    unittest.main()
