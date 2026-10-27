"""Unit tests for 'Tin vui' (hope) - scientific breakthroughs, inventions, and future solutions news."""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from haizflow.services.daily_news import (
    CATEGORY_CONFIG,
    HOPE_RSS_FEEDS,
    WorldNewsItem,
    calculate_hope_score,
    cluster_and_rank_news_topics,
    fallback_offline_news_script,
    export_editorial_script_file,
    get_mock_news_items,
    normalize_category,
)


class TestHopeGoodNews(unittest.TestCase):
    def test_normalize_category_hope_aliases(self):
        aliases = ["hope", "tinvui", "tin_vui", "goodnews", "good_news", "sangche", "phatminh", "hyvong", "hy_vong", "khoahoc_hyvong"]
        for alias in aliases:
            self.assertEqual(normalize_category(alias), "hope")

    def test_category_config_hope(self):
        self.assertIn("hope", CATEGORY_CONFIG)
        cfg = CATEGORY_CONFIG["hope"]
        self.assertEqual(cfg["label"], "Tin vui")
        self.assertEqual(cfg["file_prefix"], "hope_shorts")
        self.assertEqual(cfg["default_aspect_ratio"], "9:16")
        self.assertGreaterEqual(len(HOPE_RSS_FEEDS), 8)

    def test_calculate_hope_score(self):
        high_item = WorldNewsItem(
            title="Scientists discover cancer cure breakthrough and clean energy battery that saves planet",
            summary="Groundbreaking clinical trial shows complete remission and new green solar solution restoring Earth.",
            source="Good News Network",
            link="https://goodnewsnetwork.org/test-high",
            published="Today",
        )
        low_item = WorldNewsItem(
            title="Random stock price changes in automotive sector",
            summary="A short quarterly earnings overview.",
            source="Reuters",
            link="https://reuters.com/test-low",
            published="Today",
        )
        score_high = calculate_hope_score(high_item)
        score_low = calculate_hope_score(low_item)
        self.assertGreater(score_high, score_low)

    def test_hope_subtopic_detection_and_weighted_ranking(self):
        from haizflow.services.daily_news import detect_hope_subtopic

        med_item = WorldNewsItem(
            title="Landmark clinical trial achieves 90 percent remission in aggressive pediatric leukemia using mRNA therapy",
            summary="Cancer doctors announce breakthrough in curing tumors with targeted gene therapy saving young patients.",
            source="ScienceDaily Health",
            link="https://sciencedaily.com/health/cancer",
            published="Today",
        )
        life_item = WorldNewsItem(
            title="Endangered sea turtle population rebounds fourfold following coral reef sanctuary protection",
            summary="Marine biologists document extraordinary wildlife recovery and biodiversity resurgence.",
            source="Good News Network",
            link="https://goodnewsnetwork.org/wildlife",
            published="Today",
        )
        env_item = WorldNewsItem(
            title="Solar powered ocean barrier intercepts tons of plastic waste restoring river and clean water",
            summary="Environmental initiative marks milestone in ecological restoration and clean drinking water.",
            source="Optimist Daily",
            link="https://optimistdaily.com/ocean",
            published="Today",
        )
        other_tech_item = WorldNewsItem(
            title="Engineers design innovative robotic arm gadget and prototype for consumer manufacturing",
            summary="A neat invention milestone in materials science and robotics.",
            source="New Atlas",
            link="https://newatlas.com/tech",
            published="Today",
        )

        # 1. Verify subtopic detection
        self.assertEqual(detect_hope_subtopic(med_item), "medical")
        self.assertEqual(detect_hope_subtopic(life_item), "life")
        self.assertEqual(detect_hope_subtopic(env_item), "environment")
        self.assertEqual(detect_hope_subtopic(other_tech_item), "other")

        # 2. Verify score weights: medical, life & environment score significantly higher than other tech
        med_score = calculate_hope_score(med_item)
        life_score = calculate_hope_score(life_item)
        env_score = calculate_hope_score(env_item)
        other_score = calculate_hope_score(other_tech_item)

        self.assertGreater(med_score, other_score * 1.5)
        self.assertGreater(life_score, other_score * 1.3)
        self.assertGreater(env_score, other_score * 1.3)
        # Other tech is still positive (usable)
        self.assertGreater(other_score, 12.0)

    def test_mock_items_hope(self):
        mocks = get_mock_news_items("hope")
        self.assertGreaterEqual(len(mocks), 5)
        for it in mocks:
            self.assertIn("http", it.link)
            self.assertTrue(len(it.title) > 10)

    def test_cluster_and_rank_hope(self):
        mocks = get_mock_news_items("hope")
        clusters = cluster_and_rank_news_topics(mocks, max_topics=4, category="hope")
        self.assertLessEqual(len(clusters), 4)
        self.assertGreater(len(clusters), 0)

    def test_fallback_script_and_proof_of_work(self):
        mocks = get_mock_news_items("hope")
        script = fallback_offline_news_script(mocks[:5], category="hope")
        self.assertTrue("#Shorts" in script.title)
        self.assertGreater(len(script.scenes), 0)

        # Check export editorial proof of work
        manifest = {
            "title": script.title,
            "category": "hope",
            "created_at": "2026-10-24T07:30:00",
            "scenes": [
                {"text": s.text, "duration_ms": s.duration_ms, "image_path": s.image_path}
                for s in script.scenes
            ],
        }
        proof_path = export_editorial_script_file(manifest, news_items=mocks[:5])
        self.assertTrue(proof_path.exists())
        self.assertGreater(proof_path.stat().st_size, 500)
        content = proof_path.read_text(encoding="utf-8")
        self.assertIn("Tin vui", content)
        self.assertIn("HỒ SƠ BIÊN TẬP", content)


if __name__ == "__main__":
    unittest.main()
