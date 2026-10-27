"""Phase 3 (YouTube compliance plan): scrolling news ticker replacing subtitles."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from haizflow.pipeline.slide_composer import _build_overlay_graph
from haizflow.pipeline.ticker import MAX_LOOP_PX, build_ticker, split_ticker_items
from haizflow.schemas.article_video import ArticleProjectConfig

SAMPLE = "Tin một về Ukraine | Tin hai về giá dầu tăng mạnh | Tin ba về bóng đá châu Âu"


class TickerBuildTests(unittest.TestCase):
    def test_empty_text_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(build_ticker(1920, 1080, "  |  ", Path(tmp)))

    def test_split_items(self):
        self.assertEqual(split_ticker_items("A | B |  | C."), ["A", "B", "C"])

    def test_landscape_bar_is_flush_bottom_and_strip_covers_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = build_ticker(1920, 1080, SAMPLE, Path(tmp))
            self.assertEqual(t.bar_y + t.bar_h, 1080)
            with Image.open(t.strip_path) as strip:
                self.assertEqual(strip.height, t.bar_h)
                # strip must cover the visible area for the whole loop (seamless wrap-around)
                self.assertGreaterEqual(strip.width, (1920 - t.strip_x) + t.loop_px)
            with Image.open(t.badge_path) as badge:
                self.assertEqual(badge.height, t.bar_h)

    def test_portrait_bar_is_lifted_above_shorts_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = build_ticker(1080, 1920, SAMPLE, Path(tmp), label="TIN NÓNG")
            self.assertLess(t.bar_y + t.bar_h, 1920 * 0.86)

    def test_very_long_text_is_capped(self):
        long_text = " | ".join(f"Tiêu đề số {i} khá dài để thử giới hạn độ dài dải chữ chạy" for i in range(200))
        with tempfile.TemporaryDirectory() as tmp:
            t = build_ticker(1920, 1080, long_text, Path(tmp))
            self.assertLessEqual(t.loop_px, MAX_LOOP_PX)

    def test_offset_keeps_scroll_continuous(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = build_ticker(1920, 1080, SAMPLE, Path(tmp))
            self.assertIn("(t+0.000)", t.scroll_overlay())
            self.assertIn("(t+12.500)", t.with_offset(12.5).scroll_overlay())


class OverlayGraphTests(unittest.TestCase):
    def test_no_overlays_uses_plain_vf(self):
        inputs, args = _build_overlay_graph("scale=1:1", None, None)
        self.assertEqual((inputs, args), ([], ["-vf", "scale=1:1"]))

    def test_ticker_and_branding_stream_indices_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = build_ticker(1920, 1080, SAMPLE, Path(tmp))
            brand = Path(tmp) / "brand.png"
            brand.write_bytes(b"x")
            inputs, args = _build_overlay_graph("scale=1:1", brand, t)
            self.assertEqual(inputs.count("-i"), 3)  # strip, badge, branding
            graph = args[args.index("-filter_complex") + 1]
            self.assertIn("[s1][1:v]overlay=x='", graph)  # scrolling strip is input 1
            self.assertIn("[2:v]overlay=x=0:y=", graph)  # badge is input 2
            self.assertIn("[3:v]overlay=0:0", graph)  # branding is input 3 (top-most)
            self.assertTrue(graph.endswith(",format=yuv420p[v]"))
            self.assertEqual(args[-2:], ["-map", "[v]"])

    def test_branding_only_matches_phase2_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            brand = Path(tmp) / "brand.png"
            brand.write_bytes(b"x")
            inputs, args = _build_overlay_graph("scale=1:1", brand, None)
            graph = args[args.index("-filter_complex") + 1]
            self.assertEqual(graph, "[0:v]scale=1:1[s0];[s0][1:v]overlay=0:0:format=auto,format=yuv420p[v]")


class TickerConfigTests(unittest.TestCase):
    def test_ticker_is_opt_in(self):
        cfg = ArticleProjectConfig()
        self.assertEqual(cfg.ticker_text, "")
        self.assertEqual(cfg.ticker_label, "TIN MỚI")


if __name__ == "__main__":
    unittest.main()
