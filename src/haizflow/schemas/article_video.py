"""Data contracts and schemas for Article-to-Video generation."""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


ARTICLE_VIDEO_SCHEMA_VERSION = 1

ImageStyle = Literal[
    "anime_2d",
    "manhwa_webtoon",
    "watercolor",
    "cyberpunk",
    "comic_book",
    "cinematic",
]

VoiceProvider = Literal[
    "vieneu",
    "vieneu-gpu",
    "edge",
    "omnivoice",
]

AspectRatio = Literal["16:9", "9:16", "1:1"]


class CharacterPreset(BaseModel):
    """A consistent 2D character definition with prompt anchoring."""

    id: str = Field(description="Unique character identifier, e.g. 'char_nam_hoc_sinh'")
    display_name: str = Field(description="Human readable name, e.g. 'Minh Triết - Nam sinh 17 tuổi'")
    gender: Literal["male", "female", "other"] = "male"
    age_group: str = Field(default="teenager", description="e.g. child, teenager, young_adult, elderly")
    thumbnail: str = Field(default="", description="Path or relative URI to preview avatar")
    style_tag: str = Field(default="anime_2d", description="Primary visual style compatibility")
    prompt_anchor: str = Field(
        description="Core immutable visual descriptors injected into generation prompts"
    )
    reference_images: List[str] = Field(
        default_factory=list,
        description="Optional paths to frontal, 3/4 angle reference portraits"
    )
    description: str = Field(default="", description="Personality or background notes")


class CharacterCatalog(BaseModel):
    """Container for the bundled and user-added character asset library."""

    schema_version: int = Field(default=1)
    characters: List[CharacterPreset] = Field(default_factory=list)


class ArticleScene(BaseModel):
    """An individual narration segment paired with its visual depiction."""

    scene_index: int = Field(ge=0)
    text: str = Field(description="Clean narration text for TTS synthesis")
    visual_priority_score: float = Field(
        default=5.0,
        ge=0.0,
        le=10.0,
        description="Heuristic or LLM score reflecting dramatic/visual importance"
    )
    has_image: bool = Field(
        default=False,
        description="Whether this scene triggers a new illustration image"
    )
    image_prompt: str = Field(
        default="",
        description="English visual prompt optimized for image generation"
    )
    character_id: Optional[str] = Field(
        default=None,
        description="Character preset ID active in this scene, if any"
    )
    image_path: str = Field(
        default="",
        description="Local path to the downloaded or cached scene illustration"
    )
    audio_path: str = Field(
        default="",
        description="Local path to the synthesized narration audio clip"
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Playback duration of the scene audio in milliseconds"
    )
    start_time_ms: int = Field(
        default=0,
        ge=0,
        description="Timeline offset of this scene in milliseconds"
    )
    has_transition_cue: bool = Field(
        default=False,
        description="Whether to play a transition sound effect/cue at the start of this scene"
    )
    chapter_label: str = Field(
        default="",
        description="Optional chapter / topic section badge for this scene (e.g. 'THỜI SỰ THẾ GIỚI')"
    )


class ArticleProjectConfig(BaseModel):
    """User configuration for converting an article into a full video."""

    article_text: str = Field(default="", description="Full source text of the article")
    voice_provider: VoiceProvider = "edge"
    voice_id: str = Field(default="vi-VN-NamMinhNeural", description="Identifier of the TTS voice")
    voice_rate: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech rate multiplier")
    voice_pitch: float = Field(default=0.0, ge=-20.0, le=20.0, description="Pitch offset in semitones")
    image_style: ImageStyle = "anime_2d"
    character_id: Optional[str] = Field(
        default=None,
        description="Active 2D character ID from the catalog"
    )
    image_count_target: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Target number of distinct illustrations to generate"
    )
    aspect_ratio: AspectRatio = "16:9"
    background_music_path: str = Field(default="", description="Optional path to background music")
    background_music_volume: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="BGM volume level (0.0 - 1.0)"
    )
    subtitle_enabled: bool = Field(default=True, description="Render on-screen subtitles")
    subtitle_font_family: str = Field(default="Bangers", description="Font name for subtitles")
    subtitle_font_size: int = Field(default=52, ge=12, le=200)
    branding_enabled: bool = Field(
        default=False,
        description="Overlay the channel logo (top-left) and a faint watermark on every slide",
    )
    ticker_text: str = Field(
        default="",
        description="Scrolling news ticker text (items separated by ' | '); empty disables the ticker",
    )
    ticker_label: str = Field(default="TIN MỚI", description="Fixed badge text at the left of the ticker bar")
    category: str = Field(default="", description="News category tag, e.g. 'world', 'war', 'tech', 'sports', 'viral'")


class ArticleVideoProject(BaseModel):
    """Persisted project model for an article-to-video production."""

    schema_version: int = Field(default=ARTICLE_VIDEO_SCHEMA_VERSION)
    project_id: str = Field(description="Immutable UUID or project slug")
    project_name: str = Field(default="Untitled Article Video")
    config: ArticleProjectConfig = Field(default_factory=ArticleProjectConfig)
    scenes: List[ArticleScene] = Field(default_factory=list)
    status: Literal["draft", "analyzed", "audio_ready", "images_ready", "rendered", "failed"] = "draft"
    total_duration_ms: int = Field(default=0, ge=0)
    created_at: str = Field(default="")
    updated_at: str = Field(default="")
    error_message: str = Field(default="")
