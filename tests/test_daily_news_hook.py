"""Phase 1 (YouTube compliance plan): hook-first intro, curiosity titles, thumbnail hook."""

import unittest
from datetime import datetime
from unittest.mock import patch

from haizflow.services.daily_news import (
    DailyNewsScene,
    WorldNewsItem,
    build_hook_title,
    build_video_chapters,
    fallback_offline_news_script,
    format_youtube_description_with_sources,
    get_mock_news_items,
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


class TinMoiChapterTests(unittest.TestCase):
    def test_tin_moi_mock_items_and_fallback_have_three_chapters(self):
        items = get_mock_news_items("tin_moi")
        self.assertEqual(
            [it.topic_block for it in items],
            ["world", "world", "world", "war", "war", "war", "sports", "sports"],
        )
        with patch("haizflow.services.daily_news.translate_text_en_to_vi", side_effect=lambda t, *a, **k: t), patch(
            "haizflow.services.daily_news.cook_summary_into_vietnamese", return_value="Chi tiết."
        ):
            digest = fallback_offline_news_script(items, max_topics=8, category="tin_moi")
            blocks = [s.topic_block for s in digest.scenes if s.topic_block in ("world", "war", "sports")]
            # Ordered world -> war -> sports
            self.assertEqual(blocks, sorted(blocks, key=lambda b: ("world", "war", "sports").index(b)))
            self.assertEqual(set(blocks), {"world", "war", "sports"})
            labels = [s.chapter_label for s in digest.scenes if s.chapter_label]
            self.assertIn("THỜI SỰ THẾ GIỚI", labels)
            self.assertIn("ĐIỂM NÓNG CHIẾN SỰ", labels)
            self.assertIn("THỂ THAO QUỐC TẾ", labels)

    def test_build_video_chapters_and_youtube_description(self):
        scenes = [
            DailyNewsScene(scene_index=0, text="Mở đầu", duration_ms=14000, start_time_ms=0, topic_block="intro"),
            DailyNewsScene(scene_index=1, text="Tin 1", duration_ms=35000, start_time_ms=14000, topic_block="world"),
            DailyNewsScene(scene_index=2, text="Tin 2", duration_ms=40000, start_time_ms=49000, topic_block="war"),
            DailyNewsScene(scene_index=3, text="Tin 3", duration_ms=30000, start_time_ms=89000, topic_block="sports"),
        ]
        chapters = build_video_chapters(scenes, category="tin_moi")
        self.assertEqual(len(chapters), 4)
        self.assertEqual(chapters[0]["timestamp"], "00:00")
        self.assertEqual(chapters[0]["title"], "Điểm tin mở đầu")
        self.assertEqual(chapters[1]["timestamp"], "00:14")
        self.assertEqual(chapters[1]["title"], "Thời sự & Kinh tế Thế giới")
        self.assertEqual(chapters[2]["timestamp"], "00:49")
        self.assertEqual(chapters[2]["title"], "Điểm nóng Chiến sự & An ninh")
        self.assertEqual(chapters[3]["timestamp"], "01:29")
        self.assertEqual(chapters[3]["title"], "Thể thao & Sân cỏ Quốc tế")

        desc = format_youtube_description_with_sources(
            {
                "title": "Bản Tin Nóng",
                "summary": "Tóm tắt bản tin",
                "aspect_ratio": "16:9",
                "chapters": chapters,
                "sources": [{"title": "BBC News", "source": "BBC"}],
            }
        )
        self.assertIn("⏱️ PHÂN ĐOẠN BẢN TIN (CHAPTERS):", desc)
        self.assertIn("00:00 Điểm tin mở đầu", desc)
        self.assertIn("00:14 Thời sự & Kinh tế Thế giới", desc)
        self.assertIn("00:49 Điểm nóng Chiến sự & An ninh", desc)
        self.assertIn("01:29 Thể thao & Sân cỏ Quốc tế", desc)


if __name__ == "__main__":
    unittest.main()
