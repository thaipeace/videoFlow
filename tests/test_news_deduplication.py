"""Unit tests for the 7-day persistent deduplication history and Shorts Top 3 enhancements."""

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from haizflow.services.daily_news import (
    WorldNewsItem,
    _extract_title_tokens,
    _normalize_title_for_dedup,
    is_duplicate_with_published_history,
    is_within_time_window,
    load_published_news_history,
    record_published_news_history,
    save_published_news_history,
)


class TestNewsDeduplication(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_dedup_"))
        self._orig_runtime = None

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_title_for_dedup(self):
        t1 = "Breaking: Chinese neighbours go viral over 200-year land dispute dating back to Qianlong era - SCMP"
        t2 = "Watch: Chinese neighbours go viral over 200-year land dispute dating back to Qianlong era!"
        self.assertEqual(_normalize_title_for_dedup(t1), _normalize_title_for_dedup(t2))

    def test_extract_title_tokens(self):
        t = "A simple liquid can stop cavities without drilling, major study confirms"
        tokens = _extract_title_tokens(t)
        self.assertIn("simple", tokens)
        self.assertIn("liquid", tokens)
        self.assertIn("cavities", tokens)
        self.assertIn("drilling", tokens)
        self.assertNotIn("with", tokens)  # stopword

    def test_is_duplicate_exact_and_normalized(self):
        history = [
            {
                "title": "Chinese neighbours go viral over 200-year land dispute dating back to Qianlong era - South China Morning Post",
                "normalized_title": _normalize_title_for_dedup("Chinese neighbours go viral over 200-year land dispute dating back to Qianlong era - South China Morning Post"),
                "link": "https://scmp.com/news/china/article123",
                "category": "viral",
                "timestamp": datetime.now().isoformat(),
            }
        ]

        # 1. Exact match
        self.assertTrue(is_duplicate_with_published_history(
            "Chinese neighbours go viral over 200-year land dispute dating back to Qianlong era - South China Morning Post",
            "https://scmp.com/news/china/article123",
            history,
        ))

        # 2. Same story from different URL and slight title variations
        self.assertTrue(is_duplicate_with_published_history(
            "Viral Chinese neighbours in 200-year Qianlong era land dispute",
            "https://anothernews.com/viral-land-dispute",
            history,
        ))

        # 3. URL match with query parameters stripped
        self.assertTrue(is_duplicate_with_published_history(
            "Completely different rewritten headline",
            "https://scmp.com/news/china/article123?oc=5&utm_source=rss",
            history,
        ))

        # 4. Completely different story
        self.assertFalse(is_duplicate_with_published_history(
            "NASA James Webb Space Telescope discovers water geysers on distant icy moon",
            "https://nasa.gov/news/webb-water-moon",
            history,
        ))

    def test_time_window_filtering_for_hope(self):
        now = datetime.now()
        # Item published 2 hours ago (valid)
        fresh_pub = (now - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertTrue(is_within_time_window(fresh_pub, export_dt=now, category="hope"))

        # Item published 30 hours ago (valid for 48h hope window)
        yesterday_pub = (now - timedelta(hours=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertTrue(is_within_time_window(yesterday_pub, export_dt=now, category="hope"))

        # Ancient item published 25 days ago (e.g. Florida coral reef paper from Oct 02) -> MUST BE REJECTED
        ancient_pub = (now - timedelta(days=25)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertFalse(is_within_time_window(ancient_pub, export_dt=now, category="hope"))

    def test_time_window_filtering_for_viral(self):
        now = datetime.now()
        # Item published 3 hours ago -> valid
        fresh_pub = (now - timedelta(hours=3)).strftime("%a, %d %b %Y %H:%M:%S")
        self.assertTrue(is_within_time_window(fresh_pub, export_dt=now, category="viral"))

        # Item published 5 days ago -> invalid for viral
        old_pub = (now - timedelta(days=5)).strftime("%a, %d %b %Y %H:%M:%S")
        self.assertFalse(is_within_time_window(old_pub, export_dt=now, category="viral"))

    def test_save_and_load_published_history_lifecycle(self):
        import haizflow.services.daily_news as dn
        old_runtime = dn.runtime_data_dir

        def mock_runtime():
            return self.temp_dir

        dn.runtime_data_dir = mock_runtime
        try:
            # 1. Initial load should be empty in clean temp dir
            history = load_published_news_history()
            self.assertEqual(len(history), 0)

            # 2. Record new items
            items = [
                WorldNewsItem(
                    title="A simple liquid can stop cavities without drilling, major study confirms",
                    summary="Test summary",
                    source="ScienceDaily",
                    published="Today",
                    link="https://sciencedaily.com/dentistry",
                ),
                WorldNewsItem(
                    title="New research identifies exact spot where Alzheimer protein tangles lock in",
                    summary="Test summary 2",
                    source="Optimist Daily",
                    published="Today",
                    link="https://optimistdaily.com/alzheimer",
                ),
            ]
            record_published_news_history(items, "hope")

            # 3. Verify history reloads with these items (permanent retention: max_age_days=None)
            reloaded = load_published_news_history(max_age_days=None)
            self.assertEqual(len(reloaded), 2)
            titles = [it["title"] for it in reloaded]
            self.assertIn(items[0].title, titles)
            self.assertIn(items[1].title, titles)

            # 4. Duplicate check should detect them
            self.assertTrue(is_duplicate_with_published_history(
                "A simple liquid can stop cavities without drilling",
                "https://sciencedaily.com/dentistry",
                reloaded,
            ))
        finally:
            dn.runtime_data_dir = old_runtime

    def test_single_standout_story_ranking(self):
        from haizflow.services.daily_news import cluster_and_rank_news_topics
        items = [
            WorldNewsItem(
                title="Ordinary cat sleeps on chair in local office",
                summary="Normal office cat naps during working hours.",
                source="Daily Local",
                published="Today",
                link="https://example.com/cat1",
            ),
            WorldNewsItem(
                title="Bizarre modified motorcycle takes a 25-mile drive on open ocean water",
                summary="An unbelievable and bizarre feat of amphibious vehicle engineering.",
                source="UPI Odd News",
                published="Today",
                link="https://example.com/bike-water",
            ),
        ]
        # For viral with max_topics = 1, should pick the highest novelty item
        top1 = cluster_and_rank_news_topics(items, max_topics=1, category="viral")
        self.assertEqual(len(top1), 1)
        self.assertIn("motorcycle", top1[0].title.lower())

    def test_single_story_fallback_script_duration_and_wordcount(self):
        from haizflow.services.daily_news import fallback_offline_news_script
        items = [
            WorldNewsItem(
                title="Modified motorcycle takes a 25-mile drive on water",
                summary="A stuntman built an amphibious motorcycle and drove it twenty-five miles across the ocean waters.",
                source="UPI Odd News",
                published="Today",
                link="https://example.com/bike-water",
            ),
        ]
        digest = fallback_offline_news_script(items, max_topics=1, category="viral")
        self.assertEqual(len(digest.scenes), 3)
        total_words = sum(len(sc.text.split()) for sc in digest.scenes)
        # Total words must be strictly <= 60 words so speech duration is under 25 seconds
        self.assertLessEqual(total_words, 60)
        self.assertGreaterEqual(total_words, 35)


if __name__ == "__main__":
    unittest.main()
