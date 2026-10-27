import tempfile
import unittest
from pathlib import Path
from PIL import Image

from haizflow.pipeline.subscribe_cta import (
    render_cta_frame,
    synthesize_cta_sfx,
    get_or_build_subscribe_cta,
    mix_cta_sfx_into_audio,
)
from haizflow.pipeline.slide_composer import _build_overlay_graph, get_video_duration


class SubscribeCtaTests(unittest.TestCase):
    def test_render_cta_frame_16x9(self):
        frame = render_cta_frame(1.0, total_dur=3.8, width=1920, height=1080)
        self.assertEqual(frame.size, (1920, 1080))
        self.assertEqual(frame.mode, "RGBA")

    def test_render_cta_frame_9x16(self):
        frame = render_cta_frame(1.8, total_dur=3.8, width=1080, height=1920)
        self.assertEqual(frame.size, (1080, 1920))
        self.assertEqual(frame.mode, "RGBA")

    def test_synthesize_sfx(self):
        with tempfile.TemporaryDirectory() as tmp:
            sfx_path = Path(tmp) / "sfx.wav"
            synthesize_cta_sfx(sfx_path, duration=3.8)
            self.assertTrue(sfx_path.is_file())
            dur = get_video_duration(str(sfx_path))
            self.assertAlmostEqual(dur, 3.8, delta=0.2)

    def test_build_overlay_graph_with_cta(self):
        with tempfile.TemporaryDirectory() as tmp:
            cta_dummy = Path(tmp) / "cta.mov"
            cta_dummy.write_bytes(b"\x00" * 100)
            extra_inputs, filter_args = _build_overlay_graph(
                filter_chain="scale=1920:1080",
                overlay_path=None,
                ticker=None,
                cta_video_path=cta_dummy,
                cta_start_sec=1.5,
            )
            self.assertIn("-filter_complex", filter_args)
            self.assertTrue(any("overlay=" in arg for arg in filter_args))
            self.assertTrue(any("setpts=" in arg for arg in filter_args))
            self.assertTrue(any(str(cta_dummy.resolve()) in inp for inp in extra_inputs))


if __name__ == "__main__":
    unittest.main()
