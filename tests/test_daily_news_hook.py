"""Phase 1 (YouTube compliance plan): hook-first intro, curiosity titles, thumbnail hook."""

import unittest
from datetime import datetime
from unittest.mock import patch

from haizflow.services.daily_news import (
    WorldNewsItem,
    build_hook_title,
    fallback_offline_news_script,
    sanitize_thumbnail_hook,
    strip_leading_greeting,
)


class HookTitleTests(unittest.TestCase):
    def test_title_format_has_hook_label_and_date(self):
        title = build_hook_title("Giá Vàng Lao Dốc, Chạm Đáy Mới", "world", datetime(2026, 10, 24))
        self.assertEqual(title, "Giá Vàng Lao Dốc, Chạm Đáy Mới - Bản Tin Thế Giới 24/10/2026")

    def test_title_drops_toan_canh_and_inline_date(self):
        title = build_hook_title("Toàn Cảnh Ngày 24/10/2026: Nga Tập Kích Kyiv", "world", datetime(2026, 10, 24))
        self.assertNotIn("Toàn Cảnh", title)
        self.assertEqual(title.count("24/10/2026"), 1)
        self.assertTrue(title.startswith("Nga Tập Kích Kyiv"))

    def test_title_never_exceeds_youtube_limit_and_viral_has_shorts(self):
        title = build_hook_title("Tin " * 80, "viral", datetime(2026, 10, 24))
        self.assertLessEqual(len(title), 100)
        self.assertTrue(title.endswith("#Shorts"))
        self.assertIn("Tin Nóng & Độc Lạ 24/10/2026", title)

    def test_category_labels(self):
        self.assertIn("Bản Tin Công Nghệ", build_hook_title("AI", "tech"))
        self.assertIn("Bản Tin Bóng Đá", build_hook_title("Derby", "sports"))


class ThumbnailHookTests(unittest.TestCase):
    def test_limited_to_eight_words_uppercase(self):
        hook = sanitize_thumbnail_hook("sốc đáy mới của giá vàng thế giới hôm nay lúc này", "world")
        self.assertLessEqual(len(hook.split()), 8)
        self.assertEqual(hook, hook.upper())

    def test_empty_falls_back_to_category_default(self):
        self.assertTrue(sanitize_thumbnail_hook("", "tech"))


class GreetingGuardTests(unittest.TestCase):
    def test_strips_leading_greeting_sentence(self):
        text = "Chào mừng quý vị đã quay trở lại. Một tên lửa vừa giáng xuống trung tâm Kyiv rạng sáng nay."
        self.assertTrue(strip_leading_greeting(text).startswith("Một tên lửa"))

    def test_keeps_text_without_greeting(self):
        text = "Một tên lửa vừa giáng xuống trung tâm Kyiv rạng sáng nay."
        self.assertEqual(strip_leading_greeting(text), text)


class FallbackScriptTests(unittest.TestCase):
    def _items(self):
        return [
            WorldNewsItem(title="Oil prices surge - BBC", summary="Oil surged.", source="BBC", published="", link=""),
            WorldNewsItem(title="Markets fall - CNN", summary="Markets fell.", source="CNN", published="", link=""),
        ]

    def test_fallback_intro_has_no_greeting_and_new_fields(self):
        with patch("haizflow.services.daily_news.translate_text_en_to_vi", side_effect=lambda t, *a, **k: t), patch(
            "haizflow.services.daily_news.cook_summary_into_vietnamese", return_value="Chi tiết."
        ):
            for cat in ("world", "war", "tech", "sports", "viral"):
                digest = fallback_offline_news_script(self._items(), max_topics=2, category=cat)
                self.assertNotIn("Chào mừng", digest.scenes[0].text)
                self.assertNotIn("Toàn Cảnh", digest.title)
                self.assertLessEqual(len(digest.title), 100)
                self.assertLessEqual(len(digest.thumbnail_hook.split()), 8)
                self.assertTrue(digest.ticker_summary)


if __name__ == "__main__":
    unittest.main()
