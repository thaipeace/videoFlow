"""Unit tests for DailyNewsController."""

import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from haizflow.desktop.daily_news_controller import DailyNewsController


class TestDailyNewsController(unittest.TestCase):
    """Test suite for DailyNewsController state, setters, signals, and workflows."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.fake_settings_file = Path(self.tmp_dir.name) / "daily_news_settings.json"
        self.settings_patcher = patch(
            "haizflow.desktop.daily_news_controller.SETTINGS_FILE",
            self.fake_settings_file,
        )
        self.settings_patcher.start()
        with patch("haizflow.desktop.daily_news_controller.DailyNewsController.refreshScheduleStatus"):
            self.controller = DailyNewsController()

    def tearDown(self):
        self.settings_patcher.stop()
        self.tmp_dir.cleanup()

    def test_initial_defaults(self):
        """Verify default properties on initialization."""
        self.assertFalse(self.controller.isBusy)
        self.assertEqual(self.controller.progressPercent, 0)
        self.assertEqual(self.controller.status, "idle")
        self.assertIn(self.controller.selectedCategory, ("tin_moi", "tin_nong", "hope", "viral", "world", "war", "tech", "sports"))
        self.assertIn(self.controller.aspectRatio, ("16:9", "9:16"))
        self.assertGreaterEqual(self.controller.maxTopics, 2)
        self.assertIn(self.controller.detailLevel, ("concise", "standard", "deep"))
        self.assertIn(self.controller.youtubePrivacy, ("public", "unlisted", "private"))
        self.assertIsInstance(self.controller.autoUploadYoutube, bool)
        self.assertIsInstance(self.controller.autoUploadFacebook, bool)
        self.assertIsInstance(self.controller.bgmEnabled, bool)
        self.assertIsInstance(self.controller.bgmVolume, float)
        self.assertIsInstance(self.controller.historyList, list)

        # Fresh controller with no existing settings file must default to 'tin_moi'
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("haizflow.desktop.daily_news_controller.SETTINGS_FILE", Path(tmpdir) / "none.json"):
                with patch("haizflow.desktop.daily_news_controller.DailyNewsController.refreshScheduleStatus"):
                    fresh = DailyNewsController()
                    self.assertEqual(fresh.selectedCategory, "tin_moi")

    def test_property_setters_and_bounds(self):
        """Verify property updates, constraints, and clamping."""
        # Category setter & aliases
        self.controller.setSelectedCategory("tin_moi")
        self.assertEqual(self.controller.selectedCategory, "tin_moi")
        self.assertEqual(self.controller.aspectRatio, "16:9")
        self.controller.setSelectedCategory("morning")
        self.assertEqual(self.controller.selectedCategory, "tin_moi")
        self.controller.setSelectedCategory("tin_nong")
        self.assertEqual(self.controller.selectedCategory, "tin_nong")
        self.assertEqual(self.controller.aspectRatio, "16:9")
        self.controller.setSelectedCategory("evening")
        self.assertEqual(self.controller.selectedCategory, "tin_nong")
        self.controller.setSelectedCategory("tech")
        self.assertEqual(self.controller.selectedCategory, "tech")
        self.controller.setSelectedCategory("congnghe")
        self.assertEqual(self.controller.selectedCategory, "tech")
        self.controller.setSelectedCategory("sports")
        self.assertEqual(self.controller.selectedCategory, "sports")
        self.controller.setSelectedCategory("thethao")
        self.assertEqual(self.controller.selectedCategory, "sports")
        self.controller.setSelectedCategory("viral")
        self.assertEqual(self.controller.selectedCategory, "viral")
        self.assertEqual(self.controller.aspectRatio, "9:16")
        self.controller.setSelectedCategory("tinla")
        self.assertEqual(self.controller.selectedCategory, "viral")
        self.controller.setSelectedCategory("docla")
        self.assertEqual(self.controller.selectedCategory, "viral")
        self.controller.setSelectedCategory("world")
        self.assertEqual(self.controller.selectedCategory, "world")
        self.assertEqual(self.controller.aspectRatio, "16:9")
        self.controller.setSelectedCategory("invalid")
        self.assertEqual(self.controller.selectedCategory, "tin_moi")

        # Max topics clamping (1..15)
        self.controller.setMaxTopics(5)
        self.assertEqual(self.controller.maxTopics, 5)
        self.controller.setMaxTopics(999)
        self.assertEqual(self.controller.maxTopics, 15)
        self.controller.setMaxTopics(0)
        self.assertEqual(self.controller.maxTopics, 1)
        self.controller.setMaxTopics(1)
        self.assertEqual(self.controller.maxTopics, 1)

        # Aspect ratio
        self.controller.setAspectRatio("9:16")
        self.assertEqual(self.controller.aspectRatio, "9:16")
        self.controller.setAspectRatio("16:9")
        self.assertEqual(self.controller.aspectRatio, "16:9")

        # Voice ID
        self.controller.setVoiceId("vi-VN-HoaiMyNeural")
        self.assertEqual(self.controller.voiceId, "vi-VN-HoaiMyNeural")

        # Detail level
        self.controller.setDetailLevel("deep")
        self.assertEqual(self.controller.detailLevel, "deep")
        self.controller.setDetailLevel("concise")
        self.assertEqual(self.controller.detailLevel, "concise")

        # BGM & Volume clamping
        self.controller.setBgmEnabled(False)
        self.assertFalse(self.controller.bgmEnabled)
        self.controller.setBgmVolume(0.15)
        self.assertAlmostEqual(self.controller.bgmVolume, 0.15, places=2)
        self.controller.setBgmVolume(0.50)
        self.assertAlmostEqual(self.controller.bgmVolume, 0.30, places=2)
        self.controller.setBgmVolume(0.001)
        self.assertAlmostEqual(self.controller.bgmVolume, 0.01, places=2)

        # Social auto-upload toggles
        self.controller.setAutoUploadYoutube(True)
        self.assertTrue(self.controller.autoUploadYoutube)
        self.controller.setAutoUploadFacebook(True)
        self.assertTrue(self.controller.autoUploadFacebook)

        # YouTube Privacy
        self.controller.setYoutubePrivacy("public")
        self.assertEqual(self.controller.youtubePrivacy, "public")
        self.controller.setYoutubePrivacy("unlisted")
        self.assertEqual(self.controller.youtubePrivacy, "unlisted")
        self.controller.setYoutubePrivacy("private")
        self.assertEqual(self.controller.youtubePrivacy, "private")

        # YouTube Playlist settings
        self.controller.setAutoAddToPlaylist(True)
        self.assertTrue(self.controller.autoAddToPlaylist)
        self.controller.setSelectedCategory("world")
        self.controller.setYoutubePlaylistWorld("Bản tin thế giới")
        self.assertEqual(self.controller.currentCategoryPlaylist, "Bản tin thế giới")
        self.controller.setCurrentCategoryPlaylist("Bản tin quốc tế")
        self.assertEqual(self.controller.youtubePlaylistWorld, "Bản tin quốc tế")
        self.assertEqual(self.controller.currentCategoryPlaylist, "Bản tin quốc tế")

        self.controller.setSelectedCategory("viral")
        self.controller.setYoutubePlaylistViral("Tin lạ & Độc lạ thế giới")
        self.assertEqual(self.controller.youtubePlaylistViral, "Tin lạ & Độc lạ thế giới")
        self.assertEqual(self.controller.currentCategoryPlaylist, "Tin lạ & Độc lạ thế giới")
        self.controller.setCurrentCategoryPlaylist("Tin sốc thế giới")
        self.assertEqual(self.controller.youtubePlaylistViral, "Tin sốc thế giới")
        self.assertEqual(self.controller.currentCategoryPlaylist, "Tin sốc thế giới")

        # Scheduler
        self.controller.setScheduleTime("06:30")
        self.assertEqual(self.controller.scheduleTime, "06:30")
        self.controller.setScheduleWakeUp(False)
        self.assertFalse(self.controller.scheduleWakeUp)

    def test_signals_emission(self):
        """Verify that modifying properties emits notification signals."""
        signals_received = []

        self.controller.selectedCategoryChanged.connect(lambda: signals_received.append("category"))
        self.controller.maxTopicsChanged.connect(lambda: signals_received.append("maxTopics"))
        self.controller.aspectRatioChanged.connect(lambda: signals_received.append("aspectRatio"))
        self.controller.autoUploadYoutubeChanged.connect(lambda: signals_received.append("autoYT"))
        self.controller.autoUploadFacebookChanged.connect(lambda: signals_received.append("autoFB"))

        self.controller.setSelectedCategory("tech")
        self.controller.setMaxTopics(7 if self.controller.maxTopics != 7 else 9)
        target_ratio = "9:16" if self.controller.aspectRatio == "16:9" else "16:9"
        self.controller.setAspectRatio(target_ratio)
        self.controller.setAutoUploadYoutube(not self.controller.autoUploadYoutube)
        self.controller.setAutoUploadFacebook(not self.controller.autoUploadFacebook)

        self.assertIn("category", signals_received)
        self.assertIn("maxTopics", signals_received)
        self.assertIn("aspectRatio", signals_received)
        self.assertIn("autoYT", signals_received)
        self.assertIn("autoFB", signals_received)

    def test_cancel_production(self):
        """Verify cancelProduction signals and event flag."""
        self.controller.cancelProduction()
        self.assertTrue(self.controller._cancel_event.is_set())
        self.assertIn("dừng", self.controller.progressMessage.lower())

    def test_history_parsing(self):
        """Verify scanning and parsing of history runs from runtime data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "daily_news"
            # 1. World news item
            run_dir_1 = base_dir / "20261020_080000"
            run_dir_1.mkdir(parents=True)
            v1 = run_dir_1 / "world_news_20261020_080000.mp4"
            v1.write_bytes(b"dummy_mp4_bytes")
            m1 = run_dir_1 / "social_publish_manifest.json"
            m1.write_text(json.dumps({
                "title": "Bản Tin Thời Sự Thế Giới Đặc Biệt",
                "summary": "Tổng hợp diễn biến quan trọng hôm nay.",
                "hashtags": "#tintucthegioi #thoisu",
                "category": "world",
                "category_label": "Thời sự",
                "scenes_count": 5,
                "aspect_ratio": "16:9",
                "created_at": "2026-10-20 08:00:00",
            }), encoding="utf-8")

            # 2. Tech news item
            run_dir_2 = base_dir / "tech_20261020_090000"
            run_dir_2.mkdir(parents=True)
            v2 = run_dir_2 / "tech_news_20261020_090000.mp4"
            v2.write_bytes(b"dummy_mp4_bytes_tech")
            m2 = run_dir_2 / "social_publish_manifest.json"
            m2.write_text(json.dumps({
                "title": "Bản Tin Công Nghệ Thế Giới Mới Nhất",
                "summary": "Nvidia ra mắt chip AI Blackwell Ultra.",
                "hashtags": "#congnghe #ai",
                "category": "tech",
                "category_label": "Công nghệ",
                "scenes_count": 6,
                "aspect_ratio": "16:9",
                "created_at": "2026-10-20 09:00:00",
            }), encoding="utf-8")

            with patch("haizflow.desktop.daily_news_controller.runtime_data_dir", return_value=Path(tmpdir)):
                self.controller.refreshHistory()

            self.assertEqual(len(self.controller.historyList), 2)
            categories = {item["category"] for item in self.controller.historyList}
            self.assertIn("world", categories)
            self.assertIn("tech", categories)
            tech_item = next(it for it in self.controller.historyList if it["category"] == "tech")
            self.assertEqual(tech_item["category_label"], "Công nghệ")
            self.assertEqual(tech_item["video_name"], "tech_news_20261020_090000.mp4")

    @patch("haizflow.services.youtube_direct.get_saved_token", return_value=None)
    @patch("haizflow.services.zernio_keys.active_key", return_value=None)
    def test_publish_video_without_api_key(self, mock_key, mock_yt_token):
        """Verify social publish without Zernio API key reports ready state."""
        try:
            from PySide6.QtCore import Qt
            direct_conn = Qt.DirectConnection
        except ImportError:
            direct_conn = None

        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_video = Path(tmpdir) / "news.mp4"
            dummy_video.write_bytes(b"data")

            completed_events = []
            if direct_conn:
                self.controller.uploadCompleted.connect(lambda p, post_id: completed_events.append((p, post_id)), direct_conn)
            else:
                self.controller.uploadCompleted.connect(lambda p, post_id: completed_events.append((p, post_id)))

            thread = self.controller.publishVideo(str(dummy_video), "youtube")
            if thread:
                thread.join(timeout=3.0)

            self.assertGreater(len(completed_events), 0)
            platform, status = completed_events[0]
            self.assertEqual(platform, "youtube")
            self.assertEqual(status, "local_ready")

    @patch("subprocess.run")
    def test_schedule_management(self, mock_run):
        """Verify configuring and removing Windows scheduled task."""
        mock_run.return_value = MagicMock(returncode=0)

        self.controller.configureSchedule("06:30", True)
        self.assertTrue(mock_run.called)

        mock_run.reset_mock()
        self.controller.removeSchedule()
        self.assertTrue(mock_run.called)

    @patch("haizflow.desktop.daily_news_controller.produce_daily_news_video")
    def test_start_production_with_category(self, mock_produce):
        """Verify starting production with specific category passes it to pipeline."""
        mock_produce.return_value = Path("test_video.mp4")

        self.controller.setSelectedCategory("tech")
        self.controller.startProduction()
        if self.controller._worker_thread:
            self.controller._worker_thread.join(timeout=2.0)

        mock_produce.assert_called()
        _, kwargs = mock_produce.call_args
        self.assertEqual(kwargs.get("category"), "tech")

    def test_dismiss_banner_and_clear_message(self):
        """Verify dismissing banner resets status and clears messages."""
        self.controller._status = "error"
        self.controller._upload_message = "Upload failed error"
        self.controller.dismissBanner()
        self.assertEqual(self.controller.status, "idle")
        self.assertEqual(self.controller.uploadMessage, "")

        self.controller._upload_message = "Sample msg"
        self.controller.clearUploadMessage()
        self.assertEqual(self.controller.uploadMessage, "")

    def test_daily_news_qml_component_loads(self):
        """Verify that DailyNewsPage.qml is ready without syntax or type errors."""
        try:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtQml import QQmlEngine, QQmlComponent
            from PySide6.QtCore import QUrl
        except ImportError:
            self.skipTest("PySide6 QML dependencies not available in environment.")

        app = QGuiApplication.instance() or QGuiApplication([])
        engine = QQmlEngine()
        qml_dir = Path(__file__).resolve().parent.parent / "src" / "haizflow" / "desktop" / "qml"
        engine.addImportPath(str(qml_dir))
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_dir / "DailyNewsPage.qml")))
        self.assertTrue(component.isReady(), "\n".join(e.toString() for e in component.errors()))


    def test_update_and_toggle_youtube_status(self):
        """Verify updating and toggling YouTube publication status in history manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "daily_news"
            run_dir = base_dir / "20261020_120000"
            run_dir.mkdir(parents=True, exist_ok=True)
            v_file = run_dir / "world_news_20261020_120000.mp4"
            v_file.write_bytes(b"dummy video data")

            manifest_file = run_dir / "social_publish_manifest.json"
            manifest_file.write_text(json.dumps({
                "title": "Bản Tin Thời Sự Thế Giới",
                "category": "world",
                "category_label": "Thời sự",
                "youtube_published": False,
            }), encoding="utf-8")

            with patch("haizflow.desktop.daily_news_controller.runtime_data_dir", return_value=Path(tmpdir)):
                self.controller.refreshHistory()
                self.assertEqual(len(self.controller.historyList), 1)
                item = self.controller.historyList[0]
                self.assertFalse(item["youtube_published"])

                # 1. Update status to True with custom URL and note
                res = self.controller.updateYouTubeStatus(
                    video_path=str(v_file),
                    published=True,
                    video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    note="Đăng thủ công kênh chính",
                )
                self.assertTrue(res)

                # Verify updated in historyList
                item = self.controller.historyList[0]
                self.assertTrue(item["youtube_published"])
                self.assertEqual(item["youtube_video_id"], "dQw4w9WgXcQ")
                self.assertEqual(item["youtube_url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                self.assertEqual(item["custom_note"], "Đăng thủ công kênh chính")
                self.assertTrue(bool(item["youtube_published_at"]))

                # 2. Toggle status
                self.controller.toggleYouTubeStatus(str(v_file))
                item = self.controller.historyList[0]
                self.assertFalse(item["youtube_published"])
                self.assertEqual(item["youtube_published_at"], "")

                # 3. Toggle back
                self.controller.toggleYouTubeStatus(str(v_file))
                item = self.controller.historyList[0]
                self.assertTrue(item["youtube_published"])

    def test_delete_video(self):
        """Verify permanently deleting a video and its directory from history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "daily_news"
            run_dir = base_dir / "20261020_150000"
            run_dir.mkdir(parents=True, exist_ok=True)
            v_file = run_dir / "tech_news_20261020_150000.mp4"
            v_file.write_bytes(b"dummy video content")

            with patch("haizflow.desktop.daily_news_controller.runtime_data_dir", return_value=Path(tmpdir)):
                self.controller._last_video_path = str(v_file)
                self.controller.refreshHistory()
                self.assertEqual(len(self.controller.historyList), 1)

                # Delete video
                res = self.controller.deleteVideo(str(v_file))
                self.assertTrue(res)
                self.assertFalse(v_file.exists())
                self.assertFalse(run_dir.exists())
                self.assertEqual(self.controller.lastVideoPath, "")
                self.assertEqual(len(self.controller.historyList), 0)

                # Deleting non-existent video returns False gracefully
                res_fake = self.controller.deleteVideo(str(Path(tmpdir) / "fake.mp4"))
                self.assertFalse(res_fake)

    def test_category_schedules(self):
        """Verify per-category schedule management, time setting, wake-up, and status."""
        # 1. Verify categorySchedules list structure (1 Broadcast + 2 Shorts)
        schedules = self.controller.categorySchedules
        self.assertEqual(len(schedules), 3)
        cats = [s["category"] for s in schedules]
        self.assertEqual(cats, ["tin_moi", "hope", "ai"])

        # 2. Set individual category times and wake up
        with patch.object(self.controller, "configureCategorySchedule", return_value=True):
            self.controller.setCategoryScheduleTime("tin_moi", "06:00")
            self.controller.setCategoryScheduleTime("hope", "12:00")
            self.controller.setCategoryScheduleTime("ai", "17:30")
            self.controller.setCategoryScheduleWakeUp("ai", False)

        sched_map = {s["category"]: s for s in self.controller.categorySchedules}
        self.assertEqual(sched_map["tin_moi"]["time"], "06:00")
        self.assertEqual(sched_map["hope"]["time"], "12:00")
        self.assertEqual(sched_map["ai"]["time"], "17:30")
        self.assertFalse(sched_map["ai"]["wake_up"])
        self.assertTrue(sched_map["tin_moi"]["wake_up"])

        # 3. Switching active category updates scheduleTime and scheduleWakeUp
        self.controller.setSelectedCategory("ai")
        self.assertEqual(self.controller.scheduleTime, "17:30")
        self.assertFalse(self.controller.scheduleWakeUp)

        self.controller.setSelectedCategory("tin_moi")
        self.assertEqual(self.controller.scheduleTime, "06:00")
        self.assertTrue(self.controller.scheduleWakeUp)

        self.controller.setSelectedCategory("hope")
        self.assertEqual(self.controller.scheduleTime, "12:00")
        self.assertTrue(self.controller.scheduleWakeUp)

        # 4. Mock configureCategorySchedule and removeCategorySchedule
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = self.controller.configureCategorySchedule("hope", "12:15", True)
            self.assertTrue(ok)
            self.assertEqual(self.controller._schedules["hope"]["time"], "12:15")

            ok_del = self.controller.removeCategorySchedule("hope")
            self.assertTrue(ok_del)

    def test_playlist_management(self):
        """Verify unified playlist settings, single video addition, and batch addition."""
        # 1. Defaults and setAllPlaylistsToWorldNews
        self.controller.setYoutubePlaylistTech("Bản tin tạm thời")
        self.assertEqual(self.controller.youtubePlaylistTech, "Bản tin tạm thời")

        self.controller.setAllPlaylistsToWorldNews()
        self.assertEqual(self.controller.youtubePlaylistWorld, "Bản tin thế giới")
        self.assertEqual(self.controller.youtubePlaylistTech, "Bản tin thế giới")
        self.assertEqual(self.controller.youtubePlaylistSports, "Bản tin thế giới")
        self.assertEqual(self.controller.youtubePlaylistViral, "Bản tin thế giới")
        self.assertEqual(self.controller.youtubePlaylistHope, "Bản tin thế giới")

        # 2. Add single video to playlist
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "daily_news" / "run_20261021_01"
            run_dir.mkdir(parents=True)
            v_file = run_dir / "world_news_20261021.mp4"
            v_file.write_bytes(b"dummy")

            manifest = {
                "title": "Bản Tin Thế Giới Đặc Biệt",
                "youtube_published": True,
                "youtube_video_id": "vid_abc_123",
                "youtube_url": "https://www.youtube.com/watch?v=vid_abc_123",
            }
            mf_path = run_dir / "social_publish_manifest.json"
            mf_path.write_text(json.dumps(manifest), encoding="utf-8")

            with patch("haizflow.desktop.daily_news_controller.runtime_data_dir", return_value=Path(tmpdir)):
                with patch("haizflow.services.youtube_direct.get_or_create_playlist", return_value=("PLOUagwqnThxE", "Bản tin thế giới")):
                    with patch("haizflow.services.youtube_direct.add_video_to_playlist", return_value={"success": True, "already_in_playlist": False}):
                        ok = self.controller.addVideoToPlaylist(str(v_file), "Bản tin thế giới")
                        self.assertTrue(ok)

                        # Check that manifest was updated with playlist info
                        updated_m = json.loads(mf_path.read_text(encoding="utf-8"))
                        self.assertEqual(updated_m.get("youtube_playlist_title"), "Bản tin thế giới")
                        self.assertEqual(updated_m.get("youtube_playlist_id"), "PLOUagwqnThxE")

                        # 3. Batch add all videos
                        self.controller.refreshHistory()
                        self.assertEqual(len(self.controller.historyList), 1)

                        with patch("threading.Thread") as mock_thread:
                            # Run target immediately
                            def run_target(target, daemon=True):
                                m = MagicMock()
                                m.start = lambda: target()
                                return m
                            mock_thread.side_effect = run_target
                            self.controller.addAllVideosToPlaylist("Bản tin thế giới")

                        self.assertIn("Bản tin thế giới", self.controller.uploadMessage)

    def test_video_title_with_date(self):
        """Verify video title formatting with date, updating title, and batch date migration."""
        from haizflow.services.daily_news import ensure_date_in_title
        from datetime import datetime

        # 1. Test ensure_date_in_title helper
        fixed_dt = datetime(2026, 10, 21, 8, 30)
        t1 = ensure_date_in_title("Bản Tin Thế Giới Toàn Cảnh: Diễn Biến Nóng", fixed_dt)
        self.assertEqual(t1, "Bản Tin Thế Giới Toàn Cảnh Ngày 21/10/2026: Diễn Biến Nóng")

        t2 = ensure_date_in_title("Bản Tin Bóng Đá Toàn Cảnh", fixed_dt)
        self.assertEqual(t2, "Bản Tin Bóng Đá Toàn Cảnh Ngày 21/10/2026")

        t3 = ensure_date_in_title("Bản Tin Thời Sự Ngày 20/10/2026: Tin Cũ", fixed_dt)
        self.assertEqual(t3, "Bản Tin Thời Sự Ngày 20/10/2026: Tin Cũ")

        # ISO timestamp parsing
        t4 = ensure_date_in_title("Bản Tin Công Nghệ Toàn Cảnh", "2026-10-20T15:30:00+00:00")
        self.assertEqual(t4, "Bản Tin Công Nghệ Toàn Cảnh Ngày 20/10/2026")

        # 2. Test updateVideoTitle on controller
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "daily_news" / "run_20261021_02"
            run_dir.mkdir(parents=True)
            v_file = run_dir / "world_news.mp4"
            v_file.write_bytes(b"data")
            mf_path = run_dir / "social_publish_manifest.json"
            mf_path.write_text(json.dumps({
                "title": "Bản Tin Cũ",
                "created_at": "2026-10-21T07:00:00+00:00",
            }), encoding="utf-8")

            with patch("haizflow.desktop.daily_news_controller.runtime_data_dir", return_value=Path(tmpdir)):
                # Update title
                ok = self.controller.updateVideoTitle(str(v_file), "Bản Tin Mới Cập Nhật")
                self.assertTrue(ok)

                saved_m = json.loads(mf_path.read_text(encoding="utf-8"))
                self.assertIn("21/10/2026", saved_m["title"])

                # Update with updateYouTubeStatus
                ok_yt = self.controller.updateYouTubeStatus(
                    video_path=str(v_file),
                    published=True,
                    video_url="https://www.youtube.com/watch?v=123",
                    note="Ghi chú test",
                    title="Bản Tin Tối Siêu Nóng"
                )
                self.assertTrue(ok_yt)
                saved_m2 = json.loads(mf_path.read_text(encoding="utf-8"))
                self.assertIn("21/10/2026", saved_m2["title"])

    def test_save_production_settings(self):
        """Verify saveProductionSettings updates all fields in memory and writes once to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_settings_file = Path(tmpdir) / "daily_news_settings.json"
            with patch("haizflow.desktop.daily_news_controller.SETTINGS_FILE", fake_settings_file):
                self.controller.setSelectedCategory("war")
                self.controller.saveProductionSettings(
                    max_topics=10,
                    aspect_ratio="16:9",
                    voice_id="multi_trio",
                    bgm_enabled=True,
                    bgm_volume=0.12,
                    auto_upload_youtube=True,
                    youtube_privacy="unlisted",
                    auto_add_playlist=True,
                    playlist_title="Chiến sự thế giới đặc biệt",
                )

                self.assertEqual(self.controller.maxTopics, 10)
                self.assertEqual(self.controller.aspectRatio, "16:9")
                self.assertEqual(self.controller.voiceId, "multi_trio")
                self.assertTrue(self.controller.bgmEnabled)
                self.assertAlmostEqual(self.controller.bgmVolume, 0.12, places=2)
                self.assertTrue(self.controller.autoUploadYoutube)
                self.assertEqual(self.controller.youtubePrivacy, "unlisted")
                self.assertTrue(self.controller.autoAddToPlaylist)
                self.assertEqual(self.controller.youtubePlaylistWar, "Chiến sự thế giới đặc biệt")
                self.assertEqual(self.controller.currentCategoryPlaylist, "Chiến sự thế giới đặc biệt")

                self.assertTrue(fake_settings_file.is_file())
                saved_data = json.loads(fake_settings_file.read_text(encoding="utf-8"))
                self.assertEqual(saved_data["max_topics"], 10)
                self.assertEqual(saved_data["youtube_playlist_war"], "Chiến sự thế giới đặc biệt")


if __name__ == "__main__":
    unittest.main()




