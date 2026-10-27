"""Unit tests for Article-to-Video schemas."""

import unittest

from haizflow.schemas.article_video import (
    ARTICLE_VIDEO_SCHEMA_VERSION,
    ArticleProjectConfig,
    ArticleScene,
    ArticleVideoProject,
    CharacterCatalog,
    CharacterPreset,
)


class TestArticleVideoSchemas(unittest.TestCase):
    def test_character_preset_defaults_and_validation(self):
        char = CharacterPreset(
            id="char_test_1",
            display_name="Test Character",
            gender="male",
            prompt_anchor="young boy with brown hair and blue eyes",
        )
        self.assertEqual(char.id, "char_test_1")
        self.assertEqual(char.gender, "male")
        self.assertEqual(char.style_tag, "anime_2d")
        self.assertEqual(char.age_group, "teenager")

        # Serialization & roundtrip
        json_data = char.model_dump_json()
        restored = CharacterPreset.model_validate_json(json_data)
        self.assertEqual(restored.id, char.id)
        self.assertEqual(restored.prompt_anchor, char.prompt_anchor)

    def test_article_scene_defaults(self):
        scene = ArticleScene(scene_index=0, text="Hôm nay là một ngày đẹp trời.")
        self.assertEqual(scene.scene_index, 0)
        self.assertEqual(scene.visual_priority_score, 5.0)
        self.assertFalse(scene.has_image)
        self.assertEqual(scene.image_prompt, "")
        self.assertEqual(scene.duration_ms, 0)

    def test_article_project_config_defaults(self):
        config = ArticleProjectConfig(article_text="Nội dung bài viết mẫu.")
        self.assertEqual(config.voice_provider, "edge")
        self.assertEqual(config.voice_id, "vi-VN-NamMinhNeural")
        self.assertEqual(config.image_style, "anime_2d")
        self.assertEqual(config.image_count_target, 1)
        self.assertEqual(config.aspect_ratio, "16:9")
        self.assertTrue(config.subtitle_enabled)

    def test_article_video_project_lifecycle(self):
        config = ArticleProjectConfig(
            article_text="Đoạn văn thứ nhất. Đoạn văn thứ hai.",
            image_count_target=2,
            image_style="manhwa_webtoon",
        )
        project = ArticleVideoProject(
            project_id="proj_art_123",
            project_name="Dự án Video Đọc Truyện",
            config=config,
            scenes=[
                ArticleScene(scene_index=0, text="Đoạn văn thứ nhất.", has_image=True),
                ArticleScene(scene_index=1, text="Đoạn văn thứ hai.", has_image=True),
            ],
            status="analyzed",
        )
        self.assertEqual(project.schema_version, ARTICLE_VIDEO_SCHEMA_VERSION)
        self.assertEqual(len(project.scenes), 2)
        self.assertTrue(project.scenes[0].has_image)

        # JSON Roundtrip
        dumped = project.model_dump_json()
        reloaded = ArticleVideoProject.model_validate_json(dumped)
        self.assertEqual(reloaded.project_id, "proj_art_123")
        self.assertEqual(reloaded.config.image_style, "manhwa_webtoon")
        self.assertEqual(len(reloaded.scenes), 2)


if __name__ == "__main__":
    unittest.main()
