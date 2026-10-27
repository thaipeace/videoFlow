"""Unit tests for StoryDirector service."""

import json
import unittest
from unittest.mock import MagicMock, patch

from haizflow.schemas.article_video import ArticleProjectConfig, ArticleScene
from haizflow.services import story_director


class TestStoryDirector(unittest.TestCase):
    def setUp(self):
        self.sample_text = (
            "Ngày xửa ngày xưa, tại một ngôi làng ven biển xinh đẹp, có một cậu bé tên là Minh Triết. "
            "Cậu luôn mơ ước được trở thành một nhà thám hiểm tài ba và đi khắp năm châu bốn biển. "
            "Một buổi chiều nọ, khi đang đi dạo trên bờ cát vàng, cậu bỗng nhìn thấy một chiếc chai thủy tinh phát sáng. "
            "Bên trong chiếc chai là một bức thư cổ với những ký tự vô cùng kỳ lạ. "
            "Minh Triết hồi hộp mở chiếc chai ra và cuộc hành trình kỳ thú chính thức bắt đầu từ đây."
        )

    def test_segment_text_into_paragraphs(self):
        segments = story_director.segment_text_into_paragraphs(self.sample_text, target_words_per_segment=25)
        self.assertGreaterEqual(len(segments), 2)
        # Verify text completeness
        joined = " ".join(segments)
        self.assertIn("Minh Triết", joined)
        self.assertIn("thủy tinh phát sáng", joined)

    def test_heuristic_visual_priority(self):
        score_first = story_director.heuristic_visual_priority("Mở đầu câu chuyện.", 0, 5)
        self.assertGreaterEqual(score_first, 8.0)

        score_action = story_director.heuristic_visual_priority("Cậu bé bỗng nhìn thấy ánh sáng rực rỡ và chạy thật nhanh.", 2, 5)
        self.assertGreater(score_action, 5.0)

    def test_distribute_image_allocations_default_one_image(self):
        scenes = [
            ArticleScene(scene_index=0, text="Mở đầu", visual_priority_score=8.5),
            ArticleScene(scene_index=1, text="Đoạn văn bình thường", visual_priority_score=5.0),
            ArticleScene(scene_index=2, text="Đoạn cao trào", visual_priority_score=9.2),
            ArticleScene(scene_index=3, text="Kết thúc", visual_priority_score=7.0),
        ]
        story_director.distribute_image_allocations(scenes, target_count=1)

        allocated = [s for s in scenes if s.has_image]
        self.assertEqual(len(allocated), 1)
        self.assertEqual(allocated[0].scene_index, 2)  # 9.2 was highest score

    def test_distribute_image_allocations_multiple_images(self):
        scenes = [
            ArticleScene(scene_index=i, text=f"Scene {i}", visual_priority_score=float(i % 5 + 5))
            for i in range(10)
        ]
        story_director.distribute_image_allocations(scenes, target_count=3)

        allocated = [s for s in scenes if s.has_image]
        self.assertEqual(len(allocated), 3)

    def test_build_scene_prompt_with_character(self):
        prompt = story_director.build_scene_prompt(
            scene_text="Mỹ Dung đứng trước hành lang bệnh viện u ám",
            image_style="cinematic",
            character_id="char_my_dung",
        )
        self.assertIn("cinematic film still", prompt)
        self.assertIn("My Dung", prompt)
        self.assertIn("Vietnamese young woman", prompt)
        self.assertIn("depicting:", prompt)

    def test_build_scene_prompt_free_mode_no_character(self):
        prompt = story_director.build_scene_prompt(
            scene_text="Một cậu bé thám hiểm bước vào khu rừng thần tiên đầy hoa phát sáng",
            image_style="cinematic",
            character_id="none",
        )
        self.assertIn("cinematic film still", prompt)
        self.assertIn("depicting:", prompt)
        self.assertNotIn("featuring", prompt)
        self.assertNotIn("My Dung", prompt)
        self.assertNotIn("Vietnamese young woman named My Dung", prompt)
        self.assertNotIn("mole", prompt)

    def test_analyze_article_offline_end_to_end(self):
        config = ArticleProjectConfig(
            article_text=self.sample_text,
            image_style="cinematic",
            character_id="char_my_dung",
            image_count_target=2,
        )
        scenes = story_director.analyze_article_offline(config)
        self.assertGreaterEqual(len(scenes), 2)

        images_count = sum(1 for s in scenes if s.has_image)
        self.assertEqual(images_count, 2)

        for scene in scenes:
            if scene.has_image:
                self.assertTrue(len(scene.image_prompt) > 20)
                self.assertIn("cinematic film still", scene.image_prompt)
                self.assertIn("My Dung", scene.image_prompt)

    @patch("haizflow.services.story_director.urlopen")
    def test_analyze_article_with_gemini_mock(self, mock_urlopen):
        mock_response = MagicMock()
        fake_gemini_json = [
            {
                "text": "Minh Triết đi dạo trên bờ biển chiều tà.",
                "visual_priority_score": 8.5,
                "english_scene_desc": "young Vietnamese boy walking along sunset beach, glowing ocean waves",
            },
            {
                "text": "Cậu phát hiện một chiếc chai thủy tinh bí ẩn.",
                "visual_priority_score": 9.5,
                "english_scene_desc": "holding a mystical glowing glass bottle with an ancient parchment inside",
            },
        ]
        gemini_wrapper = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(fake_gemini_json)}]
                    }
                }
            ]
        }
        mock_response.read.return_value = json.dumps(gemini_wrapper).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        config = ArticleProjectConfig(
            article_text=self.sample_text,
            image_style="manhwa_webtoon",
            character_id="char_nam_hoc_sinh",
            image_count_target=1,
        )
        scenes = story_director.analyze_article_with_gemini(config, api_key="fake-gemini-key")
        # Verify 100% of story sentences are preserved (5 scenes, not shortened)
        self.assertEqual(len(scenes), 5)
        allocated = [s for s in scenes if s.has_image]
        self.assertEqual(len(allocated), 1)
        self.assertTrue(len(allocated[0].image_prompt) > 0)


if __name__ == "__main__":
    unittest.main()
