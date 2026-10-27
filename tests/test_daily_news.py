"""Unit tests for the Daily World News video automation service."""

import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from haizflow.services.daily_news import (
    clean_html_text,
    is_vietnam_related,
    DailyNewsScene,
    DailyNewsDigest,
    WorldNewsItem,
    fallback_offline_news_script,
    normalize_english_journalism,
    normalize_vietnamese_journalism,
    cluster_and_rank_news_topics,
    format_source_attribution_lead_in,
    normalize_category,
    get_category_config,
    get_mock_news_items,
    TECH_RSS_FEEDS,
    SPORTS_RSS_FEEDS,
    WORLD_RSS_FEEDS,
    format_youtube_description_with_sources,
)


class TestDailyNewsService(unittest.TestCase):
    def test_is_vietnam_related_detection(self):
        # Must detect Vietnam related terms
        self.assertTrue(is_vietnam_related("Chính phủ Việt Nam ban hành nghị định mới"))
        self.assertTrue(is_vietnam_related("Economic boom in Hanoi and Saigon"))
        self.assertTrue(is_vietnam_related("Vietnam leads renewable energy surge"))

        # Must allow pure international news
        self.assertFalse(is_vietnam_related("Macron visits Berlin for European defense summit"))
        self.assertFalse(is_vietnam_related("Wall Street indexes jump after tech earnings rally"))
        self.assertFalse(is_vietnam_related("NASA confirms water vapor detected on exoplanet"))

    def test_clean_html_text(self):
        raw = "<p>Breaking news: &quot;Major breakthrough&quot; in <b>AI</b> research.</p>"
        cleaned = clean_html_text(raw)
        self.assertEqual(cleaned, 'Breaking news: "Major breakthrough" in AI research.')

    def test_fallback_offline_news_script(self):
        sample_items = [
            WorldNewsItem(
                title="Global summit addresses climate crisis",
                summary="World leaders met in Geneva today.",
                source="Reuters",
                published="Today",
                link="https://reuters.com",
            ),
        ]
        digest = fallback_offline_news_script(sample_items)
        self.assertIsInstance(digest, DailyNewsDigest)
        self.assertGreaterEqual(len(digest.scenes), 2)
        self.assertTrue(digest.title)
        self.assertIn("#", digest.hashtags)

    def test_normalize_english_journalism(self):
        raw = "Ukraine and Russia exchange strikes in deadly drone strikes on energy grid"
        normalized = normalize_english_journalism(raw)
        self.assertIn("exchange military attacks", normalized)
        self.assertIn("drone attacks", normalized)
        self.assertNotIn("exchange strikes", normalized)

    def test_normalize_vietnamese_journalism(self):
        # Must eliminate mistranslation of strikes -> đình công in military context
        bad_vi = "Ukraine và Nga trao đổi đình công trong các cuộc đình công bằng máy bay không người lái của Nga"
        normalized = normalize_vietnamese_journalism(bad_vi)
        self.assertNotIn("đình công", normalized)
        self.assertIn("tập kích", normalized)

        # Must normalize legislative and crime terminology
        bad_terms = "Nhà lập pháp bị thương trong vụ đâm xe cố ý"
        norm_terms = normalize_vietnamese_journalism(bad_terms)
        self.assertIn("Nghị sĩ", norm_terms)
        self.assertIn("vụ cố ý lao xe tấn công", norm_terms)

    def test_cluster_and_rank_news_topics(self):
        items = [
            WorldNewsItem(
                title="Australian MP Helen Haines in critical condition after car ramming",
                summary="Lawmaker injured outside office.",
                source="Đài phát thanh NPR",
                published="Today",
                link="https://npr.org/1",
                full_text="Police confirmed the arrest of a 34-year-old suspect.",
            ),
            WorldNewsItem(
                title="Helen Haines: Australian independent MP critically hurt in hit-and-run",
                summary="Emergency security called.",
                source="báo The Guardian",
                published="Today",
                link="https://guardian.com/2",
                full_text="Prime Minister called for immediate review of parliament safety.",
            ),
            WorldNewsItem(
                title="Super Typhoon Champi intensifies to Category 5 storm",
                summary="Storm tracks toward Pacific.",
                source="hãng tin Al Jazeera",
                published="Today",
                link="https://aljazeera.com/3",
                full_text="Sustained winds reached 165 mph.",
            ),
        ]

        clusters = cluster_and_rank_news_topics(items, max_topics=8)
        # 3 raw items must cluster into 2 distinct topics (2 Helen Haines items merged into 1)
        self.assertEqual(len(clusters), 2)

        # The Helen Haines cluster should merge sources and full text
        haines_topic = next(c for c in clusters if "Haines" in c.title or "Haines" in c.full_text)
        self.assertIn("Đài phát thanh NPR", haines_topic.source)
        self.assertIn("The Guardian", haines_topic.source)
        self.assertIn("34-year-old", haines_topic.full_text)
        self.assertIn("Prime Minister", haines_topic.full_text)

    def test_format_source_attribution_lead_in(self):
        source = "báo The Guardian"
        # Must rotate and produce varied, natural phrases requested by user
        lead_0 = format_source_attribution_lead_in(source, 0)
        lead_1 = format_source_attribution_lead_in(source, 1)
        lead_2 = format_source_attribution_lead_in(source, 2)

        self.assertEqual(lead_0, "Theo báo The Guardian, ")
        self.assertEqual(lead_1, "Báo The Guardian có viết, ")
        self.assertEqual(lead_2, "The Guardian cho hay, ")

        # Must never return the static repetitive phrase
        for i in range(8):
            lead = format_source_attribution_lead_in(source, i)
            self.assertNotIn("Theo ghi nhận từ", lead)

    def test_scene_transition_cues(self):
        items = [
            WorldNewsItem(
                title="Event A headline",
                summary="Details A",
                source="Reuters",
                published="Today",
                link="https://1",
            ),
            WorldNewsItem(
                title="Event B headline",
                summary="Details B",
                source="AFP",
                published="Today",
                link="https://2",
            ),
        ]
        digest = fallback_offline_news_script(items, detail_level="standard", max_topics=2)
        # Expected:
        # Scene 0: Intro (False)
        # Scene 1: Event A start (True)
        # Scene 2: Event A details (False)
        # Scene 3: Event B start (True - cue when starting new item!)
        # Scene 4: Event B details (False)
        # Scene 5: Outro (True - cue before closing!)
        self.assertFalse(digest.scenes[0].has_transition_cue)
        self.assertTrue(digest.scenes[1].has_transition_cue)
        self.assertFalse(digest.scenes[2].has_transition_cue)
        self.assertTrue(digest.scenes[3].has_transition_cue)
        self.assertFalse(digest.scenes[4].has_transition_cue)
        self.assertTrue(digest.scenes[-1].has_transition_cue)

    def test_broadcast_transition_sound_cue_and_subtitle_sync(self):
        import tempfile
        import wave
        import struct
        import math
        from haizflow.pipeline.slide_composer import (
            generate_news_transition_sting,
            export_subtitles_to_srt,
            ArticleScene,
        )

        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            sting_path = temp_dir / "test_sting.wav"
            generate_news_transition_sting(sting_path)

            self.assertTrue(sting_path.is_file())
            self.assertGreater(sting_path.stat().st_size, 10000)

            # Verify audio amplitude: must be loud and punchy for TV news
            with wave.open(str(sting_path), "rb") as w:
                self.assertEqual(w.getframerate(), 48000)
                nframes = w.getnframes()
                samples = struct.unpack(f"<{nframes}h", w.readframes(nframes))
                peak = max(abs(s) for s in samples)
                rms = math.sqrt(sum(s * s for s in samples) / len(samples))
                # Peak must be high broadcast level (> 20000 out of 32767)
                self.assertGreater(peak, 20000)
                # RMS must be solid (> 3000)
                self.assertGreater(rms, 3000)

            # Test subtitle sync: scene with transition cue starts 450ms later
            scenes = [
                ArticleScene(scene_index=0, text="Intro", duration_ms=3000, start_time_ms=0, has_transition_cue=False),
                ArticleScene(scene_index=1, text="News 1", duration_ms=4000, start_time_ms=3000, has_transition_cue=True),
            ]
            srt_path = temp_dir / "sub.srt"
            export_subtitles_to_srt(scenes, srt_path)
            srt_content = srt_path.read_text(encoding="utf-8")
            # Scene 0 starts at 00:00:00,000
            self.assertIn("00:00:00,000 --> 00:00:03,000", srt_content)
            # Scene 1 starts delayed by 450ms -> 3000 + 450 = 3450ms (00:00:03,450)
            self.assertIn("00:00:03,450 --> 00:00:07,000", srt_content)

    def test_news_bgm_generation(self):
        import wave
        from haizflow.pipeline.slide_composer import get_or_generate_news_bgm

        bgm_path = get_or_generate_news_bgm()
        self.assertTrue(bgm_path.is_file())
        self.assertGreater(bgm_path.stat().st_size, 100000)

        with wave.open(str(bgm_path), "rb") as w:
            self.assertEqual(w.getframerate(), 48000)
            dur = w.getnframes() / w.getframerate()
            self.assertGreaterEqual(dur, 10.0)

    def test_category_normalization(self):
        """Verify normalization of category aliases."""
        self.assertEqual(normalize_category("tin_moi"), "tin_moi")
        self.assertEqual(normalize_category("morning"), "tin_moi")
        self.assertEqual(normalize_category("world_sports"), "tin_moi")
        self.assertEqual(normalize_category("tin_nong"), "tin_nong")
        self.assertEqual(normalize_category("evening"), "tin_nong")
        self.assertEqual(normalize_category("war_tech"), "tin_nong")
        self.assertEqual(normalize_category("world"), "world")
        self.assertEqual(normalize_category("thoisu"), "world")
        self.assertEqual(normalize_category("tech"), "tech")
        self.assertEqual(normalize_category("congnghe"), "tech")
        self.assertEqual(normalize_category("technology"), "tech")
        self.assertEqual(normalize_category("sports"), "sports")
        self.assertEqual(normalize_category("thethao"), "sports")
        self.assertEqual(normalize_category("viral"), "viral")
        self.assertEqual(normalize_category("tinla"), "viral")
        self.assertEqual(normalize_category("docla"), "viral")
        self.assertEqual(normalize_category("shorts"), "viral")
        self.assertEqual(normalize_category("unknown_xyz"), "tin_moi")

    def test_category_configs(self):
        """Verify feeds and titles configured for each category."""
        tin_moi_cfg = get_category_config("tin_moi")
        self.assertEqual(tin_moi_cfg["label"], "Tin Mới")
        self.assertEqual(tin_moi_cfg["default_aspect_ratio"], "16:9")
        self.assertIn("Tin Mới", tin_moi_cfg["title_prefix"])
        self.assertIn("#thethao", tin_moi_cfg["hashtags"])

        tin_nong_cfg = get_category_config("tin_nong")
        self.assertEqual(tin_nong_cfg["label"], "Tin Nóng")
        self.assertEqual(tin_nong_cfg["default_aspect_ratio"], "16:9")
        self.assertIn("Tin Nóng", tin_nong_cfg["title_prefix"])
        self.assertIn("#chiensu", tin_nong_cfg["hashtags"])

        world_cfg = get_category_config("world")
        self.assertEqual(world_cfg["label"], "Thời sự")
        self.assertIn("feeds.npr.org", "".join(world_cfg["feeds"]))

        tech_cfg = get_category_config("tech")
        self.assertEqual(tech_cfg["label"], "Công nghệ")
        self.assertIn("theverge.com", "".join(tech_cfg["feeds"]))
        self.assertIn("#congnghe", tech_cfg["hashtags"])
        self.assertIn("Công Nghệ", tech_cfg["title_prefix"])

        sports_cfg = get_category_config("sports")
        self.assertEqual(sports_cfg["label"], "Bóng đá")
        self.assertIn("bbci.co.uk/sport/football", "".join(sports_cfg["feeds"]))
        self.assertIn("#bongda", sports_cfg["hashtags"])
        self.assertIn("Bóng Đá", sports_cfg["title_prefix"])

        viral_cfg = get_category_config("viral")
        self.assertEqual(viral_cfg["label"], "Tin lạ & Hài")
        self.assertEqual(viral_cfg["default_aspect_ratio"], "9:16")
        self.assertIn("#Shorts", viral_cfg["hashtags"])
        self.assertIn("Tin Nóng & Độc Lạ Thế Giới", viral_cfg["title_prefix"])

    def test_tech_and_sports_mock_items(self):
        """Verify mock items generation for tech, sports, viral, tin_moi, and tin_nong."""
        tin_moi_items = get_mock_news_items("tin_moi")
        self.assertEqual(len(tin_moi_items), 8)

        tin_nong_items = get_mock_news_items("tin_nong")
        self.assertEqual(len(tin_nong_items), 8)

        tech_items = get_mock_news_items("tech")
        self.assertEqual(len(tech_items), 8)
        self.assertTrue(any("Nvidia" in it.title or "AI" in it.title or "SpaceX" in it.title for it in tech_items))

        sports_items = get_mock_news_items("sports")
        self.assertEqual(len(sports_items), 8)
        self.assertTrue(any("Madrid" in it.title or "Mbappe" in it.title or "Haaland" in it.title for it in sports_items))

        viral_items = get_mock_news_items("viral")
        self.assertEqual(len(viral_items), 5)
        self.assertTrue(all(it.social_platform in ("x", "instagram", "facebook", "reddit", "tiktok", "threads") for it in viral_items))

        world_items = get_mock_news_items("world")
        self.assertEqual(len(world_items), 8)

    def test_category_fallback_scripts(self):
        """Verify fallback offline script adapts correctly to category."""
        tech_items = get_mock_news_items("tech")[:2]
        tech_digest = fallback_offline_news_script(tech_items, category="tech")
        self.assertIn("Công Nghệ", tech_digest.title)
        self.assertIn("#congnghe", tech_digest.hashtags)
        self.assertIn("công nghệ", tech_digest.scenes[0].text.lower())

        sports_items = get_mock_news_items("sports")[:2]
        sports_digest = fallback_offline_news_script(sports_items, category="sports")
        self.assertIn("Bóng Đá", sports_digest.title)
        self.assertIn("#bongda", sports_digest.hashtags)
        self.assertIn("bóng đá", sports_digest.scenes[0].text.lower())

        viral_items = get_mock_news_items("viral")[:2]
        viral_digest = fallback_offline_news_script(viral_items, category="viral")
        self.assertIn("#Shorts", viral_digest.title)
        self.assertIn("#Shorts", viral_digest.hashtags)
        self.assertIn("độc lạ", viral_digest.scenes[0].text.lower())

    def test_viral_news_time_window(self):
        """Verify time window from export time back to 6:30 AM yesterday."""
        from datetime import datetime
        from haizflow.services.daily_news import get_viral_news_time_window, is_within_time_window

        export_dt = datetime(2026, 10, 23, 14, 0, 0)
        start_dt, end_dt = get_viral_news_time_window(export_dt)
        self.assertGreaterEqual(end_dt, export_dt)
        self.assertEqual(start_dt, datetime(2026, 10, 22, 6, 30, 0))

        # Item within window (e.g. yesterday at 14:00)
        self.assertTrue(is_within_time_window("Thu, 22 Oct 2026 14:00:00 +0700", export_dt=export_dt))
        # Item before cutoff (e.g. yesterday at 03:00 AM local time)
        self.assertFalse(is_within_time_window("Thu, 22 Oct 2026 03:00:00 +0700", export_dt=export_dt))

    def test_create_social_post_visual(self):
        """Verify generation of 9:16 social screenshot visual."""
        import tempfile
        from haizflow.services.daily_news import create_social_post_visual
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_img = Path(tmp_dir) / "viral_card.jpg"
            create_social_post_visual(
                platform="instagram",
                headline="Bí ẩn hố phát sáng kỳ dị giữa bầu trời đêm gây sốt triệu view",
                dest_path=out_img,
                aspect_ratio="9:16",
            )
            self.assertTrue(out_img.is_file())
            with Image.open(out_img) as img:
                self.assertEqual(img.size, (1080, 1920))

    def test_format_youtube_description_video_all_sources(self):
        """Verify 100% of sources are included in YouTube description for landscape video."""
        items = [
            {"title": f"Tin thế giới số {i}", "source": f"Hãng tin {i}", "link": f"https://news{i}.org/article/{i}"}
            for i in range(1, 9)
        ]
        manifest = {
            "title": "Bản Tin Thời Sự Quốc Tế 25/10/2026",
            "summary": "Tổng hợp diễn biến nóng nhất từ khắp các châu lục trong 24 giờ qua.",
            "hashtags": "#tintucthegioi #thoisu24h #haizflow",
            "aspect_ratio": "16:9",
            "category": "world",
            "source_items": items,
        }

        desc = format_youtube_description_with_sources(manifest)

        # Must include all 8 sources and links
        for i in range(1, 9):
            self.assertIn(f"Hãng tin {i}", desc)
            self.assertIn(f"https://news{i}.org/article/{i}", desc)
            self.assertIn(f"Tin thế giới số {i}", desc)

        # Must have sources section header
        self.assertIn("NGUỒN TIN BÁO CHÍ THAM KHẢO (SOURCES):", desc)
        # Must strip #haizflow
        self.assertNotIn("haizflow", desc.lower())
        # Must have clean hashtags
        self.assertIn("#tintucthegioi", desc)

    def test_format_youtube_description_shorts_all_sources(self):
        """Verify 100% of sources are included in YouTube description for portrait Shorts."""
        items = [
            {"title": "Đột phá y khoa điều trị ung thư", "source": "ScienceDaily Health", "link": "https://sciencedaily.com/releases/2026/01.htm"},
            {"title": "Bảo tồn cá heo sông Mekong đạt kỳ tích", "source": "The Guardian Environment", "link": "https://theguardian.com/environment/2026/02"},
            {"title": "Phát hiện loài thực vật hấp thụ kim loại nặng", "source": "Reuters Science", "link": "https://reuters.com/science/plant-2026"},
        ]
        manifest = {
            "title": "Kỳ Tích Y Khoa Và Môi Trường - Bản Tin Hy Vọng 25/10/2026",
            "summary": "Những tin vui truyền cảm hứng về y tế, sự sống và thiên nhiên.",
            "hashtags": "#tinvui #ykhoa #hyvong #haizflow",
            "aspect_ratio": "9:16",
            "category": "hope",
            "source_items": items,
        }

        desc = format_youtube_description_with_sources(manifest)

        # Must include all 3 sources, titles and links
        for it in items:
            self.assertIn(it["source"], desc)
            self.assertIn(it["link"], desc)
            self.assertIn(it["title"], desc)

        # Must automatically include #Shorts in hashtags for vertical shorts
        self.assertIn("#Shorts", desc)
        # Must strip #haizflow
        self.assertNotIn("haizflow", desc.lower())

    def test_format_youtube_description_no_omissions_under_limit(self):
        """Verify that when description is very long, all sources are kept (0 omitted)."""
        items = [
            {
                "title": f"Tiêu đề bài viết rất dài và chi tiết về sự kiện thế giới số {i} với đầy đủ thông tin",
                "source": f"Hãng thông tấn quốc tế số {i}",
                "link": f"https://very-long-domain-name-international-news-agency.org/2026/10/25/breaking-news-article-slug-{i}",
            }
            for i in range(1, 21)
        ]
        manifest = {
            "title": "Bản Tin Thời Sự Quốc Tế Chi Tiết 25/10/2026",
            "summary": "Tóm tắt rất dài " * 50,  # ~800 chars summary
            "hashtags": "#tintucthegioi #thoisu #xuhuong",
            "aspect_ratio": "16:9",
            "category": "world",
            "source_items": items,
        }

        desc = format_youtube_description_with_sources(manifest, max_length=4900)

        # Must not exceed limit
        self.assertLessEqual(len(desc), 4900)

        # Must not omit any source - all 20 sources and links must be present!
        for i in range(1, 21):
            self.assertIn(f"Hãng thông tấn quốc tế số {i}", desc)
            self.assertIn(f"slug-{i}", desc)

    def test_format_youtube_description_sources_fallback(self):
        """Verify fallback when only manifest['sources'] list is available."""
        manifest = {
            "title": "Bản Tin Thời Sự",
            "summary": "Tóm tắt tin tức",
            "hashtags": "#thoisu",
            "sources": ["BBC News", "Reuters", "AP News"],
        }
        desc = format_youtube_description_with_sources(manifest)
        self.assertIn("BBC News", desc)
        self.assertIn("Reuters", desc)
        self.assertIn("AP News", desc)

    def test_placeholder_image_filtering(self):
        """Verify that Google placeholders and low-res icons are strictly rejected."""
        from haizflow.services.daily_news import is_placeholder_image_url, extract_image_from_html

        # Google placeholder images
        google_placeholder = "https://lh3.googleusercontent.com/J6_coFbogxhRI9iM864NL_liGXvsQp2AupsKei7z0cNNfDvGUmWUy20nuUhkREQyrpY4bEeIBuc=s0-w300-rw"
        self.assertTrue(is_placeholder_image_url(google_placeholder))
        self.assertTrue(is_placeholder_image_url("https://www.gstatic.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"))
        self.assertTrue(is_placeholder_image_url("https://news.google.com/static/placeholder.jpg"))
        self.assertTrue(is_placeholder_image_url("https://example.com/assets/default_image.png"))
        self.assertTrue(is_placeholder_image_url("https://example.com/images/favicon.ico"))

        # Legitimate news article photo
        real_photo = "https://images.wsj.net/im-123456?width=1280&size=1.7777777777777777"
        self.assertFalse(is_placeholder_image_url(real_photo))

        # HTML extraction with Google og:image must be rejected
        html_with_google = f'<html><head><meta property="og:image" content="{google_placeholder}"></head><body><p>Text</p></body></html>'
        extracted = extract_image_from_html(html_with_google)
        self.assertEqual(extracted, "")

        # HTML with real og:image must be accepted
        html_with_real = f'<html><head><meta property="og:image" content="{real_photo}"></head><body><p>Text</p></body></html>'
        extracted_real = extract_image_from_html(html_with_real)
        self.assertEqual(extracted_real, real_photo)

    def test_semantic_topic_matching_and_image_alignment(self):
        """Verify that scenes match the exact right news items and never drift sequentially."""
        from haizflow.services.daily_news import (
            clean_query_for_wikimedia,
            find_matching_news_item_for_scene,
            score_item_topic_match,
        )

        news_items = [
            WorldNewsItem(
                title="53 Orangutans Rescued from Fires in Borneo, With Many Rewilded to Forest Preserves",
                summary="Wildlife teams successfully rehabilitated 53 orangutans rescued from Kalimantan peat fires.",
                source="Good News Network",
                published="Today",
                link="https://goodnewsnetwork.org/orangutans",
                image_url="https://images.goodnewsnetwork.org/orangutan.jpg",
            ),
            WorldNewsItem(
                title="Geographic Focus Area Determination for Florida's Coral Reef Restoration & Recovery",
                summary="Marine biologists identified priority reef tracts across Florida keys.",
                source="Phys.org",
                published="Today",
                link="https://phys.org/coral",
                image_url="https://phys.org/coral.jpg",
            ),
            WorldNewsItem(
                title="A simple liquid can stop cavities without drilling, major clinical study confirms",
                summary="Silver diamine fluoride treatment arrests tooth decay painlessly in pediatric patients.",
                source="Medical News",
                published="Today",
                link="https://medicalnews.com/cavities",
                image_url="https://medicalnews.com/cavity.jpg",
            ),
        ]

        # 1. Scene about Cavities (Dentist) must match Item 2 (Cavities), NOT Item 0 (Orangutans)!
        matched_cavity = find_matching_news_item_for_scene(
            scene_text="Thử nghiệm lâm sàng xác nhận một loại chất lỏng đặc biệt có thể trị sâu răng trong vài giây không cần khoan.",
            scene_entity="dentist applying liquid to child teeth",
            scene_ai_prompt="cinematic photo of dental clinic and smiling child teeth",
            source_event_idx=3,
            news_items=news_items,
        )
        self.assertIsNotNone(matched_cavity)
        self.assertEqual(matched_cavity.image_url, "https://medicalnews.com/cavity.jpg")

        # 2. Scene about Orangutans must match Item 0 (Orangutans)
        matched_orangutan = find_matching_news_item_for_scene(
            scene_text="Kỳ tích tại Borneo khi 53 chú đười ươi được cứu thoát khỏi hỏa hoạn và tái thả về rừng.",
            scene_entity="orangutan rescue forest Borneo",
            scene_ai_prompt="cinematic photo of rescued orangutan climbing tree in jungle",
            source_event_idx=1,
            news_items=news_items,
        )
        self.assertIsNotNone(matched_orangutan)
        self.assertEqual(matched_orangutan.image_url, "https://images.goodnewsnetwork.org/orangutan.jpg")

        # 3. Generic outro scene must NOT match any article image (0% sequential drift)
        matched_outro = find_matching_news_item_for_scene(
            scene_text="Thế giới luôn tràn ngập những điều kỳ diệu và hy vọng. Hãy bấm đăng ký kênh để đón nhận nguồn năng lượng tích cực mỗi ngày!",
            scene_entity="beautiful sunrise nature hope",
            scene_ai_prompt="cinematic vertical 9:16 sunrise over thriving green planet Earth",
            source_event_idx=0,
            news_items=news_items,
        )
        self.assertIsNone(matched_outro)

        # 4. clean_query_for_wikimedia must strip sentiment fluff
        self.assertEqual(clean_query_for_wikimedia("beautiful sunrise nature hope"), "sunrise")
        self.assertIn("dentist", clean_query_for_wikimedia("dentist applying liquid to child teeth"))


if __name__ == "__main__":
    unittest.main()


