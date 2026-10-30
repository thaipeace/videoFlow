"""Phase 2 (YouTube compliance plan): tiny VCH logo + faint random-slot watermark overlay."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from haizflow.pipeline.branding import (
    WATERMARK_SLOTS,
    BrandingOverlayPool,
    build_branding_overlay,
)
from haizflow.schemas.article_video import ArticleProjectConfig


class BrandingOverlayTests(unittest.TestCase):
    def test_overlay_matches_frame_and_is_mostly_transparent(self):
        for w, h in ((1920, 1080), (1080, 1920)):
            with tempfile.TemporaryDirectory() as tmp:
                path = build_branding_overlay(w, h, Path(tmp) / "o.png")
                img = Image.open(path)
                self.assertEqual(img.size, (w, h))
                self.assertEqual(img.mode, "RGBA")
                alpha = img.getchannel("A")
                opaque = (w * h) - alpha.histogram()[0]
                self.assertLess(opaque / (w * h), 0.01)  # logo + watermark cover < 1% of the frame
                self.assertEqual(alpha.getpixel((w // 2, h // 2)), 0)  # centre stays clean

    def test_logo_is_small_and_top_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = Image.open(build_branding_overlay(1920, 1080, Path(tmp) / "o.png"))
            box = img.getchannel("A").crop((0, 0, 400, 200)).getbbox()
            self.assertIsNotNone(box)
            self.assertLess(box[2] - box[0], 90)  # tiny badge width
            self.assertLess(box[3] - box[1], 40)  # tiny badge height

    def test_watermark_alpha_is_faint(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = Image.open(build_branding_overlay(1920, 1080, Path(tmp) / "o.png", "right"))
            lower = img.getchannel("A").crop((0, 700, 1920, 1080))
            self.assertLessEqual(lower.getextrema()[1], 60)

    def test_pool_never_repeats_slot_consecutively(self):
        with tempfile.TemporaryDirectory() as tmp:
            pool = BrandingOverlayPool(1920, 1080, Path(tmp), seed="x")
            names = [pool.next_overlay().name for _ in range(12)]
            self.assertTrue(all(a != b for a, b in zip(names, names[1:])))
            self.assertTrue(set(names) <= {f"branding_{s}.png" for s in WATERMARK_SLOTS})

    def test_chapter_label_renders_pill_next_to_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            pool = BrandingOverlayPool(1920, 1080, Path(tmp), seed="x")
            path = pool.next_overlay(chapter_label="THỜI SỰ THẾ GIỚI")
            self.assertTrue(path.name.startswith("branding_"))
            img = Image.open(path)
            box = img.getchannel("A").crop((0, 0, 500, 200)).getbbox()
            self.assertIsNotNone(box)
            self.assertGreater(box[2] - box[0], 90)  # wider than logo alone due to chapter pill


class BrandingConfigTests(unittest.TestCase):
    def test_branding_is_opt_in(self):
        self.assertFalse(ArticleProjectConfig().branding_enabled)


if __name__ == "__main__":
    unittest.main()
