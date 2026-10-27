"""Unit tests for direct Google YouTube Data API v3 integration."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from haizflow.services import youtube_direct


class TestYouTubeDirect(unittest.TestCase):
    """Test suite for direct Google YouTube client."""

    def test_save_and_get_client_credentials(self):
        """Verify saving and reading Google client credentials."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_file = Path(tmpdir) / "youtube_client_secret.json"
            with patch("haizflow.services.youtube_direct.CLIENT_SECRET_FILE", secret_file):
                # Initially empty
                c_id, c_secret = youtube_direct.get_client_credentials()
                self.assertEqual(c_id, "")
                self.assertEqual(c_secret, "")

                # Save credentials
                youtube_direct.save_client_credentials("my-client-id.apps.googleusercontent.com", "my-secret-key")
                c_id, c_secret = youtube_direct.get_client_credentials()
                self.assertEqual(c_id, "my-client-id.apps.googleusercontent.com")
                self.assertEqual(c_secret, "my-secret-key")

    def test_import_client_secret_file(self):
        """Verify importing downloaded Google Cloud client_secret.json file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            imported_json = Path(tmpdir) / "downloaded_client_secret.json"
            target_secret_file = Path(tmpdir) / "youtube_client_secret.json"

            sample_google_cloud_payload = {
                "installed": {
                    "client_id": "google-test-id-12345.apps.googleusercontent.com",
                    "client_secret": "GOCSPX-secret123",
                    "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            imported_json.write_text(json.dumps(sample_google_cloud_payload), encoding="utf-8")

            with patch("haizflow.services.youtube_direct.CLIENT_SECRET_FILE", target_secret_file):
                c_id, c_secret = youtube_direct.import_client_secret_file(str(imported_json))
                self.assertEqual(c_id, "google-test-id-12345.apps.googleusercontent.com")
                self.assertEqual(c_secret, "GOCSPX-secret123")

    def test_save_and_clear_token(self):
        """Verify saving, loading, and deleting OAuth tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "youtube_token.json"
            with patch("haizflow.services.youtube_direct.TOKEN_FILE", token_file):
                self.assertIsNone(youtube_direct.get_saved_token())

                token_data = {
                    "access_token": "ya29.dummy_access_token",
                    "refresh_token": "1//dummy_refresh_token",
                    "expires_in": 3600,
                    "channel_title": "Tin Tức Thế Giới 24h",
                }
                youtube_direct.save_token(token_data)
                loaded = youtube_direct.get_saved_token()
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded["access_token"], "ya29.dummy_access_token")
                self.assertEqual(loaded["channel_title"], "Tin Tức Thế Giới 24h")

                youtube_direct.clear_saved_token()
                self.assertIsNone(youtube_direct.get_saved_token())

    @patch("urllib.request.urlopen")
    def test_get_channel_info(self, mock_urlopen):
        """Verify fetching channel title via YouTube Data API."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "items": [
                {
                    "id": "UC1234567890",
                    "snippet": {
                        "title": "Thời Sự Thế Giới Official",
                        "description": "Kênh tin tức",
                    }
                }
            ]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        info = youtube_direct.get_channel_info("dummy_token")
        self.assertEqual(info["title"], "Thời Sự Thế Giới Official")
        self.assertEqual(info["id"], "UC1234567890")

    @patch("urllib.request.urlopen")
    def test_upload_video_resumable(self, mock_urlopen):
        """Verify full resumable upload protocol flow to Google YouTube."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_mp4 = Path(tmpdir) / "test_broadcast.mp4"
            dummy_mp4.write_bytes(b"0" * (1024 * 1024))  # 1MB dummy video

            # 1. Mock Init request (returns Location header)
            mock_init_resp = MagicMock()
            mock_init_resp.headers = {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=session999"}
            mock_init_resp.__enter__.return_value = mock_init_resp

            # 2. Mock Chunk upload request (returns 201 Created and video resource)
            mock_chunk_resp = MagicMock()
            mock_chunk_resp.status = 201
            mock_chunk_resp.read.return_value = json.dumps({
                "id": "dQw4w9WgXcQ",
                "snippet": {"title": "Bản Tin Thời Sự Quốc Tế"},
            }).encode("utf-8")
            mock_chunk_resp.__enter__.return_value = mock_chunk_resp

            mock_urlopen.side_effect = [mock_init_resp, mock_chunk_resp]

            with patch("haizflow.services.youtube_direct.get_valid_access_token", return_value="dummy_access_token"):
                progress_events = []
                res = youtube_direct.upload_video_to_youtube(
                    video_path=str(dummy_mp4),
                    title="Bản Tin Thời Sự Quốc Tế",
                    description="Tổng hợp diễn biến hôm nay",
                    tags=["thoisu", "tintuc"],
                    privacy_status="public",
                    progress_callback=lambda pct, msg: progress_events.append((pct, msg)),
                )

                self.assertEqual(res["video_id"], "dQw4w9WgXcQ")
                self.assertEqual(res["url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                self.assertGreater(len(progress_events), 0)

    @patch("haizflow.services.youtube_direct.get_valid_access_token", return_value="dummy_token")
    @patch("urllib.request.urlopen")
    def test_playlist_operations(self, mock_urlopen, mock_token):
        """Verify listing, finding, creating, and adding to playlists."""
        # 1. List playlists
        mock_list_resp = MagicMock()
        mock_list_resp.read.return_value = json.dumps({
            "items": [
                {
                    "id": "PLOUagwqnThxE",
                    "snippet": {"title": "Bản tin thế giới", "description": "Tin tức quốc tế"},
                    "contentDetails": {"itemCount": 5}
                }
            ]
        }).encode("utf-8")
        mock_list_resp.__enter__.return_value = mock_list_resp

        mock_urlopen.return_value = mock_list_resp
        playlists = youtube_direct.list_channel_playlists()
        self.assertEqual(len(playlists), 1)
        self.assertEqual(playlists[0]["id"], "PLOUagwqnThxE")
        self.assertEqual(playlists[0]["title"], "Bản tin thế giới")

        # 2. Find playlist by title
        found = youtube_direct.find_playlist_by_title("Bản tin thế giới")
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], "PLOUagwqnThxE")

        # 3. Add video to playlist
        mock_item_resp = MagicMock()
        mock_item_resp.read.return_value = json.dumps({
            "id": "item123",
            "snippet": {"playlistId": "PLOUagwqnThxE", "resourceId": {"videoId": "dQw4w9WgXcQ"}}
        }).encode("utf-8")
        mock_item_resp.__enter__.return_value = mock_item_resp
        mock_urlopen.return_value = mock_item_resp

        add_res = youtube_direct.add_video_to_playlist("dQw4w9WgXcQ", "PLOUagwqnThxE")
        self.assertTrue(add_res["success"])
        self.assertEqual(add_res["playlist_id"], "PLOUagwqnThxE")

    def test_has_playlist_permission(self):
        """Verify has_playlist_permission checks exact scope tokens, not substrings."""
        with patch("haizflow.services.youtube_direct.get_saved_token") as mock_tok:
            # 1. Only upload and readonly -> False
            mock_tok.return_value = {
                "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
            }
            self.assertFalse(youtube_direct.has_playlist_permission())

            # 2. Contains https://www.googleapis.com/auth/youtube -> True
            mock_tok.return_value = {
                "scope": "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.upload"
            }
            self.assertTrue(youtube_direct.has_playlist_permission())

            # 3. Contains force-ssl -> True
            mock_tok.return_value = {
                "scope": "https://www.googleapis.com/auth/youtube.force-ssl"
            }
            self.assertTrue(youtube_direct.has_playlist_permission())

            # 4. No token -> False
            mock_tok.return_value = None
            self.assertFalse(youtube_direct.has_playlist_permission())

    @patch("haizflow.services.youtube_direct.get_valid_access_token", return_value="fake_token")
    @patch("urllib.request.urlopen")
    def test_move_playlist_item(self, mock_urlopen, mock_token):
        """Verify moving a playlist item to position 0."""
        # 1. GET playlist item
        mock_get_resp = MagicMock()
        mock_get_resp.read.return_value = json.dumps({
            "items": [{"id": "item_abc_123"}]
        }).encode("utf-8")
        mock_get_resp.__enter__.return_value = mock_get_resp

        # 2. PUT playlist item with new position
        mock_put_resp = MagicMock()
        mock_put_resp.read.return_value = json.dumps({
            "id": "item_abc_123",
            "snippet": {"position": 0}
        }).encode("utf-8")
        mock_put_resp.__enter__.return_value = mock_put_resp

        mock_urlopen.side_effect = [mock_get_resp, mock_put_resp]

        res = youtube_direct.move_playlist_item("vid123", "PLOUagwqnThxE", position=0)
        self.assertTrue(res["success"])
        self.assertEqual(res["position"], 0)
        self.assertEqual(res["item_id"], "item_abc_123")

    @patch("haizflow.services.youtube_direct.get_valid_access_token", return_value="fake_token")
    @patch("urllib.request.urlopen")
    def test_set_video_privacy(self, mock_urlopen, mock_token):
        """Verify updating video privacy status to public."""
        mock_get_resp = MagicMock()
        mock_get_resp.read.return_value = json.dumps({
            "items": [{
                "id": "vid_priv_123",
                "snippet": {"title": "Bản tin sáng", "categoryId": "25", "tags": []},
                "status": {"privacyStatus": "private"}
            }]
        }).encode("utf-8")
        mock_get_resp.__enter__.return_value = mock_get_resp

        mock_put_resp = MagicMock()
        mock_put_resp.read.return_value = json.dumps({
            "id": "vid_priv_123",
            "status": {"privacyStatus": "public"}
        }).encode("utf-8")
        mock_put_resp.__enter__.return_value = mock_put_resp

        mock_urlopen.side_effect = [mock_get_resp, mock_put_resp]

        res = youtube_direct.set_video_privacy("vid_priv_123", "public")
        self.assertTrue(res["success"])
        self.assertEqual(res["privacy"], "public")

    def test_sanitize_youtube_metadata_removes_haizflow(self):
        """Verify that sanitize_youtube_metadata completely strips #haizflow / haizflow."""
        title = "Tin Nóng Rạng Sáng Nay #haizflow #Shorts"
        desc = "Bản tin thời sự thế giới mới nhất.\n\n#Shorts #haizflow #tintuc #HaizFlow"
        tags = ["Shorts", "haizflow", "#haizflow", "tintucthegioi", "HaizFlow", "thoisu"]

        clean_title, clean_desc, clean_tags = youtube_direct.sanitize_youtube_metadata(title, desc, tags)

        # Title
        self.assertNotIn("haizflow", clean_title.lower())
        self.assertIn("Tin Nóng Rạng Sáng Nay #Shorts", clean_title)

        # Description
        self.assertNotIn("haizflow", clean_desc.lower())
        self.assertIn("#Shorts #tintuc", clean_desc)

        # Tags
        self.assertNotIn("haizflow", [t.lower() for t in clean_tags])
        self.assertIn("Shorts", clean_tags)
        self.assertIn("tintucthegioi", clean_tags)
        self.assertIn("thoisu", clean_tags)

    def test_sanitize_youtube_metadata_removes_angle_brackets(self):
        """Verify that sanitize_youtube_metadata strips '<' and '>' to avoid YouTube 400 invalidDescription."""
        title = "<Breaking> Harry Kane Giành Quả Bóng Vàng 2026? >"
        desc = "Mô tả nguồn tin:\n[06] >!!!!(LIVESTREAMs!)Ballon d'Or 2026 Nominees <Live>\n🔗 https://news.google.com"
        tags = ["<thethao>", "bongda>", "#tintuc,"]

        clean_title, clean_desc, clean_tags = youtube_direct.sanitize_youtube_metadata(title, desc, tags)

        self.assertNotIn("<", clean_title)
        self.assertNotIn(">", clean_title)
        self.assertEqual(clean_title, "Breaking Harry Kane Giành Quả Bóng Vàng 2026?")

        self.assertNotIn("<", clean_desc)
        self.assertNotIn(">", clean_desc)
        self.assertIn("!!!!(LIVESTREAMs!)Ballon d'Or 2026 Nominees Live", clean_desc)

        for t in clean_tags:
            self.assertNotIn("<", t)
            self.assertNotIn(">", t)
            self.assertNotIn(",", t)

    @patch("urllib.request.urlopen")
    def test_upload_video_sanitizes_haizflow_in_payload(self, mock_urlopen):
        """Verify upload_video_to_youtube strips #haizflow from the actual JSON payload sent to Google."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_mp4 = Path(tmpdir) / "test_video.mp4"
            dummy_mp4.write_bytes(b"0" * (1024 * 1024))

            mock_init_resp = MagicMock()
            mock_init_resp.headers = {"Location": "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=session123"}
            mock_init_resp.__enter__.return_value = mock_init_resp

            mock_chunk_resp = MagicMock()
            mock_chunk_resp.status = 200
            mock_chunk_resp.read.return_value = json.dumps({"id": "clean_vid_123"}).encode("utf-8")
            mock_chunk_resp.__enter__.return_value = mock_chunk_resp

            captured_requests = []

            def fake_urlopen(req, *args, **kwargs):
                captured_requests.append(req)
                if len(captured_requests) == 1:
                    return mock_init_resp
                return mock_chunk_resp

            mock_urlopen.side_effect = fake_urlopen

            with patch("haizflow.services.youtube_direct.get_valid_access_token", return_value="dummy_access_token"):
                res = youtube_direct.upload_video_to_youtube(
                    video_path=str(dummy_mp4),
                    title="Tiêu Đề Video Thời Sự #haizflow",
                    description="Mô tả video thời sự\n#tintuc #haizflow #thoisu",
                    tags=["thoisu", "haizflow", "#haizflow", "tintuc"],
                    privacy_status="public",
                )

                self.assertEqual(res["video_id"], "clean_vid_123")
                self.assertGreater(len(captured_requests), 0)

                # Inspect init request payload sent to YouTube API
                init_req = captured_requests[0]
                payload = json.loads(init_req.data.decode("utf-8"))
                snippet = payload["snippet"]

                self.assertNotIn("haizflow", snippet["title"].lower())
                self.assertNotIn("haizflow", snippet["description"].lower())
                for t in snippet["tags"]:
                    self.assertNotIn("haizflow", t.lower())


if __name__ == "__main__":
    unittest.main()

