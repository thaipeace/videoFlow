"""Unit tests for ArticleVideoController."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from haizflow.desktop.article_video_controller import ArticleVideoController
from haizflow.schemas.article_video import (
    ArticleProjectConfig,
    ArticleScene,
    ArticleVideoProject,
    CharacterPreset,
)


class TestArticleVideoController(unittest.TestCase):
    """Test suite for ArticleVideoController state, signals, and workflows."""

    def setUp(self):
        self.controller = ArticleVideoController()

    def tearDown(self):
        self.controller.resetToDefaultCharacters()

    def test_initial_defaults(self):
        """Verify default properties on initialization."""
        self.assertEqual(self.controller.articleText, "")
        self.assertEqual(self.controller.imageCountTarget, 1)
        self.assertEqual(self.controller.imageStyle, "anime_2d")
        self.assertEqual(self.controller.aspectRatio, "16:9")
        self.assertEqual(self.controller.ttsProvider, "edge")
        self.assertEqual(self.controller.selectedCharacterId, "none")
        self.assertEqual(self.controller.status, "idle")
        self.assertFalse(self.controller.isBusy)
        self.assertEqual(self.controller.scenesCount, 0)
        self.assertGreater(len(self.controller.characters), 0)

    def test_property_setters_and_bounds(self):
        """Verify property updates and range bounds."""
        self.controller.setArticleText("Chào mừng bạn đến với ứng dụng đọc truyện!")
        self.assertEqual(self.controller.articleText, "Chào mừng bạn đến với ứng dụng đọc truyện!")

        self.controller.setImageCountTarget(5)
        self.assertEqual(self.controller.imageCountTarget, 5)
        # Clamping
        self.controller.setImageCountTarget(999)
        self.assertEqual(self.controller.imageCountTarget, 10)
        self.controller.setImageCountTarget(-5)
        self.assertEqual(self.controller.imageCountTarget, 1)

        self.controller.setImageStyle("manhwa_webtoon")
        self.assertEqual(self.controller.imageStyle, "manhwa_webtoon")

        self.controller.setAspectRatio("9:16")
        self.assertEqual(self.controller.aspectRatio, "9:16")

        self.controller.setTtsSpeed(1.25)
        self.assertAlmostEqual(self.controller.ttsSpeed, 1.25, places=2)

        self.controller.setBgmVolume(0.3)
        self.assertAlmostEqual(self.controller.bgmVolume, 0.3, places=2)

    def test_character_selection(self):
        """Verify selecting character from loaded catalog."""
        chars = self.controller.characters
        self.assertGreater(len(chars), 0)
        first_id = chars[0]["id"]
        self.controller.selectCharacter(first_id)
        self.assertEqual(self.controller.selectedCharacterId, first_id)

    @patch("haizflow.desktop.article_video_controller.direct_article")
    def test_analyze_story(self, mock_direct):
        """Test analyzeStory creates project and populates scenes model."""
        mock_direct.return_value = [
            ArticleScene(
                scene_index=0,
                text="Mở đầu bài viết.",
                image_prompt="A vivid scene",
                duration_ms=4000,
                has_image=True,
                visual_priority_score=9.0,
            ),
            ArticleScene(
                scene_index=1,
                text="Phần kết bài viết.",
                image_prompt="",
                duration_ms=3500,
                has_image=False,
                visual_priority_score=2.0,
            ),
        ]

        self.controller.setArticleText("Đây là một câu chuyện hay về học sinh.")
        self.controller.analyzeStory()

        # Wait for worker thread
        if self.controller._worker_thread:
            self.controller._worker_thread.join(timeout=3.0)

        self.assertEqual(self.controller.status, "idle")
        self.assertEqual(self.controller.scenesCount, 2)
        self.assertTrue(self.controller.hasProject)
        self.assertEqual(self.controller.scenes[0]["text"], "Mở đầu bài viết.")
        self.assertEqual(self.controller.scenes[0]["duration_ms"], 4000)

    @patch("haizflow.desktop.article_video_controller.generate_scenes_images")
    def test_generate_images(self, mock_gen_images):
        """Test generating images for existing project scenes."""
        # Setup mock project
        config = ArticleProjectConfig(article_text="Test", character_id="char_nam_hoc_sinh")
        scenes = [
            ArticleScene(scene_index=0, text="Scene 1", image_prompt="Hero", duration_ms=3000, has_image=True),
        ]
        self.controller._current_project = ArticleVideoProject(
            project_id="proj_1", project_name="T", config=config, scenes=scenes
        )
        self.controller._sync_scenes_model()

        def fake_generate(scenes, config, output_dir, progress_callback=None, cancel_event=None):
            scenes[0].image_path = "C:/tmp/scene_0.jpg"
            if progress_callback:
                progress_callback(100, "Done")
            return scenes

        mock_gen_images.side_effect = fake_generate

        self.controller.generateImages()
        if self.controller._worker_thread:
            self.controller._worker_thread.join(timeout=3.0)

        self.assertEqual(self.controller.status, "idle")
        self.assertEqual(self.controller.scenes[0]["image_path"], "C:/tmp/scene_0.jpg")

    @patch("haizflow.desktop.article_video_controller.compose_article_video")
    @patch("haizflow.desktop.article_video_controller.generate_scenes_images")
    def test_render_video(self, mock_gen, mock_compose):
        """Test rendering video triggers pipeline and updates output path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "output.mp4"
            out_file.touch()
            mock_compose.return_value = out_file

            config = ArticleProjectConfig(article_text="Test", character_id="char_my_dung")
            scenes = [
                ArticleScene(
                    scene_index=0,
                    text="Scene 1",
                    image_prompt="Hero",
                    duration_ms=3000,
                    has_image=True,
                    image_path=str(out_file),
                ),
            ]
            self.controller._current_project = ArticleVideoProject(
                project_id="proj_1", project_name="T", config=config, scenes=scenes
            )
            self.controller._sync_scenes_model()

            self.controller.renderVideo()
            if self.controller._worker_thread:
                self.controller._worker_thread.join(timeout=3.0)

            self.assertEqual(self.controller.status, "done")
            self.assertEqual(self.controller.outputVideoPath, str(out_file))

    def test_voice_preview(self):
        """Test voice preview sample resolution and playback state toggle."""
        self.controller.setTtsProvider("vieneu")
        self.controller.setTtsVoice("vieneu:Hải Đăng")
        url = self.controller.previewVoice()
        self.assertTrue(url.startswith("file:///"))
        self.assertTrue(url.endswith(".mp3"))
        self.assertTrue(self.controller.isVoicePreviewPlaying)
        self.assertIn("Hải Đăng", self.controller.voicePreviewStatus)

        self.controller.stopVoicePreview()
        self.assertFalse(self.controller.isVoicePreviewPlaying)
        self.assertEqual(self.controller.voicePreviewStatus, "")

    def test_import_character_portrait(self):
        """Test importing a custom character portrait."""
        from PIL import Image as PilImage
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                portrait_path = Path(tmp_dir) / "custom_test_portrait.jpg"
                img = PilImage.new("RGB", (600, 800), color=(50, 100, 150))
                img.save(portrait_path)

                char_id = self.controller.importCharacterSheet(
                    str(portrait_path),
                    display_name="Nhân Vật Thử Nghiệm",
                    prompt_anchor="Mighty test portrait with glowing eyes",
                )
                self.assertTrue(char_id.startswith("char_custom_"))
                self.assertEqual(self.controller.selectedCharacterId, char_id)
                char_ids = [c["id"] for c in self.controller.characters]
                self.assertIn(char_id, char_ids)
        finally:
            self.controller.resetToDefaultCharacters()

    def test_reset_to_default_characters(self):
        """Verify resetting to default canonical characters."""
        self.controller.resetToDefaultCharacters()
        chars = self.controller.characters
        self.assertEqual(len(chars), 4)
        ids = [c["id"] for c in chars]
        self.assertEqual(ids, ["char_my_dung", "char_ba_hanh", "char_nguoi_ao_den", "char_an"])
        self.assertEqual(self.controller.selectedCharacterId, "char_my_dung")

    def test_delete_character_and_delete_all(self):
        """Verify deleting single character, deleting all, and restoring defaults."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch("haizflow.services.character_catalog.runtime_data_dir", return_value=temp_path):
                self.controller.loadCharacters()
                # Delete one character
                self.controller.deleteCharacter("char_my_dung")
                current_ids = [c["id"] for c in self.controller.characters]
                self.assertNotIn("char_my_dung", current_ids)
                self.assertEqual(self.controller.selectedCharacterId, "none")

                # Delete all characters
                self.controller.deleteAllCharacters()
                self.assertEqual(len(self.controller.characters), 0)
                self.assertEqual(self.controller.selectedCharacterId, "none")

                # Restore default characters
                self.controller.restoreDefaultCharacters()
                restored_ids = [c["id"] for c in self.controller.characters]
                self.assertIn("char_my_dung", restored_ids)
                self.assertIn("char_ba_hanh", restored_ids)

    def test_empty_article_error(self):
        """Analyze with empty text sets error and status."""
        self.controller.setArticleText("   ")
        self.controller.analyzeStory()
        self.assertEqual(self.controller.status, "error")
        self.assertIn("Vui lòng nhập nội dung", self.controller.lastErrorMessage)

    def test_reset_project(self):
        """Reset clears current project, scenes, and output."""
        self.controller._current_project = MagicMock()
        self.controller._output_video_path = "test.mp4"
        self.controller._scenes = [{"scene_index": 0}]
        self.controller.resetProject()
        self.assertIsNone(self.controller._current_project)
        self.assertEqual(self.controller.outputVideoPath, "")
        self.assertEqual(self.controller.scenesCount, 0)

    @patch("haizflow.services.gemini_translation.save_key")
    @patch("haizflow.services.gemini_translation.clear_key")
    def test_google_api_key_management(self, mock_clear, mock_save):
        """Test saving and clearing Google API key from controller."""
        self.assertFalse(self.controller.saveGoogleApiKey(""))
        mock_save.assert_not_called()

        self.assertTrue(self.controller.saveGoogleApiKey("AIzaSyFakeKey12345"))
        mock_save.assert_called_once_with("AIzaSyFakeKey12345")

        self.assertTrue(self.controller.clearGoogleApiKey())
        mock_clear.assert_called_once()

    def test_bgm_management_and_preview(self):
        """Test BGM path cleaning, filename extraction, preview triggering, and stopping."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"dummy audio data")
            temp_bgm = f.name

        try:
            # Setting with file:/// prefix
            self.controller.setBgmPath(f"file:///{temp_bgm}")
            self.assertEqual(self.controller.bgmFileName, Path(temp_bgm).name)
            self.assertFalse(self.controller.isBgmPreviewPlaying)

            # Preview
            url = self.controller.previewBgm()
            self.assertTrue(url.startswith("file:///"))
            self.assertTrue(self.controller.isBgmPreviewPlaying)
            self.assertIn(Path(temp_bgm).name, self.controller.bgmPreviewStatus)

            # Stop preview
            self.controller.stopBgmPreview()
            self.assertFalse(self.controller.isBgmPreviewPlaying)

            # Clear BGM
            self.controller.setBgmPath("")
            self.assertEqual(self.controller.bgmPath, "")
            self.assertEqual(self.controller.bgmFileName, "")
        finally:
            Path(temp_bgm).unlink(missing_ok=True)

    def test_bgm_sync_to_active_project(self):
        """Ensure changing BGM settings syncs to active project config."""
        config = ArticleProjectConfig(article_text="Test")
        self.controller._current_project = ArticleVideoProject(
            project_id="test_sync",
            project_name="Test",
            config=config,
            scenes=[],
        )

        self.controller.setBgmPath("C:/music/track.mp3")
        self.controller.setBgmVolume(0.25)

        self.assertIn("track.mp3", self.controller._current_project.config.background_music_path)
        self.assertAlmostEqual(self.controller._current_project.config.background_music_volume, 0.25)

    @patch("haizflow.desktop.article_video_controller.generate_scene_image")
    def test_regenerate_scene_image_with_note(self, mock_gen):
        """Test regenerateSceneImageWithNote appends user guidance and updates prompt."""
        scene = ArticleScene(
            scene_index=0,
            text="Một cô gái đứng ngoài cửa.",
            image_prompt="A girl standing outside",
            duration_ms=3000,
            has_image=True,
        )
        self.controller._current_project = ArticleVideoProject(
            project_id="test_regen",
            project_name="Test Regen",
            config=ArticleProjectConfig(article_text="Test"),
            scenes=[scene],
        )

        self.controller.regenerateSceneImageWithNote(0, "nhìn sang bên trái, thêm mưa to")
        if self.controller._worker_thread:
            self.controller._worker_thread.join(timeout=3.0)

        # Check prompt updated with note
        self.assertIn("specific visual direction", scene.image_prompt)
        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        self.assertFalse(kwargs.get("use_cache"))
        self.assertIsNotNone(kwargs.get("seed"))

    def test_bgm_modes_and_resolution(self):
        """Test setDefaultBgm, disableBgm, and BGM path resolution."""
        self.controller.setDefaultBgm()
        self.assertEqual(self.controller.bgmPath, "default")
        self.assertEqual(self.controller.bgmFileName, "Nhạc nền mặc định (Inspiring)")
        resolved = self.controller._resolve_bgm_path()
        self.assertIsNotNone(resolved)

        self.controller.disableBgm()
        self.assertEqual(self.controller.bgmPath, "none")
        self.assertEqual(self.controller.bgmFileName, "Tắt nhạc nền")
        self.assertIsNone(self.controller._resolve_bgm_path())

    @patch("haizflow.services.youtube_direct.get_saved_token")
    @patch("haizflow.services.youtube_direct.get_channel_info")
    def test_youtube_status_and_privacy(self, mock_info, mock_tok):
        """Test YouTube connection detection and privacy setting."""
        mock_tok.return_value = {"access_token": "dummy"}
        mock_info.return_value = {"title": "Kênh Vạn Chuyện"}

        self.controller.refreshYouTubeStatus()
        self.assertTrue(self.controller.youtubeConnected)
        self.assertEqual(self.controller.youtubeChannelTitle, "Kênh Vạn Chuyện")

        self.controller.setYoutubePrivacy("unlisted")
        self.assertEqual(self.controller.youtubePrivacy, "unlisted")
        self.controller.setYoutubePrivacy("invalid")
        self.assertEqual(self.controller.youtubePrivacy, "public")

    @patch("haizflow.services.youtube_direct.get_saved_token", return_value={"access_token": "abc"})
    @patch("haizflow.services.youtube_direct.upload_video_to_youtube")
    def test_youtube_upload_shorts_workflow(self, mock_upload, mock_tok):
        """Test YouTube Shorts upload with 9:16 aspect ratio appending #Shorts."""
        mock_upload.return_value = {
            "video_id": "test_v123",
            "url": "https://youtu.be/test_v123",
        }
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            dummy_video = f.name

        try:
            self.controller._output_video_path = dummy_video
            self.controller.setAspectRatio("9:16")
            self.controller.setArticleText("Chuyện kể lúc nửa đêm về một ngôi nhà cổ tích.")

            self.controller.uploadToYouTubeWithParams("Câu chuyện đêm khuya", "", "")
            # Wait for background thread
            if hasattr(self.controller, "_worker_thread") and self.controller._worker_thread:
                self.controller._worker_thread.join(timeout=3.0)

            # Check that upload was called
            self.assertTrue(mock_upload.called)
            _, kwargs = mock_upload.call_args
            # Verify #Shorts tag was added because of 9:16
            self.assertIn("#Shorts", kwargs.get("title", ""))
            self.assertEqual(kwargs.get("video_path"), dummy_video)
            self.assertEqual(self.controller.youtubeVideoUrl, "https://youtu.be/test_v123")
            self.assertFalse(self.controller.isUploadingYoutube)
        finally:
            Path(dummy_video).unlink(missing_ok=True)

    def test_config_sync_to_active_project(self):
        """Verify modifying UI controls automatically updates active project config."""
        config = ArticleProjectConfig(
            article_text="Test story",
            voice_provider="edge",
            voice_id="vi-VN-NamMinhNeural",
            voice_rate=1.0,
            image_style="anime_2d",
            character_id="none",
            image_count_target=1,
            aspect_ratio="16:9",
        )
        scene = ArticleScene(
            scene_index=0,
            text="Phân cảnh mở đầu",
            audio_path="/fake/audio.mp3",
            duration_ms=3000,
        )
        self.controller._current_project = ArticleVideoProject(
            project_id="test_proj_sync",
            project_name="Test Project",
            config=config,
            scenes=[scene],
            status="analyzed",
        )

        # 1. Change aspect ratio to 9:16
        self.controller.setAspectRatio("9:16")
        self.assertEqual(self.controller.aspectRatio, "9:16")
        self.assertEqual(self.controller._current_project.config.aspect_ratio, "9:16")

        # 2. Change image style to watercolor
        self.controller.setImageStyle("watercolor")
        self.assertEqual(self.controller.imageStyle, "watercolor")
        self.assertEqual(self.controller._current_project.config.image_style, "watercolor")

        # 3. Change voice to HoaiMy -> should update config and clear stale audio path
        self.controller.setTtsVoice("vi-VN-HoaiMyNeural")
        self.assertEqual(self.controller.ttsVoice, "vi-VN-HoaiMyNeural")
        self.assertEqual(self.controller._current_project.config.voice_id, "vi-VN-HoaiMyNeural")
        self.assertEqual(self.controller._current_project.scenes[0].audio_path, "")

        # 4. Change speed to 1.3
        self.controller.setTtsSpeed(1.3)
        self.assertAlmostEqual(self.controller.ttsSpeed, 1.3, places=2)
        self.assertAlmostEqual(self.controller._current_project.config.voice_rate, 1.3, places=2)

    def test_save_config_slot(self):
        """Verify saveConfig updates active config, status, and configSavedMessage."""
        self.controller.setAspectRatio("9:16")
        self.controller.setTtsVoice("vi-VN-HoaiMyNeural")
        self.controller.setTtsSpeed(1.2)
        self.controller.setImageStyle("manhwa_webtoon")

        self.controller.saveConfig()
        self.assertIn("9:16 (Shorts)", self.controller.configSavedMessage)
        self.assertIn("HoaiMyNeural", self.controller.configSavedMessage)
        self.assertIn("1.2x", self.controller.configSavedMessage)
        self.assertIn("manhwa_webtoon", self.controller.configSavedMessage)


if __name__ == "__main__":
    unittest.main()

