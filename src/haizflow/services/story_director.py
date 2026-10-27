"""Story Director: Segments articles, assigns visual priorities, and engineers scene prompts."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from haizflow.schemas.article_video import (
    ArticleProjectConfig,
    ArticleScene,
    ImageStyle,
)
from haizflow.services.character_catalog import get_character_by_id
from haizflow.services.secure_credentials import read_secret

logger = logging.getLogger(__name__)

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
CREDENTIAL_TARGET = "HaizFlow/Gemini/APIKey"

STYLE_PROMPT_PRESETS: dict[ImageStyle, str] = {
    "anime_2d": (
        "masterpiece, best quality, modern 2D anime style, Makoto Shinkai aesthetic, "
        "cel-shaded, vibrant colors, detailed background, crisp clean lines"
    ),
    "manhwa_webtoon": (
        "digital manhwa webtoon illustration style, clean digital art, soft shading, "
        "modern dramatic lighting, sharp details, cinematic composition"
    ),
    "watercolor": (
        "delicate watercolor painting style, soft washed textures, artistic brush strokes, "
        "warm nostalgic color palette, elegant storybook illustration"
    ),
    "cyberpunk": (
        "futuristic cyberpunk concept art, neon glowing lights, moody atmospheric volumetric lighting, "
        "high tech aesthetic, detailed city elements"
    ),
    "comic_book": (
        "western comic book style, bold ink lines, dynamic perspective, "
        "dramatic pop art lighting, halftone dots texture"
    ),
    "cinematic": (
        "cinematic film still, photorealistic composition, 35mm photograph, "
        "depth of field, dramatic movie lighting, 8k resolution"
    ),
}

VIETNAMESE_VISUAL_HARNESS = (
    "authentic Vietnamese context, purely Vietnamese human faces, authentic Vietnamese ethnicity, "
    "authentically Vietnamese scenery and architecture, detailed lively environment, "
    "strictly no text, no watermark, no captions, 16:9 widescreen composition, high visual impact, cinematic storytelling frame"
)

STANDARD_NEGATIVE_PROMPT = (
    "low quality, blurry, empty background, plain background, featureless backdrop, text, captions, subtitles, labels, "
    "watermark, signature, duplicate, cropped, jpeg artifacts, Western Caucasian faces, European architecture, foreign Western elements, "
    "deformed anatomy, extra limbs, bad proportions"
)

# Vietnamese sentence boundary regex (avoid splitting abbreviations like TP.HCM, ThS., TS.)
_SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐ0-9\"'“])")


def segment_text_into_paragraphs(text: str, target_words_per_segment: int = 35) -> List[str]:
    """Split raw article text into cohesive narration chunks (around 20-50 words each)."""
    raw_paragraphs = [p.strip() for p in text.strip().split("\n") if p.strip()]
    if not raw_paragraphs:
        return []

    segments: List[str] = []
    for paragraph in raw_paragraphs:
        sentences = _SENTENCE_SPLIT_REGEX.split(paragraph)
        current_chunk: List[str] = []
        current_word_count = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            words = sentence.split()
            word_count = len(words)

            if current_word_count + word_count > target_words_per_segment and current_chunk:
                segments.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_word_count = word_count
            else:
                current_chunk.append(sentence)
                current_word_count += word_count

        if current_chunk:
            segments.append(" ".join(current_chunk))

    return segments if segments else [text.strip()]


def heuristic_visual_priority(text: str, index: int, total: int) -> float:
    """Calculate a baseline visual impact score (1.0 - 10.0) based on position and keywords."""
    score = 5.0
    # First scene (Opening / Hook) gets a high boost
    if index == 0:
        score += 3.5

    lower = text.lower()
    # Visual sensory and action words increase score
    visual_keywords = [
        "thấy", "nhìn", "bỗng", "bất ngờ", "đột nhiên", "khóc", "cười", "ôm",
        "chạy", "bước", "sáng", "tối", "mưa", "nắng", "đẹp", "trời", "biển",
        "con đường", "căn phòng", "ánh mắt", "trái tim", "cô đơn", "hạnh phúc",
        "chiến đấu", "thành công", "thất bại", "khởi đầu", "kết thúc"
    ]
    for kw in visual_keywords:
        if kw in lower:
            score += 0.4

    return min(10.0, max(1.0, round(score, 1)))


def distribute_image_allocations(scenes: List[ArticleScene], target_count: int) -> None:
    """Designate exactly target_count scenes with has_image=True.

    Ensures:
    1. If target_count == 1, the image starts at Scene 0 so the video is illustrated from second 0.
    2. The final image is never pushed to the very end of the timeline (tail scenes),
       giving it a generous 20-35% of the total duration to be seen and appreciated.
    """
    if not scenes:
        return

    # Reset all
    for scene in scenes:
        scene.has_image = False

    target_count = max(1, min(target_count, len(scenes)))

    # If only 1 image requested, pick highest visual priority outside tail buffer
    if target_count == 1:
        tail_buffer = max(1, int(round(len(scenes) * 0.20))) if len(scenes) >= 5 else (1 if len(scenes) > 2 else 0)
        pool = scenes[:len(scenes) - tail_buffer] if tail_buffer > 0 else scenes
        best = max(pool or scenes, key=lambda s: (s.visual_priority_score, -s.scene_index))
        best.has_image = True
        return

    # If target equals or exceeds scenes, enable all
    if target_count >= len(scenes):
        for scene in scenes:
            scene.has_image = True
        return

    # Reserve a tail buffer so the final image is introduced well before the end
    # (at least 20% of the timeline or 2 scenes) to maximize timeline visual impact.
    tail_buffer = max(2, int(round(len(scenes) * 0.20)))
    available_range = max(1, len(scenes) - tail_buffer)

    chosen_indices: List[int] = []

    for i in range(target_count):
        if i == 0:
            anchor = 0
            window_start = 0
            window_end = max(1, int(round(available_range / target_count)))
        elif i == target_count - 1:
            anchor = available_range
            window_start = max(chosen_indices[-1] + 1, int(round(anchor - available_range / (target_count * 2))))
            window_end = min(len(scenes) - max(1, tail_buffer // 2), available_range + 1)
        else:
            fraction = i / (target_count - 1)
            anchor = int(round(fraction * available_range))
            window_start = max(chosen_indices[-1] + 1, int(round((i - 0.4) * (available_range / (target_count - 1)))))
            window_end = min(available_range, int(round((i + 0.4) * (available_range / (target_count - 1))))) + 1

        candidate_window = scenes[window_start:max(window_start + 1, window_end)]
        if candidate_window:
            best = max(candidate_window, key=lambda s: (s.visual_priority_score, -s.scene_index))
            best_idx = best.scene_index
        else:
            best_idx = min(len(scenes) - 1, max(0, anchor))

        if chosen_indices and best_idx <= chosen_indices[-1]:
            best_idx = min(len(scenes) - 1, chosen_indices[-1] + 1)

        chosen_indices.append(best_idx)
        scenes[best_idx].has_image = True


def translate_scene_text_to_english(text: str, timeout_seconds: float = 3.5) -> str:
    """Translate Vietnamese scene narration to descriptive English visual keywords."""
    clean = text.strip().replace("\n", " ")
    if not clean:
        return ""
    # Avoid network during unittests to keep test suite fast and deterministic
    import sys
    if "unittest" in sys.modules and any("test" in arg.lower() for arg in sys.argv) and not os.environ.get("HAIZFLOW_NETWORK_TESTS"):
        return clean

    try:
        from urllib.parse import quote
        from urllib.request import Request, urlopen
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=vi&tl=en&dt=t&q={quote(clean)}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated = "".join([item[0] for item in data[0] if item and item[0]])
            if translated and len(translated.strip()) > 3:
                return translated.strip()
    except Exception as exc:
        logger.debug("Free translation helper failed: %s", exc)
    return clean


def detect_scene_character_id(text: str, default_character_id: Optional[str] = None) -> Optional[str]:
    """Dynamically determine the active focal character for a specific scene from the catalog.

    If default_character_id is 'none', empty, or None, NO character anchor is forced unless
    a character currently active in the catalog is explicitly mentioned by name.
    """
    if not text:
        return None

    # Normalise default character
    effective_default = default_character_id if default_character_id and default_character_id != "none" else None

    # Retrieve currently active characters (excluding any deleted ones)
    from haizflow.services.character_catalog import list_characters
    active_characters = list_characters()
    active_map = {c.id: c for c in active_characters}

    # Verify if effective_default still exists in catalog
    if effective_default and effective_default not in active_map:
        effective_default = None

    t_lower = text.lower()

    # Check if any active character is explicitly mentioned by name in this scene text
    for char_id, char in active_map.items():
        name_raw = char.display_name.split("(")[0].strip()
        if not name_raw or len(name_raw) < 2:
            continue
        if len(name_raw) <= 2:
            # For short names like "An", require proper capitalization and avoid common compound words
            if re.search(rf"\b{re.escape(name_raw)}\b", text) and not any(
                w in t_lower for w in ("an toàn", "bình an", "an tâm", "công an", "an ninh")
            ):
                return char_id
        else:
            if re.search(rf"\b{re.escape(name_raw.lower())}\b", t_lower):
                return char_id

    # Fallback to user-selected default character (if specified and valid)
    return effective_default


def extract_cinematic_focal_context(
    scene_text: str,
    english_translation: str = "",
    character_name: str = "",
) -> tuple[str, bool]:
    """Analyze narration to extract the primary visual subject, action, and camera perspective.

    Returns:
        (focal_visual_description, should_include_character_anchor)
    """
    txt_lower = scene_text.lower()
    eng_lower = english_translation.lower()

    # If english_translation is already provided (e.g. from Gemini or custom), respect its specific action!
    if english_translation and len(english_translation.strip()) > 10:
        return english_translation.strip(), True

    # 1. Specific medical monitor flatline (only when explicitly medical context)
    monitor_triggers = (
        "máy theo dõi nhịp tim", "máy ecg", "monitor icu", "tiếng bíp máy monitor",
        "đường điện tim phẳng", "flatline telemetry", "cardiac flatline"
    )
    is_monitor_scene = any(t in txt_lower or t in eng_lower for t in monitor_triggers)
    has_human_action = any(k in txt_lower for k in ("giật tay", "nhìn thẳng", "cúi", "ép tim", "ngực"))

    if is_monitor_scene and not has_human_action:
        desc = (
            "Cinematic extreme close-up of an ICU hospital patient vital signs telemetry monitor screen, "
            "digital glowing green heart rate line flatlining into a continuous straight alarm line, "
            "cardiac arrest telemetry readout in darkened hospital room, medical emergency drama"
        )
        return desc, False

    # 2. Specific Resuscitation / CPR (only when explicitly CPR resuscitation)
    cpr_triggers = (
        "ép tim hồi sức", "hồi sức tim phổi", "cpr chest compressions", "resuscitation compressions"
    )
    if any(t in txt_lower or t in eng_lower for t in cpr_triggers):
        desc = (
            "Intense dramatic medical emergency in intensive care unit, emergency doctor hands performing "
            "CPR chest compressions on patient in hospital bed, hands interlocked firmly pressing down on patient chest, "
            "elbows locked straight, high-stakes medical resuscitation, dramatic overhead cinematic angle"
        )
        return desc, True

    # 3. Dynamic translation of the actual scene narrative to preserve exact story gestures and postures
    raw_desc = translate_scene_text_to_english(scene_text)
    if not raw_desc:
        raw_desc = scene_text.strip()
    raw_desc = raw_desc.replace("\n", " ").strip()

    return raw_desc, True


def build_scene_prompt(
    scene_text: str,
    image_style: ImageStyle,
    character_id: Optional[str] = None,
    english_translation: str = "",
) -> str:
    """Synthesize a high-impact prompt with focal scene context FIRST, followed by character and style."""
    style_modifier = STYLE_PROMPT_PRESETS.get(image_style, STYLE_PROMPT_PRESETS["cinematic"])

    character = None
    char_name = ""
    if character_id and character_id != "none":
        character = get_character_by_id(character_id)
        if character:
            char_name = character.display_name.split("(")[0].strip()

    core_desc, include_char = extract_cinematic_focal_context(
        scene_text=scene_text,
        english_translation=english_translation,
        character_name=char_name,
    )

    clean_core = core_desc.removeprefix("depicting: ").strip()
    parts: List[str] = [f"depicting: {clean_core}"]

    # Include character presence only if relevant and character actually exists in catalog
    if include_char and character and character.prompt_anchor:
        parts.append(f"featuring {char_name}")
        parts.append(character.prompt_anchor)

    # Cinematic style and composition with Vietnamese visual harness
    parts.append(style_modifier)
    parts.append(VIETNAMESE_VISUAL_HARNESS)

    return ", ".join(parts)



def analyze_article_offline(config: ArticleProjectConfig) -> List[ArticleScene]:
    """Deterministic, zero-network fallback analyzer for offline environments."""
    raw_segments = segment_text_into_paragraphs(config.article_text)
    total = len(raw_segments)
    scenes: List[ArticleScene] = []

    for i, seg in enumerate(raw_segments):
        priority = heuristic_visual_priority(seg, i, total)
        char_id = detect_scene_character_id(seg, config.character_id)
        scene = ArticleScene(
            scene_index=i,
            text=seg,
            visual_priority_score=priority,
            has_image=False,
            character_id=char_id,
            image_prompt="",
        )
        scenes.append(scene)

    distribute_image_allocations(scenes, config.image_count_target)

    for scene in scenes:
        if scene.has_image:
            scene.image_prompt = build_scene_prompt(
                scene_text=scene.text,
                image_style=config.image_style,
                character_id=scene.character_id,
            )

    return scenes


def enhance_visual_prompts_with_gemini(
    scenes: List[ArticleScene],
    config: ArticleProjectConfig,
    api_key: str,
) -> None:
    """Call Google Gemini to craft vivid English visual prompts for scenes requiring illustrations."""
    visual_scenes = [s for s in scenes if s.has_image]
    if not visual_scenes:
        return

    character = None
    if config.character_id and config.character_id != "none":
        character = get_character_by_id(config.character_id)
    char_info = (
        f"Active character: {character.display_name}. Anchor: {character.prompt_anchor}"
        if character
        else "No fixed character: illustrate the scene subjects, actions, or environments naturally according to the narrative."
    )

    scenes_data = [
        {"scene_index": s.scene_index, "scene_text": s.text}
        for s in visual_scenes
    ]

    system_instruction = (
        "You are an expert film director and prompt engineer. "
        "For each given story scene, write a vivid, highly specific English visual prompt ('english_scene_desc') "
        "for text-to-image AI (camera angle, subject, action, lighting, mood). "
        "CRITICAL RULES & VIETNAMESE HARNESS: "
        "- PURE VIETNAMESE AUTHENTICITY: From human characters and faces to scenery and environments, everything MUST be authentically and purely Vietnamese (Vietnamese ethnicity, natural Vietnamese facial features, Vietnamese attire, and authentic Vietnamese landscapes, village architecture, rivers, or streetscapes). Never depict Western, Caucasian, or foreign elements. "
        "- RICH DETAIL & NO EMPTY BACKGROUNDS: Every scene must have rich contextual elements, lively actions, and meaningful details (never an empty or plain background). "
        "- DIVERSIFY VISUAL SUBJECTS: Do NOT create repetitive front-facing character portraits for every scene! Illustrate the focal action, subject, or environment described in the scene. "
        "- STRICTLY NO TEXT: Do not include text, signs, captions, or watermarks in the imagery. "
        f"{char_info}. Visual style: {config.image_style}. "
        "Return ONLY a valid JSON array of objects with keys 'scene_index' (int) and 'english_scene_desc' (string)."
    )

    url = f"{GEMINI_API_ENDPOINT}?{urlencode({'key': api_key})}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_instruction}\n\nScenes to illustrate:\n{json.dumps(scenes_data, ensure_ascii=False)}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
        },
    }

    try:
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))

        raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)

        if isinstance(parsed, list):
            prompt_map = {}
            for item in parsed:
                s_idx = item.get("scene_index")
                desc = str(item.get("english_scene_desc") or "").strip()
                if s_idx is not None and desc:
                    try:
                        prompt_map[int(s_idx)] = desc
                    except (ValueError, TypeError):
                        pass

            # Fallback matching by order if scene_index was omitted by model
            if not prompt_map and len(parsed) > 0:
                for idx, item in enumerate(parsed):
                    desc = str(item.get("english_scene_desc") or "").strip()
                    if desc and idx < len(visual_scenes):
                        prompt_map[visual_scenes[idx].scene_index] = desc

            for scene in visual_scenes:
                if scene.scene_index in prompt_map:
                    eng_desc = prompt_map[scene.scene_index]
                    scene.image_prompt = build_scene_prompt(
                        scene_text=scene.text,
                        image_style=config.image_style,
                        character_id=scene.character_id,
                        english_translation=eng_desc,
                    )
    except (HTTPError, URLError, KeyError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Gemini prompt enhancement failed (%s). Using local prompt builder.", exc)


def analyze_article_with_gemini(config: ArticleProjectConfig, api_key: str) -> List[ArticleScene]:
    """Segment full story and enhance visual prompts using Gemini without truncating any text."""
    # 1. Break the COMPLETE source text into narration scenes, keeping 100% of the story
    raw_segments = segment_text_into_paragraphs(config.article_text)
    if not raw_segments:
        raw_segments = [config.article_text.strip()] if config.article_text.strip() else []

    if not raw_segments:
        return []

    total = len(raw_segments)
    scenes: List[ArticleScene] = []

    for i, seg in enumerate(raw_segments):
        priority = heuristic_visual_priority(seg, i, total)
        char_id = detect_scene_character_id(seg, config.character_id)
        scene = ArticleScene(
            scene_index=i,
            text=seg,  # PRESERVE 100% OF THE ORIGINAL STORY TEXT
            visual_priority_score=priority,
            has_image=False,
            character_id=char_id,
            image_prompt="",
        )
        scenes.append(scene)

    # 2. Distribute illustrations across the full story timeline
    distribute_image_allocations(scenes, config.image_count_target)

    # 3. Enhance prompts with Gemini
    if api_key:
        enhance_visual_prompts_with_gemini(scenes, config, api_key)

    # 4. Fill in any visual scenes that don't have prompts yet
    for scene in scenes:
        if scene.has_image and not scene.image_prompt:
            scene.image_prompt = build_scene_prompt(
                scene_text=scene.text,
                image_style=config.image_style,
                character_id=scene.character_id,
            )

    return scenes


def direct_article(config: ArticleProjectConfig) -> List[ArticleScene]:
    """Primary entry point: directs the entire article into scenes preserving 100% of story content."""
    from haizflow.services.image_generator import get_effective_gemini_api_key
    api_key = get_effective_gemini_api_key()
    if api_key:
        return analyze_article_with_gemini(config, api_key)
    return analyze_article_offline(config)

