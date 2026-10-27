import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from haizflow.pipeline.thumbnail import MAX_THUMBNAIL_BYTES, build_thumbnail, thumbnail_size
from haizflow.services import youtube_direct


class ThumbnailTests(unittest.TestCase):
    def _src(self, tmp: str) -> str:
        path = Path(tmp) / "src.jpg"
        Image.effect_noise((900, 600), 80).convert("RGB").save(path)
        return str(path)

    def test_landscape_thumbnail_size_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build_thumbnail(self._src(tmp), "SỐC: ĐÁY MỚI?", "BẢN TIN THẾ GIỚI", Path(tmp) / "t.jpg", "16:9")
            with Image.open(out) as img:
                self.assertEqual(img.size, thumbnail_size("16:9"))
            self.assertLessEqual(out.stat().st_size, MAX_THUMBNAIL_BYTES)

    def test_portrait_and_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build_thumbnail(None, "TIN LẠ CHƯA TỪNG THẤY TRÊN MẠNG XÃ HỘI", "TIN NÓNG & ĐỘC LẠ", Path(tmp) / "t.jpg", "9:16")
            with Image.open(out) as img:
                self.assertEqual(img.size, (720, 1280))

    def test_set_thumbnail_missing_file_never_raises(self):
        res = youtube_direct.set_video_thumbnail("abc", "Z:/nope.jpg", access_token="x")
        self.assertFalse(res["success"])

    def test_set_thumbnail_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "t.jpg"
            f.write_bytes(b"\xff\xd8\xff")
            fake = mock.MagicMock()
            fake.__enter__.return_value.read.return_value = b"{}"
            with mock.patch("urllib.request.urlopen", return_value=fake):
                res = youtube_direct.set_video_thumbnail("vid1", str(f), access_token="x")
            self.assertTrue(res["success"])


    def test_weekday_themes_and_category_palette(self):
        from datetime import datetime
        from haizflow.pipeline.thumbnail import (
            WEEKDAY_THEMES,
            CATEGORY_LABEL_PALETTE,
            get_weekday_hook_color,
            get_category_label_color,
        )

        # 1. Test 7 Day Themes
        self.assertEqual(len(WEEKDAY_THEMES), 7)
        # Monday (0) - Thanh Mộc (#2E8B57)
        mon_dt = datetime(2026, 10, 26)  # Monday
        self.assertEqual(mon_dt.weekday(), 0)
        self.assertEqual(get_weekday_hook_color(mon_dt), (46, 139, 87))

        # Tuesday (1) - Xích Hỏa (#C62828)
        tue_dt = datetime(2026, 10, 27)
        self.assertEqual(get_weekday_hook_color(tue_dt), (198, 40, 40))

        # Wednesday (2) - Hoàng Thổ (#D4A72C)
        wed_dt = datetime(2026, 10, 28)
        self.assertEqual(get_weekday_hook_color(wed_dt), (212, 167, 44))

        # Thursday (3) - Bạch Kim (#C4C9D0)
        thu_dt = datetime(2026, 10, 29)
        self.assertEqual(get_weekday_hook_color(thu_dt), (196, 201, 208))

        # Friday (4) - Huyền Thủy (#202A44)
        fri_dt = datetime(2026, 10, 30)
        self.assertEqual(get_weekday_hook_color(fri_dt), (32, 42, 68))

        # Saturday (5) - Lam Ảnh (#4169A1)
        sat_dt = datetime(2026, 10, 31)
        self.assertEqual(get_weekday_hook_color(sat_dt), (65, 105, 161))

        # Sunday (6) - Vàng nắng cà phê (#F4C95D)
        sun_dt = datetime(2026, 11, 1)
        self.assertEqual(get_weekday_hook_color(sun_dt), (244, 201, 93))

        # 2. Test Category Title Palette
        self.assertEqual(get_category_label_color("BẢN TIN THỜI SỰ", "world"), (23, 54, 93))
        self.assertEqual(get_category_label_color("BẢN TIN CÔNG NGHỆ", "tech"), (8, 127, 140))
        self.assertEqual(get_category_label_color("BẢN TIN CHIẾN SỰ", "war"), (159, 32, 40))
        self.assertEqual(get_category_label_color("BẢN TIN BÓNG ĐÁ", "sports"), (23, 107, 58))
        self.assertEqual(get_category_label_color("TIN NÓNG & ĐỘC LẠ", "viral"), (102, 51, 153))
        self.assertEqual(get_category_label_color("TIN VUI", "hope"), (184, 92, 0))


if __name__ == "__main__":
    unittest.main()
