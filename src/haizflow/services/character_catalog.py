"""Service for discovering, loading, and managing 2D character presets."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from haizflow.core.paths import package_root, runtime_data_dir
from haizflow.schemas.article_video import CharacterCatalog, CharacterPreset

logger = logging.getLogger(__name__)

_BUNDLED_CHARACTERS_DIR = package_root() / "desktop" / "assets" / "characters"
_CATALOG_FILENAME = "catalog.json"
_CUSTOM_CHARACTERS_FILENAME = "custom_characters.json"
_DELETED_CHARACTERS_FILENAME = "deleted_character_ids.json"


def bundled_characters_directory() -> Path:
    """Return the absolute path to the bundled character assets."""
    return _BUNDLED_CHARACTERS_DIR


def custom_characters_path() -> Path:
    """Return the storage path for user-added custom characters."""
    directory = runtime_data_dir() / "characters"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _CUSTOM_CHARACTERS_FILENAME


def deleted_characters_path() -> Path:
    """Return storage path for deleted character identifiers."""
    directory = runtime_data_dir() / "characters"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _DELETED_CHARACTERS_FILENAME


def load_deleted_character_ids() -> set[str]:
    """Load the set of deleted character IDs."""
    path = deleted_characters_path()
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(data)
        return set()
    except Exception as exc:
        logger.warning("Could not read deleted characters: %s", exc)
        return set()


def save_deleted_character_ids(ids: set[str]) -> None:
    """Persist the set of deleted character IDs atomically."""
    path = deleted_characters_path()
    data = sorted(list(ids))
    content = json.dumps(data, indent=2, ensure_ascii=False)
    handle, temp_name = tempfile.mkstemp(
        prefix=".deleted-char-", suffix=".tmp", dir=path.parent
    )
    with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())
    os.replace(temp_name, path)


def resolve_character_avatar_path(thumbnail: str) -> Path:
    """Resolve a character avatar thumbnail to an absolute path on disk."""
    if not thumbnail:
        return Path("")
    candidate = Path(thumbnail)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    bundled_target = _BUNDLED_CHARACTERS_DIR / thumbnail
    if bundled_target.is_file():
        return bundled_target
    custom_target = runtime_data_dir() / "characters" / thumbnail
    if custom_target.is_file():
        return custom_target
    return bundled_target


def load_bundled_characters() -> List[CharacterPreset]:
    """Load the immutable character presets shipped with HaizFlow."""
    catalog_path = _BUNDLED_CHARACTERS_DIR / _CATALOG_FILENAME
    if not catalog_path.is_file():
        logger.warning("Bundled character catalog is missing: %s", catalog_path)
        return []
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog = CharacterCatalog.model_validate(data)
        for char in catalog.characters:
            if char.thumbnail:
                resolved = resolve_character_avatar_path(char.thumbnail)
                if resolved.is_file():
                    char.thumbnail = str(resolved)
        return catalog.characters
    except Exception as exc:
        logger.error("Failed to parse bundled character catalog: %s", exc)
        return []


def load_custom_characters() -> List[CharacterPreset]:
    """Load user-defined custom characters from runtime data."""
    path = custom_characters_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        catalog = CharacterCatalog.model_validate(data)
        for char in catalog.characters:
            if char.thumbnail:
                resolved = resolve_character_avatar_path(char.thumbnail)
                if resolved.is_file():
                    char.thumbnail = str(resolved)
        return catalog.characters
    except Exception as exc:
        logger.warning("Could not read custom characters: %s", exc)
        return []


def list_characters() -> List[CharacterPreset]:
    """Return all available characters (bundled first, then custom), excluding deleted ones."""
    deleted_ids = load_deleted_character_ids()
    bundled = [c for c in load_bundled_characters() if c.id not in deleted_ids]
    existing_ids = {c.id for c in bundled}
    custom_list = [c for c in load_custom_characters() if c.id not in deleted_ids]
    for custom_char in custom_list:
        if custom_char.id not in existing_ids:
            bundled.append(custom_char)
            existing_ids.add(custom_char.id)
    return bundled


def get_character_by_id(character_id: str) -> Optional[CharacterPreset]:
    """Retrieve a specific character preset by identifier."""
    if not character_id or character_id in ("none", ""):
        return None
    for char in list_characters():
        if char.id == character_id:
            return char
    return None


def add_custom_character(character: CharacterPreset) -> CharacterPreset:
    """Persist a new user-defined character into runtime storage."""
    target_path = custom_characters_path()
    custom_list = load_custom_characters()

    # Disallow overriding bundled IDs
    bundled_ids = {c.id for c in load_bundled_characters()}
    if character.id in bundled_ids:
        raise ValueError(f"Cannot overwrite bundled character ID '{character.id}'")

    # If it was previously marked deleted, un-delete it
    deleted_ids = load_deleted_character_ids()
    if character.id in deleted_ids:
        deleted_ids.remove(character.id)
        save_deleted_character_ids(deleted_ids)

    # Replace existing custom with same ID or append
    updated = [c for c in custom_list if c.id != character.id]
    updated.append(character)

    catalog = CharacterCatalog(schema_version=1, characters=updated)
    content = catalog.model_dump_json(indent=2)

    # Atomic write
    handle, temp_name = tempfile.mkstemp(
        prefix=".custom-char-", suffix=".tmp", dir=target_path.parent
    )
    with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())

    os.replace(temp_name, target_path)
    return character


def delete_custom_character(character_id: str) -> bool:
    """Delete a user-defined custom character by identifier."""
    target_path = custom_characters_path()
    if not target_path.is_file():
        return False
    custom_list = load_custom_characters()
    filtered = [c for c in custom_list if c.id != character_id]
    if len(filtered) == len(custom_list):
        return False

    catalog = CharacterCatalog(schema_version=1, characters=filtered)
    content = catalog.model_dump_json(indent=2)

    handle, temp_name = tempfile.mkstemp(
        prefix=".custom-char-", suffix=".tmp", dir=target_path.parent
    )
    with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())

    os.replace(temp_name, target_path)
    return True


def delete_character(character_id: str) -> bool:
    """Delete any character preset (bundled or custom) so it no longer appears in the catalog."""
    if not character_id or character_id in ("none", ""):
        return False

    delete_custom_character(character_id)

    deleted_ids = load_deleted_character_ids()
    deleted_ids.add(character_id)
    save_deleted_character_ids(deleted_ids)
    return True


def delete_all_characters() -> None:
    """Remove all characters (both custom and bundled) from the active catalog."""
    reset_custom_characters()
    bundled = load_bundled_characters()
    deleted_ids = {c.id for c in bundled}
    save_deleted_character_ids(deleted_ids)


def restore_bundled_characters() -> None:
    """Restore the default bundled canonical characters by clearing the deleted set."""
    path = deleted_characters_path()
    if path.is_file():
        try:
            path.unlink()
        except Exception as exc:
            logger.warning("Could not unlink deleted characters file: %s", exc)
            save_deleted_character_ids(set())


def reset_custom_characters() -> None:
    """Clear all custom characters and reset custom_characters.json to an empty list."""
    target_path = custom_characters_path()
    catalog = CharacterCatalog(schema_version=1, characters=[])
    content = catalog.model_dump_json(indent=2)

    handle, temp_name = tempfile.mkstemp(
        prefix=".custom-char-", suffix=".tmp", dir=target_path.parent
    )
    with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())

    os.replace(temp_name, target_path)

