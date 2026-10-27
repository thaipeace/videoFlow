"""Unit tests verifying the Supreme Law: 0% Vietnam content across all news categories."""

import unittest
from haizflow.services.daily_news import (
    CATEGORY_CONFIG,
    is_vietnam_related,
    assert_and_sanitize_no_vietnam_content,
    get_mock_news_items,
    DailyNewsDigest,
    DailyNewsScene,
)


class TestVietnamExclusionSupremeLaw(unittest.TestCase):
    def test_all_category_personas_mandate_supreme_law(self):
        """Every category persona must strictly prohibit Vietnam content."""
        for cat, cfg in CATEGORY_CONFIG.items():
            persona = cfg.get("persona", "")
            self.assertIn(
                "LUẬT TỐI THƯỢNG",
                persona,
                f"Category '{cat}' persona is missing explicit 'LUẬT TỐI THƯỢNG' clause!",
            )
            self.assertIn(
                "VIỆT NAM",
                persona.upper(),
                f"Category '{cat}' persona does not explicitly ban Vietnam content!",
            )

    def test_is_vietnam_related_flags_vietnam_terms(self):
        """is_vietnam_related must catch direct and indirect Vietnam references."""
        violating_samples = [
            "Tin tức mới từ Việt Nam hôm nay",
            "Vietnam reports GDP growth for the third quarter",
            "Chuyến thăm chính thức Hà Nội của phái đoàn quốc tế",
            "Đoàn xe di chuyển qua trung tâm TP.HCM rạng sáng nay",
            "Bạo loạn tại Sai Gon gây tắc nghẽn",
            "Hội nghị thượng đỉnh tổ chức tại Đà Nẵng",
            "Đội tuyển Việt Nam giành chiến thắng kịch tính",
            "Giải bóng đá V-League bước vào vòng đấu cuối",
            "Giá xe VinFast tăng nhẹ trên thị trường quốc tế",
            "Ngân hàng Vietcombank công bố chính sách tín dụng mới",
            "Tỷ giá 500.000 VND quy đổi sang USD",
            "Bản tin phát trên kênh VTV rạng sáng nay",
            "Theo ghi nhận từ báo VnExpress hôm nay",
            "Cuộc họp báo của Bộ Ngoại giao Việt Nam",
        ]
        for sample in violating_samples:
            self.assertTrue(
                is_vietnam_related(sample),
                f"Failed to flag Vietnam-related content: '{sample}'",
            )

    def test_is_vietnam_related_no_false_positives_on_international_words(self):
        """Ensure no false positives on legitimate international names or words."""
        safe_samples = [
            "Diplomats meet in Vienna to discuss nuclear treaty",
            "Apple announces quarterly dividend of 25 cents per share",
            "Defense forces respond to missile attacks across the border",
            "Advanced cryptography hardware unveiled at Tokyo expo",
            "Ukrainian armored division repels mechanized assault near Kharkiv",
            "Real Madrid defeats Bayern Munich in Champions League semifinal",
            "President Emmanuel Macron addresses French parliament in Paris",
            "Rare geomagnetic aurora illuminates skies across Northern Norway",
        ]
        for sample in safe_samples:
            self.assertFalse(
                is_vietnam_related(sample),
                f"False positive flagged on safe international content: '{sample}'",
            )

    def test_assert_and_sanitize_no_vietnam_content(self):
        """Sanitizer must scrub or drop any Vietnam references from title, summary, scenes, and ticker."""
        digest = DailyNewsDigest(
            digest_id="test1234",
            title="Xung Đột Biên Giới và Bài Học Cho Việt Nam",
            summary_lead="Tổng hợp tin tức chiến sự và phản ứng từ Hà Nội.",
            hashtags="#news",
            thumbnail_hook="VIỆT NAM CẢNH BÁO",
            ticker_summary="Kharkiv giao tranh dữ dội | Giá vàng tại Việt Nam tăng mạnh | Gaza không kích",
            scenes=[
                DailyNewsScene(
                    scene_index=0,
                    text="Một đợt không kích lớn vừa diễn ra, cùng điểm qua những tin tức đáng chú ý tại Việt Nam và thế giới.",
                    entity_query="Vietnam news",
                    ai_prompt="cinematic studio",
                ),
                DailyNewsScene(
                    scene_index=1,
                    text="Giao tranh ác liệt bùng phát tại khu vực Kharkiv với hơn 30 xe bọc thép bị phá hủy.",
                    entity_query="Kharkiv battle tank",
                    ai_prompt="cinematic tank battle",
                ),
                DailyNewsScene(
                    scene_index=2,
                    text="Tại Hà Nội, các chuyên gia quân sự Việt Nam đưa ra phân tích sâu sắc về trận địa.",
                    entity_query="Hanoi defense meeting",
                    ai_prompt="generals in Hanoi",
                ),
                DailyNewsScene(
                    scene_index=3,
                    text="Bản tin thời sự thế giới hôm nay xin được khép lại tại đây. Đừng quên bấm đăng ký kênh.",
                    entity_query="Studio desk",
                    ai_prompt="cinematic newsroom",
                ),
            ],
        )

        sanitized = assert_and_sanitize_no_vietnam_content(digest)

        # Title, hook, summary, ticker must have 0 Vietnam references
        self.assertFalse(is_vietnam_related(sanitized.title))
        self.assertFalse(is_vietnam_related(sanitized.summary_lead))
        self.assertFalse(is_vietnam_related(sanitized.thumbnail_hook))
        self.assertFalse(is_vietnam_related(sanitized.ticker_summary))

        # Scene 2 (purely about Hanoi/Vietnam) must be dropped
        self.assertEqual(len(sanitized.scenes), 3)
        for sc in sanitized.scenes:
            self.assertFalse(
                is_vietnam_related(sc.text),
                f"Scene text still contains Vietnam reference: {sc.text}",
            )
            self.assertFalse(
                is_vietnam_related(sc.entity_query),
                f"Scene entity_query still contains Vietnam reference: {sc.entity_query}",
            )

    def test_all_mock_news_items_have_zero_vietnam_content(self):
        """Every single mock item across all categories must be 100% international."""
        categories = ["world", "tech", "sports", "war", "viral"]
        for cat in categories:
            items = get_mock_news_items(cat)
            self.assertTrue(len(items) >= 4, f"Category '{cat}' should have at least 4 mock items.")
            for item in items:
                self.assertFalse(
                    is_vietnam_related(item.title),
                    f"Mock item title in '{cat}' violates Supreme Law: '{item.title}'",
                )
                self.assertFalse(
                    is_vietnam_related(item.summary),
                    f"Mock item summary in '{cat}' violates Supreme Law: '{item.summary}'",
                )


if __name__ == "__main__":
    unittest.main()
