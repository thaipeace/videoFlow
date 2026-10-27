"""Unit and integration tests for ImageGenerator service."""

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from haizflow.schemas.article_video import ArticleProjectConfig, ArticleScene
from haizflow.services import image_generator
from haizflow.services.image_generator import ImageGenerationError


class TestImageGenerator(unittest.TestCase):
    def test_compute_image_cache_key_determinism(self):
        k1 = image_generator.compute_image_cache_key("anime boy reading book", "16:9", "anime_2d")
        k2 = image_generator.compute_image_cache_key("anime boy reading book", "16:9", "anime_2d")
        self.assertEqual(k1, k2)

        # Different prompt gives different key
        k3 = image_generator.compute_image_cache_key("anime girl reading book", "16:9", "anime_2d")
        self.assertNotEqual(k1, k3)

        # Different aspect ratio gives different key
        k4 = image_generator.compute_image_cache_key("anime boy reading book", "9:16", "anime_2d")
        self.assertNotEqual(k1, k4)

    def test_cache_save_and_retrieve(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_cache = Path(temp_dir)
            key = "test_key_12345"
            fake_bytes = b"fake-jpeg-image-bytes-with-sufficient-length-greater-than-512-" * 20

            # Initially not cached
            self.assertIsNone(image_generator.get_cached_image(key, temp_cache))

            # Save
            saved_path = image_generator.save_image_to_cache(key, fake_bytes, ".jpg", temp_cache)
            self.assertTrue(saved_path.is_file())

            # Retrieve
            retrieved = image_generator.get_cached_image(key, temp_cache)
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved, saved_path)
            self.assertEqual(retrieved.read_bytes(), fake_bytes)

    def test_call_imagen_api_missing_key(self):
        with self.assertRaises(ImageGenerationError) as ctx:
            image_generator.call_imagen_api("test prompt", api_key="")
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("haizflow.services.image_generator.urlopen")
    def test_call_imagen_api_success(self, mock_urlopen):
        raw_image_data = b"REAL_IMAGE_DATA_BYTES_123"
        b64_str = base64.b64encode(raw_image_data).decode("ascii")
        mock_response = MagicMock()
        mock_payload = {
            "predictions": [
                {"bytesBase64Encoded": b64_str, "mimeType": "image/jpeg"}
            ]
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        data = image_generator.call_imagen_api("a majestic sunset", api_key="valid-test-key")
        self.assertEqual(data, raw_image_data)

    def test_create_fallback_placeholder_image(self):
        jpeg_bytes = image_generator.create_fallback_placeholder_image(
            prompt="Mỹ Dung đứng trước hành lang", width=640, height=360, style="cinematic"
        )
        self.assertGreater(len(jpeg_bytes), 1000)

        # Verify it is valid decodable image
        from io import BytesIO
        with Image.open(BytesIO(jpeg_bytes)) as img:
            self.assertEqual(img.size, (640, 360))
            self.assertEqual(img.format, "JPEG")

    def test_create_fallback_placeholder_with_character_sheet(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sheet = Path(tmp_dir) / "test_sheet.jpg"
            img = Image.new("RGB", (800, 400), color=(180, 50, 50))
            img.save(sheet)

            jpeg_bytes = image_generator.create_fallback_placeholder_image(
                prompt="Mỹ Dung trong sương mù",
                width=640,
                height=360,
                style="cinematic",
                character_image_path=sheet,
            )
            self.assertGreater(len(jpeg_bytes), 1000)
            from io import BytesIO
            with Image.open(BytesIO(jpeg_bytes)) as out_img:
                self.assertEqual(out_img.size, (640, 360))
                self.assertEqual(out_img.format, "JPEG")

    def test_import_custom_scene_image_cropping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_img_path = temp_path / "custom.png"

            # Create an arbitrary 1000x1000 square image
            square_img = Image.new("RGB", (1000, 1000), color=(255, 0, 0))
            square_img.save(source_img_path)

            dest_path = temp_path / "fitted_16_9.jpg"
            image_generator.import_custom_scene_image(
                source_path=source_img_path,
                destination_path=dest_path,
                aspect_ratio="16:9",
            )
            self.assertTrue(dest_path.is_file())

            # Check that output is fitted to 1920x1080
            with Image.open(dest_path) as out:
                self.assertEqual(out.size, (1920, 1080))

    def test_generate_scenes_images_pipeline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            scenes = [
                ArticleScene(
                    scene_index=0,
                    text="Mở đầu câu chuyện.",
                    has_image=True,
                    image_prompt="anime landscape, peaceful village",
                ),
                ArticleScene(
                    scene_index=1,
                    text="Đoạn văn tiếp nối.",
                    has_image=False,
                ),
                ArticleScene(
                    scene_index=2,
                    text="Cao trào gặp gỡ.",
                    has_image=True,
                    image_prompt="dramatic stormy night, ancient tower",
                ),
            ]
            config = ArticleProjectConfig(
                article_text="...",
                aspect_ratio="16:9",
                image_style="anime_2d",
            )

            # Generate (will use placeholder fallback since no real API key is passed)
            updated_scenes = image_generator.generate_scenes_images(
                scenes=scenes,
                config=config,
                output_dir=temp_path,
            )

            # Only scenes 0 and 2 should have image_path populated
            self.assertTrue(Path(updated_scenes[0].image_path).is_file())
            self.assertFalse(bool(updated_scenes[1].image_path))
            self.assertTrue(Path(updated_scenes[2].image_path).is_file())

    def test_get_effective_gemini_api_key_filters_mock(self):
        # Explicit mock string must be rejected
        self.assertEqual(image_generator.get_effective_gemini_api_key("example-gemini-key"), "")
        # Empty string must return empty or fall back
        self.assertEqual(image_generator.get_effective_gemini_api_key(""), "")
        # Real string should be accepted
        self.assertEqual(image_generator.get_effective_gemini_api_key("AIzaSyTestValidKey123"), "AIzaSyTestValidKey123")

    @patch("haizflow.services.image_generator.call_free_ai_api")
    def test_generate_scene_image_cascade_free_ai(self, mock_free):
        mock_free.return_value = b"MOCK_FREE_AI_IMAGE_BYTES"
        with tempfile.TemporaryDirectory() as temp_dir:
            dest = Path(temp_dir) / "test_cascade.jpg"
            image_generator.generate_scene_image(
                prompt="A scenic lake at sunset",
                destination_path=dest,
                api_key="",
                use_cache=False,
                allow_free_online=True,
            )
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_bytes(), b"MOCK_FREE_AI_IMAGE_BYTES")
            mock_free.assert_called_once()


if __name__ == "__main__":
    unittest.main()
