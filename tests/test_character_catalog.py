"""Unit tests for CharacterCatalog service."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from haizflow.schemas.article_video import CharacterPreset
from haizflow.services import character_catalog


class TestCharacterCatalog(unittest.TestCase):
    def test_load_bundled_characters(self):
        characters = character_catalog.load_bundled_characters()
        self.assertGreaterEqual(len(characters), 3)

        ids = [c.id for c in characters]
        self.assertIn("char_my_dung", ids)
        self.assertIn("char_ba_hanh", ids)
        self.assertIn("char_nguoi_ao_den", ids)

        # Check prompt anchor presence and model sheet references
        for c in characters:
            self.assertTrue(len(c.prompt_anchor) > 10)
            self.assertTrue(bool(c.display_name))
            self.assertTrue(bool(c.thumbnail))
            self.assertTrue(Path(c.thumbnail).is_file())

    def test_get_character_by_id(self):
        char = character_catalog.get_character_by_id("char_my_dung")
        self.assertIsNotNone(char)
        self.assertEqual(char.id, "char_my_dung")
        self.assertEqual(char.gender, "female")
        self.assertIn("Mỹ Dung", char.display_name)

        missing = character_catalog.get_character_by_id("non_existent_id")
        self.assertIsNone(missing)

    def test_custom_character_add_and_delete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch("haizflow.services.character_catalog.runtime_data_dir", return_value=temp_path):
                custom = CharacterPreset(
                    id="char_custom_alien",
                    display_name="Alien X - Người ngoài hành tinh",
                    gender="other",
                    age_group="young_adult",
                    style_tag="cyberpunk",
                    prompt_anchor="futuristic green alien with glowing purple eyes and sleek armor",
                )
                added = character_catalog.add_custom_character(custom)
                self.assertEqual(added.id, "char_custom_alien")

                # Verify presence in list
                all_chars = character_catalog.list_characters()
                self.assertIn("char_custom_alien", [c.id for c in all_chars])

                # Disallow overwriting bundled
                with self.assertRaises(ValueError):
                    character_catalog.add_custom_character(
                        CharacterPreset(
                            id="char_my_dung",
                            display_name="Hacked",
                            gender="female",
                            prompt_anchor="none",
                        )
                    )

                # Delete custom
                deleted = character_catalog.delete_custom_character("char_custom_alien")
                self.assertTrue(deleted)
                all_chars_after = character_catalog.list_characters()
                self.assertNotIn("char_custom_alien", [c.id for c in all_chars_after])

    def test_reset_custom_characters(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch("haizflow.services.character_catalog.runtime_data_dir", return_value=temp_path):
                custom = CharacterPreset(
                    id="char_custom_temp",
                    display_name="Temp Character",
                    gender="other",
                    age_group="young_adult",
                    style_tag="cinematic",
                    prompt_anchor="temp prompt",
                )
                character_catalog.add_custom_character(custom)
                self.assertEqual(len(character_catalog.load_custom_characters()), 1)

                character_catalog.reset_custom_characters()
                self.assertEqual(len(character_catalog.load_custom_characters()), 0)

    def test_delete_bundled_and_all_characters(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch("haizflow.services.character_catalog.runtime_data_dir", return_value=temp_path):
                # Verify bundled are initially present
                initial = character_catalog.list_characters()
                self.assertIn("char_my_dung", [c.id for c in initial])

                # Delete bundled character
                deleted = character_catalog.delete_character("char_my_dung")
                self.assertTrue(deleted)
                after_one = character_catalog.list_characters()
                self.assertNotIn("char_my_dung", [c.id for c in after_one])
                self.assertIsNone(character_catalog.get_character_by_id("char_my_dung"))

                # Delete all characters
                character_catalog.delete_all_characters()
                self.assertEqual(len(character_catalog.list_characters()), 0)

                # Restore bundled characters
                character_catalog.restore_bundled_characters()
                restored = character_catalog.list_characters()
                self.assertIn("char_my_dung", [c.id for c in restored])
                self.assertIn("char_ba_hanh", [c.id for c in restored])


if __name__ == "__main__":
    unittest.main()
