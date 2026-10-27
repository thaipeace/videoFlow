import unittest
from pathlib import Path

from haizflow.pipeline.subscribe_cta import (
    render_cta_frame,
    synthesize_cta_sfx,
    mix_cta_sfx_into_audio,
)
from haizflow.pipeline.slide_composer import (
    WAR_VOICE_MASTER_CHAIN,
    VOICE_MASTER_CHAIN,
    _build_overlay_graph,
    get_video_duration,
)
from haizflow.services.daily_news import (
    normalize_category,
    get_category_config,
    get_lead_ins_for_category,
    get_mock_news_items,
    WAR_LEAD_INS,
    DEFAULT_THUMBNAIL_HOOKS,
)


class WarNewsAndCtaFixTests(unittest.TestCase):
    def test_war_category_normalization(self):
        for term in ("war", "chiensu", "conflict", "chientranh", "chien_su", "war_news"):
            self.assertEqual(normalize_category(term), "war")

    def test_war_category_config(self):
        cfg = get_category_config("war")
        self.assertEqual(cfg["label"], "Chiến sự")
        self.assertEqual(cfg["file_prefix"], "war_news")
        self.assertTrue(len(cfg["feeds"]) >= 5)
        self.assertIn("chiensuthegioi", cfg["hashtags"])
        self.assertEqual(DEFAULT_THUMBNAIL_HOOKS["war"], "CHIẾN SỰ: BƯỚC NGOẶT MỚI")

    def test_war_lead_ins(self):
        lead_ins = get_lead_ins_for_category("war")
        self.assertEqual(lead_ins, WAR_LEAD_INS)
        self.assertTrue(len(lead_ins) >= 5)

    def test_war_mock_news_items(self):
        items = get_mock_news_items("war")
        self.assertEqual(len(items), 8)
        for item in items:
            self.assertTrue(item.title)
            self.assertTrue(item.summary)
            self.assertTrue(item.source)

    def test_war_voice_master_chain(self):
        self.assertIn("highpass", WAR_VOICE_MASTER_CHAIN)
        self.assertIn("equalizer", WAR_VOICE_MASTER_CHAIN)
        self.assertIn("acompressor", WAR_VOICE_MASTER_CHAIN)
        self.assertIn("loudnorm", WAR_VOICE_MASTER_CHAIN)

    def test_cta_frame_transparent_tail(self):
        # The last frames must be 100% transparent to prevent any leftover bell icons on screen
        frame_end = render_cta_frame(3.78, total_dur=3.8, width=1920, height=1080)
        extrema = frame_end.getextrema()
        alpha_min, alpha_max = extrema[3]
        self.assertEqual(alpha_max, 0, "Last frame of CTA animation must be fully transparent")

    def test_build_overlay_graph_cta_eof_pass(self):
        dummy_cta = Path("dummy_cta.mov")
        # Ensure dummy path doesn't error when not present, test with dummy file
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cta_f = Path(tmp) / "cta.mov"
            cta_f.write_bytes(b"\x00" * 100)
            extra_inputs, filter_args = _build_overlay_graph(
                filter_chain="scale=1920:1080",
                overlay_path=None,
                ticker=None,
                cta_video_path=cta_f,
                cta_start_sec=2.0,
            )
            filter_str = " ".join(filter_args)
            self.assertIn("overlay=0:0", filter_str)
            self.assertIn("gte(t,2.00)", filter_str)


if __name__ == "__main__":
    unittest.main()
