"""Unit tests for football news image verification and Vietnamese name pronunciation normalization."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from haizflow.pipeline.pronunciation import normalize_vietnamese_pronunciation
from haizflow.pipeline.tts import preprocess_text_for_tts
from haizflow.services.daily_news import (
    search_wikimedia_commons,
    extract_search_keywords_from_headline,
    prepare_scene_illustrations,
    DailyNewsScene,
)


class TestFootballPronunciation(unittest.TestCase):
    def test_football_superstars_pronunciation(self):
        text = "Kylian Mbappé và Erling Haaland so tài cùng Jude Bellingham và Vinicius Junior."
        norm = normalize_vietnamese_pronunciation(text)
        self.assertIn("Ki-li-an Em-báp-pê", norm)
        self.assertIn("Ơ-ling Ha-lân", norm)
        self.assertIn("Giu Bét-ling-hem", norm)
        self.assertIn("Vi-ni-xi-út Giu-ni-o", norm)

    def test_football_clubs_and_tournaments(self):
        text = "Real Madrid đối đầu Arsenal tại Champions League, trong khi Man City thống trị Premier League."
        norm = normalize_vietnamese_pronunciation(text)
        self.assertIn("Rê-an Ma-đrít", norm)
        self.assertIn("Át-sê-nan", norm)
        self.assertIn("Cúp C1", norm)
        self.assertIn("Man Xi-ti", norm)
        self.assertIn("Ngoại Hạng Anh", norm)

    def test_football_managers(self):
        text = "HLV Mikel Arteta khen ngợi chiến thuật của Pep Guardiola và Carlo Ancelotti."
        norm = normalize_vietnamese_pronunciation(text)
        self.assertIn("Mi-ken A-tê-ta", norm)
        self.assertIn("Pép Goác-đi-ô-la", norm)
        self.assertIn("Các-lô An-xê-lốt-ti", norm)

    def test_var_and_ballon_dor(self):
        text = "Quyết định từ VAR gây tranh cãi trước thềm lễ trao giải Ballon d'Or."
        norm = normalize_vietnamese_pronunciation(text)
        self.assertIn("Vê-A-Rờ", norm)
        self.assertIn("Quả Bóng Vàng", norm)

    def test_tts_preprocessor_integrates_pronunciation(self):
        raw = "  Tiền đạo Kylian Mbappé khoác áo Real Madrid.  "
        processed = preprocess_text_for_tts(raw, target_language="vi")
        self.assertEqual(processed, "Tiền đạo Ki-li-an Em-báp-pê khoác áo Rê-an Ma-đrít.")


class TestFootballImageVerification(unittest.TestCase):
    def test_reject_metaphor_and_toxic_queries(self):
        bad_queries = [
            "witch-hunt tactics against manager",
            "mafia boss influence",
            "Catholic saint church cathedral",
            "saint",
            "doctor hospital patient surgery",
        ]
        for query in bad_queries:
            title, url = search_wikimedia_commons(query, category="sports")
            self.assertIsNone(title, f"Expected '{query}' to be rejected, but got '{title}'")
            self.assertIsNone(url)

    def test_extract_keywords_from_headline_prioritizes_football(self):
        headline = "Mikel Arteta laughs off witch-hunt accusations as Arsenal beat Chelsea"
        extracted = extract_search_keywords_from_headline(headline, category="sports")
        self.assertNotIn("witch", extracted.lower())
        self.assertIn("football", extracted.lower())

    def test_prepare_illustrations_sports_fallback_prompt(self):
        scene = DailyNewsScene(
            scene_index=0,
            text="Trận thư hùng kịch tính trên sân cỏ châu Âu kết thúc với tỷ số hòa.",
            entity_query="witch-hunt tactics",  # should be rejected and fall back
            ai_prompt="",
            has_transition_cue=False,
        )
        # Verify entity_query is rejected
        title, url = search_wikimedia_commons(scene.entity_query, category="sports")
        self.assertIsNone(title)
        self.assertIsNone(url)


if __name__ == "__main__":
    unittest.main()
