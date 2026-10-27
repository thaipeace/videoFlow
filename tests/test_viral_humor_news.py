import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from haizflow.services.daily_news import (
    WorldNewsItem,
    is_low_novelty_viral_news,
    calculate_viral_novelty_score,
    cluster_and_rank_news_topics,
    is_vietnam_related,
)


class ViralHumorAndNoveltyTests(unittest.TestCase):
    def test_low_novelty_filtering(self):
        # Mundane / low-novelty items should be flagged
        self.assertTrue(is_low_novelty_viral_news("Michigan woman turns birthday money into $150,000 lottery prize"))
        self.assertTrue(is_low_novelty_viral_news("Rare 1943 bronze penny sells for record $200,000 at auction"))
        self.assertTrue(is_low_novelty_viral_news("Study finds drinking 3 cups of coffee daily improves morning alertness"))
        self.assertTrue(is_low_novelty_viral_news("Flight to Dallas delayed by 40 minutes due to paperwork issue"))

        # Genuinely bizarre or hilarious items should NOT be flagged
        self.assertFalse(is_low_novelty_viral_news("Watch: Escaped cow runs onto Maryland highway, blocks traffic"))
        self.assertFalse(is_low_novelty_viral_news("Canadian Man Learns The Hard Way Why You Shouldn't Steal Flamingos When Drunk"))
        self.assertFalse(is_low_novelty_viral_news("Hilarious animal photos from this year's Comedy Wildlife Awards"))
        self.assertFalse(is_low_novelty_viral_news("Clumsy burglar gets stuck upside down in bakery chimney and calls police"))
        self.assertFalse(is_low_novelty_viral_news("Surreal glowing purple atmospheric cloud baffles scientists in Norway"))

    def test_viral_novelty_scoring(self):
        # Low novelty gets negative score
        low_item = WorldNewsItem(
            title="Michigan woman turns birthday money into $150,000 lottery prize",
            summary="She bought a scratch-off ticket.",
            source="UPI",
            published="Today",
            link="https://upi.com",
        )
        self.assertLess(calculate_viral_novelty_score(low_item), 0)

        # High humor story gets high positive score
        humor_item = WorldNewsItem(
            title="Hilarious animal antics: cheeky monkey steals tourist phone and takes selfies",
            summary="A funny monkey caused laughing fits after an epic fail theft in Bali.",
            source="Reddit r/funny",
            published="Today",
            link="https://reddit.com",
            social_platform="reddit",
        )
        self.assertGreaterEqual(calculate_viral_novelty_score(humor_item), 30)

        # High bizarre story gets high positive score
        bizarre_item = WorldNewsItem(
            title="Bizarre unexplainable glowing phenomenon lights up Siberian sky at midnight",
            summary="Mysterious creature sightings and a deep sinkhole baffle local residents.",
            source="X Trending",
            published="Today",
            link="https://x.com",
            social_platform="x",
        )
        self.assertGreaterEqual(calculate_viral_novelty_score(bizarre_item), 30)

    def test_cluster_and_rank_viral_prioritizes_humor_and_bizarre_over_fluff(self):
        items = [
            WorldNewsItem(
                title="Rare stamp sells for $5,000 at stamp collector auction house",
                summary="A collector auction in Ohio sold an old stamp.",
                source="Auction News",
                published="Today",
                link="https://news.com/1",
            ),
            WorldNewsItem(
                title="Clumsy thief falls through bakery ceiling and calls emergency hotline for rescue",
                summary="A hilarious botched heist left the suspect hanging upside down.",
                source="UPI Odd News",
                published="Today",
                link="https://news.com/2",
            ),
            WorldNewsItem(
                title="Bizarre alien-like deep sea creature with glowing tentacles discovered off coast of Japan",
                summary="Marine biologists recorded an unbelievable mysterious organism.",
                source="Reddit",
                published="Today",
                link="https://news.com/3",
            ),
            WorldNewsItem(
                title="Study reveals adults sleep better with room temperature at 20 degrees",
                summary="Researchers survey 500 people about sleep patterns.",
                source="Survey News",
                published="Today",
                link="https://news.com/4",
            ),
        ]

        ranked = cluster_and_rank_news_topics(items, max_topics=2, category="viral")
        self.assertEqual(len(ranked), 2)
        # The 2 top ranked items must be the hilarious thief and the bizarre deep sea creature
        top_titles = [it.title for it in ranked]
        self.assertTrue(any("Clumsy thief" in t for t in top_titles))
        self.assertTrue(any("Bizarre alien-like" in t for t in top_titles))
        self.assertFalse(any("Rare stamp" in t for t in top_titles))
        self.assertFalse(any("Study reveals" in t for t in top_titles))

    def test_strict_vietnam_exclusion_rule(self):
        # Verify 0% Vietnam content is strictly maintained
        self.assertTrue(is_vietnam_related("Chuyện lạ tại Hà Nội sáng nay"))
        self.assertTrue(is_vietnam_related("Funny monkey steals fruit in Ho Chi Minh City"))
        self.assertTrue(is_vietnam_related("Clip hài hước của du khách tại Đà Nẵng Việt Nam"))
        self.assertFalse(is_vietnam_related("Hilarious animal antics in California"))
        self.assertFalse(is_vietnam_related("Clumsy thief in London arrested after epic fail"))

    def test_viral_image_acquisition_uses_direct_photo_or_ai_prompt(self):
        from unittest.mock import patch, MagicMock
        from haizflow.services.daily_news import acquire_images_for_scenes, DailyNewsScene

        scenes = [
            DailyNewsScene(
                scene_index=0,
                text="Chú bò tẩu thoát náo loạn đường cao tốc",
                ai_prompt="escaped cow running on highway",
                image_url="https://example.com/real_cow.jpg",
                social_platform="x",
            ),
            DailyNewsScene(
                scene_index=1,
                text="Nghệ sĩ tạo quái vật từ rác thải",
                ai_prompt="giant 3-meter monster made of recycled junk",
                image_url="",
                social_platform="instagram",
            ),
        ]

        out_dir = Path("runtime/temp_test_viral_acq")
        out_dir.mkdir(parents=True, exist_ok=True)

        def fake_download(url, dest, aspect_ratio="9:16"):
            dest = Path(dest)
            dest.write_bytes(b"dummy image data")
            return True

        def fake_social(platform, headline, image_path=None, dest_path=Path("."), aspect_ratio="9:16"):
            dest_path = Path(dest_path)
            dest_path.write_bytes(b"dummy card")
            return dest_path

        def fake_ai(prompt, destination_path, aspect_ratio="9:16", style="cinematic", allow_free_online=True):
            destination_path = Path(destination_path)
            destination_path.write_bytes(b"dummy ai image")
            return destination_path

        with patch("haizflow.services.daily_news.download_and_format_image", side_effect=fake_download) as mock_dl, \
             patch("haizflow.services.daily_news.generate_scene_image", side_effect=fake_ai) as mock_ai, \
             patch("haizflow.services.daily_news.search_wikimedia_commons") as mock_wiki, \
             patch("haizflow.services.daily_news.create_social_post_visual", side_effect=fake_social) as mock_social, \
             patch("haizflow.services.daily_news.is_image_mostly_blank", return_value=False):

            acquire_images_for_scenes(scenes, out_dir, category="viral")

            # Verify Wikimedia was NEVER queried for viral news
            mock_wiki.assert_not_called()

            # Verify scene 0 used direct article photo
            self.assertEqual(scenes[0].image_source_type, "direct_photo")

            # Verify scene 1 (no image_url) called AI generation with its ai_prompt
            mock_ai.assert_called()
            self.assertEqual(scenes[1].image_source_type, "ai_generated")

        # Cleanup
        if out_dir.exists():
            import shutil
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_core_visual_subject_grounding(self):
        from haizflow.services.daily_news import extract_core_visual_subject, ground_prompt_to_core_subject

        # 1. Animal on highway: Must focus on the animal (cow), NOT on Maryland
        cow_subject = extract_core_visual_subject("Watch: Escaped cow runs onto Maryland highway, blocks traffic")
        self.assertIn("cow", cow_subject.lower())
        self.assertNotIn("maryland", cow_subject.lower())

        # 2. Ground prompt removes standalone Maryland so image generator won't draw Mary
        raw_prompt = "Escaped cow on Maryland highway with police cars"
        grounded = ground_prompt_to_core_subject(raw_prompt, fallback_headline="Escaped cow in Maryland")
        self.assertIn("cow", grounded.lower())
        self.assertNotIn("maryland", grounded.lower())

        # 3. Accidental Vietnamese prompt gets scrubbed and replaced with grounded English subject
        vi_prompt = "cinematic photo of viral breaking sensation: Con bò trốn thoát chạy vào đường cao tốc Maryland, cản trở giao thông"
        grounded_vi = ground_prompt_to_core_subject(vi_prompt, fallback_headline="Escaped cow runs onto Maryland highway")
        self.assertIn("cow", grounded_vi.lower())
        self.assertFalse(any(c in grounded_vi for c in "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"))

        # 4. Frog collection story
        frog_subject = extract_core_visual_subject("California Woman Sets Guinness World Record for Largest Collection of Frog Memorabilia")
        self.assertIn("frog", frog_subject.lower())

    def test_editorial_proof_of_work_generation(self):
        from haizflow.services.daily_news import (
            safe_script_filename,
            generate_editorial_proof_of_work_text,
            export_editorial_script_file,
            get_editorial_scripts_dir,
        )

        # 1. Test safe_script_filename
        fn = safe_script_filename(
            title="Đảo Riêng 22 Mẫu Anh Giá Chỉ 995.000 USD Tại Mỹ #Shorts",
            category="viral",
            created_at="2026-10-24T06:30:00Z",
            digest_id="f72c3a49",
        )
        self.assertTrue(fn.startswith("2026-10-24_viral_"))
        self.assertTrue(fn.endswith("_f72c3a49.txt"))
        self.assertIn("Dao_Rieng", fn)

        # 2. Test generate_editorial_proof_of_work_text
        mock_manifest = {
            "title": "Kỷ lục thế giới mới tại Nhật Bản",
            "category": "viral",
            "category_label": "Tin Lạ & Hài",
            "aspect_ratio": "9:16",
            "created_at": "2026-10-24T07:00:00Z",
            "summary": "Một kỷ lục thế giới vừa được xác lập tại Tokyo.",
            "thumbnail_hook": "KỶ LỤC THẾ GIỚI MỚI?",
            "ticker_summary": "Tokyo xác lập kỷ lục thế giới mới | Du khách thích thú",
            "hashtags": "#Shorts #tokyo #guinness",
            "sources": ["UPI Odd News", "Japan Today"],
            "source_items": [
                {
                    "title": "New record set in Tokyo",
                    "source": "Japan Today",
                    "link": "https://japantoday.com/record",
                    "published": "2026-10-24",
                }
            ],
            "script_scenes": [
                {
                    "scene_index": 0,
                    "text": "Một kỷ lục Guinness vừa chính thức được công nhận tại Nhật Bản!",
                    "entity": "Guinness world record Tokyo Japan",
                    "image_source": "social_screenshot",
                    "transition_cue": False,
                },
                {
                    "scene_index": 1,
                    "text": "Hàng ngàn người dân đã tập trung tại quảng trường Shibuya để theo dõi sự kiện.",
                    "entity": "Shibuya crossing crowd event",
                    "image_source": "social_screenshot",
                    "transition_cue": True,
                },
            ],
        }

        doc = generate_editorial_proof_of_work_text(mock_manifest)
        self.assertIn("EDITORIAL PROOF OF WORK", doc)
        self.assertIn("Kỷ lục thế giới mới tại Nhật Bản", doc)
        self.assertIn("https://japantoday.com/record", doc)
        self.assertIn("Một kỷ lục Guinness vừa chính thức được công nhận tại Nhật Bản!", doc)
        self.assertIn("TOÀN VĂN KỊCH BẢN LỜI THOẠI BIÊN TẬP", doc)
        self.assertIn("BẢNG PHÂN CẢNH SẢN XUẤT CHI TIẾT", doc)
        self.assertIn("CAM KẾT BIÊN TẬP & BẢN QUYỀN SẢN XUẤT", doc)

        # 3. Test export_editorial_script_file
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir)
            central_file = export_editorial_script_file(mock_manifest, output_dir=out_path)
            self.assertTrue(central_file.is_file())
            self.assertTrue((out_path / "script_raw.txt").is_file())
            self.assertIn("Shibuya", (out_path / "script_raw.txt").read_text(encoding="utf-8"))
            central_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
