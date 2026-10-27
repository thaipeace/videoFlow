"""Unit and integration tests for SlideComposer pipeline."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from haizflow.pipeline import slide_composer
from haizflow.schemas.article_video import (
    ArticleProjectConfig,
    ArticleScene,
    ArticleVideoProject,
)


class TestSlideComposer(unittest.TestCase):
    def test_resolution_for_aspect_ratio(self):
        self.assertEqual(slide_composer.resolution_for_aspect_ratio("16:9"), (1920, 1080))
        self.assertEqual(slide_composer.resolution_for_aspect_ratio("9:16"), (1080, 1920))
        self.assertEqual(slide_composer.resolution_for_aspect_ratio("1:1"), (1080, 1080))

    def test_build_ken_burns_filter_expressions(self):
        f_in = slide_composer.build_ken_burns_filter(5.0, "zoom_in", 1920, 1080, 30)
        self.assertIn("zoompan=", f_in)
        self.assertIn("min(zoom+", f_in)
        self.assertIn("d=150", f_in)  # 5s * 30fps
        self.assertIn("s=1920x1080", f_in)

        f_out = slide_composer.build_ken_burns_filter(4.0, "zoom_out", 1920, 1080, 30)
        self.assertIn("zoompan=", f_out)
        self.assertIn("d=120", f_out)

        f_pan_lr = slide_composer.build_ken_burns_filter(3.0, "pan_left_to_right", 1920, 1080, 30)
        self.assertIn("zoompan=", f_pan_lr)
        self.assertIn("1.12", f_pan_lr)

        f_static = slide_composer.build_ken_burns_filter(2.0, "static", 1920, 1080, 30)
        self.assertNotIn("zoompan", f_static)
        self.assertIn("scale=1920:1080", f_static)

    def test_calculate_slide_specs_grouping(self):
        scenes = [
            ArticleScene(
                scene_index=0,
                text="Scene 0",
                duration_ms=4000,
                has_image=True,
                image_path="img_a.png",
            ),
            ArticleScene(
                scene_index=1,
                text="Scene 1",
                duration_ms=3000,
                has_image=False,
                image_path="",
            ),
            ArticleScene(
                scene_index=2,
                text="Scene 2",
                duration_ms=5000,
                has_image=True,
                image_path="img_b.png",
            ),
        ]
        specs = slide_composer.calculate_slide_specs(scenes)
        self.assertEqual(len(specs), 2)

        # First slide groups scenes 0 and 1 (4s + 3s = 7s)
        self.assertEqual(specs[0].image_path, "img_a.png")
        self.assertAlmostEqual(specs[0].duration_seconds, 7.0)
        self.assertEqual(specs[0].scene_indices, [0, 1])
        self.assertEqual(specs[0].effect, "zoom_in")

        # Second slide covers scene 2 (5s)
        self.assertEqual(specs[1].image_path, "img_b.png")
        self.assertAlmostEqual(specs[1].duration_seconds, 5.0)
        self.assertEqual(specs[1].scene_indices, [2])
        self.assertEqual(specs[1].effect, "pan_left_to_right")

    def test_export_subtitles_to_srt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            srt_path = Path(temp_dir) / "subtitles.srt"
            scenes = [
                ArticleScene(
                    scene_index=0,
                    text="Câu mở đầu câu chuyện.",
                    start_time_ms=0,
                    duration_ms=3500,
                ),
                ArticleScene(
                    scene_index=1,
                    text="Câu tiếp theo đầy kịch tính.",
                    start_time_ms=3500,
                    duration_ms=4200,
                ),
            ]
            slide_composer.export_subtitles_to_srt(scenes, srt_path)
            self.assertTrue(srt_path.is_file())

            content = srt_path.read_text(encoding="utf-8")
            self.assertIn("Câu mở đầu câu chuyện.", content)
            self.assertIn("Câu tiếp theo đầy kịch tính.", content)
            self.assertIn("00:00:00,000 --> 00:00:03,500", content)
            self.assertIn("00:00:03,500 --> 00:00:07,700", content)

    @patch("subprocess.run")
    def test_render_single_slide_mocked(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_img = temp_path / "test.png"
            fake_img.write_bytes(b"dummy")

            out_clip = temp_path / "slide.mp4"
            spec = slide_composer.SlideSpec(
                image_path=str(fake_img),
                duration_seconds=3.0,
                effect="zoom_in",
            )
            result = slide_composer.render_single_slide(spec, out_clip)
            self.assertEqual(result, out_clip)
            mock_run.assert_called()

    @patch("subprocess.run")
    def test_compose_article_video_mocked(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            fake_img = temp_path / "scene.png"
            fake_img.write_bytes(b"dummy")

            fake_audio = temp_path / "audio.wav"
            fake_audio.write_bytes(b"RIFFdummyWAVE")

            def fake_render_slide(spec, output_path, **kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"fake_mp4_content")
                return output_path

            project = ArticleVideoProject(
                project_id="test_proj_compose",
                config=ArticleProjectConfig(article_text="Xin chào các bạn."),
                scenes=[
                    ArticleScene(
                        scene_index=0,
                        text="Xin chào các bạn.",
                        duration_ms=4000,
                        has_image=True,
                        image_path=str(fake_img),
                        audio_path=str(fake_audio),
                    )
                ],
            )
            output_vid = temp_path / "output.mp4"
            progress_events = []

            def on_progress(pct, msg):
                progress_events.append((pct, msg))

            with patch("haizflow.pipeline.slide_composer.render_single_slide", side_effect=fake_render_slide):
                res = slide_composer.compose_article_video(
                    project=project,
                    output_video_path=output_vid,
                    progress_callback=on_progress,
                )
            self.assertEqual(res, output_vid)
            self.assertTrue(len(progress_events) >= 3)
            # Final event should be 100%
            self.assertEqual(progress_events[-1][0], 100)

            # Verify that in all FFmpeg calls, all '-i' inputs precede any '-map' or codec options
            for call_args in mock_run.call_args_list:
                cmd = call_args[0][0]
                if "-movflags" in cmd:
                    # This is the final muxing command
                    first_output_opt_idx = len(cmd)
                    for opt in ("-map", "-c:v", "-c:a", "-c:s", "-movflags"):
                        if opt in cmd:
                            first_output_opt_idx = min(first_output_opt_idx, cmd.index(opt))

                    # Find all '-i' indices
                    input_indices = [i for i, arg in enumerate(cmd) if arg == "-i"]
                    self.assertTrue(len(input_indices) >= 2)
                    for idx in input_indices:
                        self.assertLess(
                            idx,
                            first_output_opt_idx,
                            f"Input '-i' at index {idx} must precede output option at index {first_output_opt_idx} in command: {cmd}",
                        )
                    # Check subtitle track mapping
                    self.assertIn("-c:s", cmd)
                    self.assertIn("mov_text", cmd)


if __name__ == "__main__":
    unittest.main()
