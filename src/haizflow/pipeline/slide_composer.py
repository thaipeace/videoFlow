"""SlideComposer: Automated Ken Burns motion, typography, and FFmpeg video assembly.

Takes an ArticleVideoProject with scenes and image assets, computes visual motion
slide specs, renders Ken Burns video segments via hardware-accelerated FFmpeg,
and mixes master audio into a final broadcast-quality 1080p MP4.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

import numpy as np

from haizflow.config import MEDIA_PROCESS_TIMEOUT_SECONDS
from haizflow.schemas.article_video import (
    ArticleProjectConfig,
    ArticleScene,
    ArticleVideoProject,
    AspectRatio,
)
from haizflow.utils.ffmpeg import _binary, get_video_duration, preferred_video_encoder

if TYPE_CHECKING:
    from haizflow.pipeline.ticker import TickerSpec

logger = logging.getLogger(__name__)

EFFECT_ROTATION = [
    "zoom_in",
    "pan_left_to_right",
    "zoom_out",
    "pan_right_to_left",
    "static",
]


def acquire_prevent_sleep() -> None:
    """Prevent Windows OS from sleeping during video rendering."""
    if os.name == "nt":
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            logger.debug("Windows thread execution state set to ES_SYSTEM_REQUIRED (prevent sleep).")
        except Exception as exc:
            logger.debug("Failed to set Windows thread execution state: %s", exc)


def release_prevent_sleep() -> None:
    """Restore default Windows OS sleep behavior."""
    if os.name == "nt":
        ES_CONTINUOUS = 0x80000000
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            logger.debug("Windows thread execution state reset to ES_CONTINUOUS.")
        except Exception:
            pass


@contextlib.contextmanager
def prevent_system_sleep():
    """Context manager to prevent Windows sleep during media tasks."""
    acquire_prevent_sleep()
    try:
        yield
    finally:
        release_prevent_sleep()

# Broadcast-style voice chain: rumble cut, warmth + presence EQ, gentle compression,
# a barely audible room tail, then loudness normalization (-16 LUFS, YouTube friendly).
VOICE_MASTER_CHAIN = (
    "highpass=f=80,"
    "equalizer=f=170:t=q:w=1.0:g=2.5,"
    "equalizer=f=3000:t=q:w=1.2:g=2.0,"
    "equalizer=f=7500:t=q:w=1.5:g=-2.0,"
    "acompressor=threshold=-20dB:ratio=3:attack=15:release=180:makeup=2,"
    "aecho=0.88:0.9:38:0.10,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)

# Chuyên biệt cho Chiến sự thế giới: âm hưởng đanh thép, trường lực mạnh, rền vang hào hùng
WAR_VOICE_MASTER_CHAIN = (
    "highpass=f=75,"
    "equalizer=f=140:t=q:w=1.2:g=3.2,"
    "equalizer=f=2800:t=q:w=1.0:g=2.8,"
    "equalizer=f=5500:t=q:w=1.2:g=1.5,"
    "equalizer=f=8000:t=q:w=1.5:g=-2.5,"
    "acompressor=threshold=-18dB:ratio=3.5:attack=12:release=150:makeup=2.8,"
    "aecho=0.85:0.88:45:0.12,"
    "loudnorm=I=-15.5:TP=-1.0:LRA=9.5"
)


@dataclass
class SlideSpec:
    """Specifications for rendering a single visual slide."""

    image_path: str
    duration_seconds: float
    effect: str
    scene_indices: List[int] = field(default_factory=list)


def resolution_for_aspect_ratio(aspect_ratio: AspectRatio) -> Tuple[int, int]:
    """Return standard (width, height) pixel dimensions for the requested aspect ratio."""
    mapping = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
    }
    return mapping.get(aspect_ratio, (1920, 1080))


def build_ken_burns_filter(
    duration_seconds: float,
    effect: str,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> str:
    """Generate FFmpeg zoompan filter expression for fluid 30fps Ken Burns motion."""
    total_frames = max(1, int(duration_seconds * fps))

    if effect == "zoom_in":
        zoom_step = 0.18 / total_frames
        return (
            f"scale=-2:{height*2},crop={width*2}:{height*2},"
            f"zoompan=z='min(zoom+{zoom_step:.6f},1.18)':"
            f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

    if effect == "zoom_out":
        zoom_step = 0.18 / total_frames
        return (
            f"scale=-2:{height*2},crop={width*2}:{height*2},"
            f"zoompan=z='if(lte(zoom,1.0),1.18,max(1.0,zoom-{zoom_step:.6f}))':"
            f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

    if effect == "pan_left_to_right":
        pan_step = f"((iw-iw/1.12)*({total_frames}-on)/{total_frames})"
        return (
            f"scale=-2:{height*2},crop={width*2}:{height*2},"
            f"zoompan=z='1.12':x='{pan_step}':y='(ih-ih/zoom)/2':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

    if effect == "pan_right_to_left":
        pan_step = f"((iw-iw/1.12)*on/{total_frames})"
        return (
            f"scale=-2:{height*2},crop={width*2}:{height*2},"
            f"zoompan=z='1.12':x='{pan_step}':y='(ih-ih/zoom)/2':"
            f"d={total_frames}:s={width}x{height}:fps={fps}"
        )

    return f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"


def calculate_slide_specs(
    scenes: List[ArticleScene],
    default_image_path: str = "",
    min_slide_duration: float = 3.0,
) -> List[SlideSpec]:
    """Group consecutive scenes under active illustration images into SlideSpecs."""
    if not scenes:
        return []

    specs: List[SlideSpec] = []
    current_image = ""
    current_duration_ms = 0
    current_scene_indices: List[int] = []
    effect_idx = 0

    fallback_image = default_image_path
    for s in scenes:
        if s.has_image and s.image_path:
            fallback_image = s.image_path
            break

    for idx, scene in enumerate(scenes):
        scene_dur = scene.duration_ms if scene.duration_ms > 0 else 4000

        if scene.has_image and scene.image_path and (scene.image_path != current_image or not current_image):
            if current_image and current_duration_ms > 0:
                duration_sec = max(min_slide_duration, current_duration_ms / 1000.0)
                effect = EFFECT_ROTATION[effect_idx % len(EFFECT_ROTATION)]
                specs.append(
                    SlideSpec(
                        image_path=current_image,
                        duration_seconds=duration_sec,
                        effect=effect,
                        scene_indices=list(current_scene_indices),
                    )
                )
                effect_idx += 1
            current_image = scene.image_path
            current_duration_ms = scene_dur
            current_scene_indices = [idx]
        else:
            if not current_image:
                current_image = fallback_image or scene.image_path or default_image_path
            current_duration_ms += scene_dur
            current_scene_indices.append(idx)

    if current_image and current_duration_ms > 0:
        duration_sec = max(min_slide_duration, current_duration_ms / 1000.0)
        effect = EFFECT_ROTATION[effect_idx % len(EFFECT_ROTATION)]
        specs.append(
            SlideSpec(
                image_path=current_image,
                duration_seconds=duration_sec,
                effect=effect,
                scene_indices=list(current_scene_indices),
            )
        )

    return specs


def _build_overlay_graph(
    filter_chain: str,
    overlay_path: Optional[Path],
    ticker: Optional["TickerSpec"] = None,
    cta_video_path: Optional[Path] = None,
    cta_start_sec: float = 0.5,
) -> Tuple[List[str], List[str]]:
    """Return (extra FFmpeg input args, filter args) layering ticker, CTA, and branding over the slide.

    Layer order (bottom -> top): motion slide, ticker bar, scrolling strip, ticker badge, CTA card, branding.
    Extra inputs start at index 1 (index 0 is the slide image).
    """
    if not overlay_path and not ticker and not cta_video_path:
        return [], ["-vf", filter_chain]

    extra_inputs: List[str] = []
    parts: List[str] = [f"[0:v]{filter_chain}[s0]"]
    label_no = 0
    next_input_idx = 1

    def add_loop_input(path: Path) -> int:
        nonlocal next_input_idx
        extra_inputs.extend(["-loop", "1", "-i", str(Path(path).resolve())])
        idx = next_input_idx
        next_input_idx += 1
        return idx

    def add_video_input(path: Path) -> int:
        nonlocal next_input_idx
        extra_inputs.extend(["-i", str(Path(path).resolve())])
        idx = next_input_idx
        next_input_idx += 1
        return idx

    def chain(filter_desc: str, input_idx: Optional[int] = None) -> None:
        nonlocal label_no
        src = f"[s{label_no}]"
        label_no += 1
        dst = f"[s{label_no}]"
        pad = f"[{input_idx}:v]" if input_idx is not None else ""
        parts.append(f"{src}{pad}{filter_desc}{dst}")

    if ticker:
        chain(",".join(ticker.drawbox_filters()))
        chain(ticker.scroll_overlay(), add_loop_input(ticker.strip_path))
        chain(f"overlay=x=0:y={ticker.bar_y}:format=auto", add_loop_input(ticker.badge_path))
    if cta_video_path and Path(cta_video_path).is_file():
        c_idx = add_video_input(cta_video_path)
        cta_lbl = f"cta{label_no}"
        parts.append(f"[{c_idx}:v]setpts=PTS-STARTPTS+{cta_start_sec:.2f}/TB[{cta_lbl}]")
        src = f"[s{label_no}]"
        label_no += 1
        dst = f"[s{label_no}]"
        parts.append(f"{src}[{cta_lbl}]overlay=0:0:enable='gte(t,{cta_start_sec:.2f})':format=auto{dst}")
    if overlay_path:
        chain("overlay=0:0:format=auto", add_loop_input(overlay_path))

    parts[-1] = parts[-1].rsplit(f"[s{label_no}]", 1)[0] + ",format=yuv420p[v]"
    return extra_inputs, ["-filter_complex", ";".join(parts), "-map", "[v]"]


def render_single_slide(
    spec: SlideSpec,
    output_path: Path,
    aspect_ratio: AspectRatio = "16:9",
    fps: int = 30,
    cancel_event: Optional[Event] = None,
    overlay_path: Optional[Path] = None,
    ticker: Optional["TickerSpec"] = None,
    cta_video_path: Optional[Path] = None,
    cta_start_sec: float = 0.5,
) -> Path:
    """Render an individual motion slide MP4 using hardware acceleration when possible."""
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("Slide render cancelled by user.")

    width, height = resolution_for_aspect_ratio(aspect_ratio)
    filter_chain = build_ken_burns_filter(
        duration_seconds=spec.duration_seconds,
        effect=spec.effect,
        width=width,
        height=height,
        fps=fps,
    )

    encoder, encoder_args = preferred_video_encoder(quality=21)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image_arg = str(Path(spec.image_path).resolve())
    extra_inputs, filter_args = _build_overlay_graph(
        filter_chain,
        overlay_path,
        ticker,
        cta_video_path=cta_video_path,
        cta_start_sec=cta_start_sec,
    )
    input_args = ["-loop", "1", "-i", image_arg, *extra_inputs]

    cmd = [
        _binary("ffmpeg"),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        *input_args,
        *filter_args,
        "-t", f"{spec.duration_seconds:.3f}",
        "-c:v", encoder,
        *encoder_args,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path.resolve()),
    ]

    result = None
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(60.0, spec.duration_seconds * 10),
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as tex:
        logger.warning(
            "Slide render encoder '%s' timed out (spec duration %.2fs): %s. Falling back to CPU libx264.",
            encoder, spec.duration_seconds, tex
        )
        result = None

    if result is None or result.returncode != 0:
        if encoder != "libx264":
            fallback_cmd = [
                _binary("ffmpeg"),
                "-y",
                "-hide_banner",
                "-loglevel", "error",
                *input_args,
                *filter_args,
                "-t", f"{spec.duration_seconds:.3f}",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-pix_fmt", "yuv420p",
                str(output_path.resolve()),
            ]
            try:
                fallback_res = subprocess.run(
                    fallback_cmd,
                    capture_output=True,
                    text=True,
                    timeout=max(90.0, spec.duration_seconds * 15),
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if fallback_res.returncode != 0:
                    raise RuntimeError(f"FFmpeg slide render failed: {fallback_res.stderr.strip()}")
            except subprocess.TimeoutExpired as fb_tex:
                raise RuntimeError(f"FFmpeg CPU fallback timed out: {fb_tex}")
        else:
            err_msg = result.stderr.strip() if result else "Process timed out"
            raise RuntimeError(f"FFmpeg slide render failed: {err_msg}")

    return output_path


def _format_srt_timestamp(ms: int) -> str:
    """Format milliseconds into SRT timestamp format: HH:MM:SS,mmm."""
    total_seconds = max(0, ms) // 1000
    milliseconds = max(0, ms) % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def export_subtitles_to_srt(scenes: List[ArticleScene], output_path: Path) -> Path:
    """Generate a clean, timed SRT subtitle file from narrated scenes."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    blocks: List[str] = []
    idx = 1

    for scene in scenes:
        text = scene.text.strip()
        if not text:
            continue
        start_ms = getattr(scene, "start_time_ms", 0)
        dur_ms = max(500, getattr(scene, "duration_ms", 3000))
        end_ms = start_ms + dur_ms
        if getattr(scene, "has_transition_cue", False):
            start_ms += 450

        start_ts = _format_srt_timestamp(start_ms)
        end_ts = _format_srt_timestamp(end_ms)
        blocks.append(f"{idx}\n{start_ts} --> {end_ts}\n{text}\n")
        idx += 1

    output_path.write_text("\n".join(blocks), encoding="utf-8")
    return output_path


def concatenate_video_clips(clip_paths: List[Path], output_path: Path) -> Path:
    """Concatenate multiple slide clips smoothly using FFmpeg concat demuxer."""
    if not clip_paths:
        raise ValueError("No video clips provided for concatenation.")
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], output_path)
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.parent / "concat_list.txt"

    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in clip_paths:
                clean_path = str(p.resolve()).replace("\\", "/")
                f.write(f"file '{clean_path}'\n")

        cmd = [
            _binary("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file.resolve()),
            "-c", "copy",
            str(output_path.resolve()),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MEDIA_PROCESS_TIMEOUT_SECONDS,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode != 0:
            raise RuntimeError(f"Video concatenation failed: {result.stderr.strip()}")

        return output_path
    finally:
        if list_file.is_file():
            list_file.unlink()


def concatenate_audio_clips(audio_paths: List[Path], output_path: Path) -> Path:
    """Concatenate narration clips into a continuous audio file using FFmpeg filter complex."""
    if not audio_paths:
        raise ValueError("No audio clips provided for concatenation.")
    if len(audio_paths) == 1:
        shutil.copy2(audio_paths[0], output_path)
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    inputs = []
    filter_parts = []
    for i, p in enumerate(audio_paths):
        inputs.extend(["-i", str(p.resolve())])
        filter_parts.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a{i}];")

    concat_inputs = "".join(f"[a{i}]" for i in range(len(audio_paths)))
    filter_complex = f"{''.join(filter_parts)}{concat_inputs}concat=n={len(audio_paths)}:v=0:a=1[out]"

    cmd = [
        _binary("ffmpeg"),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        str(output_path.resolve()),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=MEDIA_PROCESS_TIMEOUT_SECONDS,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    if result.returncode != 0:
        raise RuntimeError(f"Audio concatenation failed: {result.stderr.strip()}")

    return output_path


def get_or_generate_news_bgm(output_dir: Optional[Path] = None) -> Path:
    """Synthesize high-end atmospheric broadcast news soundtrack."""
    runtime_dir = Path(__file__).resolve().parent.parent.parent.parent / "runtime" / "assets"
    dest = (output_dir or runtime_dir) / "news_broadcast_theme.wav"
    dest.parent.mkdir(parents=True, exist_ok=True)

    asset_bgm = Path(__file__).resolve().parent.parent / "assets" / "sounds" / "news_broadcast_theme.wav"
    if asset_bgm.is_file() and asset_bgm.stat().st_size > 10000:
        try:
            shutil.copy2(str(asset_bgm), str(dest))
            return dest
        except Exception:
            pass

    if dest.is_file() and dest.stat().st_size > 10000:
        return dest

    try:
        sr = 48000
        dur = 30.0
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)

        drone_f = 65.41
        drone = 0.18 * np.sin(2 * np.pi * drone_f * t)
        drone += 0.10 * np.sin(2 * np.pi * (drone_f * 1.5) * t)

        pad = 0.08 * np.sin(2 * np.pi * 130.81 * t) + 0.06 * np.sin(2 * np.pi * 196.00 * t)

        pulse = np.zeros_like(t)
        bpm = 110.0
        beat_interval = 60.0 / bpm
        decay_samples = int(sr * 0.12)
        env = np.exp(-np.linspace(0, 5, decay_samples))
        for b in np.arange(0, dur, beat_interval):
            idx_start = int(b * sr)
            idx_end = min(len(pulse), idx_start + decay_samples)
            actual_len = idx_end - idx_start
            pulse[idx_start:idx_end] += (
                0.22 * np.sin(2 * np.pi * 55.0 * t[idx_start:idx_end]) * env[:actual_len]
            )

        shimmer = 0.03 * np.sin(2 * np.pi * 523.25 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t))

        mix = drone + pad + pulse + shimmer
        fade_samples = int(sr * 1.0)
        mix[:fade_samples] *= np.linspace(0, 1, fade_samples)
        mix[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        peak = np.max(np.abs(mix))
        scaled = (mix / peak) * 27500.0
        audio_i16 = scaled.astype(np.int16)

        with wave.open(str(dest), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(audio_i16.tobytes())

        return dest
    except Exception as exc:
        logger.warning("BGM synthesis failed (%s). Continuing without custom BGM.", exc)
        return dest


def mix_master_audio(
    narration_audio: Path,
    output_path: Path,
    bgm_path: Optional[Path] = None,
    bgm_volume: float = 0.08,
    voice_chain: Optional[str] = None,
    target_video_duration: Optional[float] = None,
) -> Path:
    """Mix speech with ducked background music into a master audio stream."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chain = voice_chain or VOICE_MASTER_CHAIN

    if not bgm_path or not Path(bgm_path).is_file():
        filter_complex = f"[0:a]{chain}[out]"
        cmd = [
            _binary("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(narration_audio.resolve()),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "aac",
            "-b:a", "320k",
            "-ar", "48000",
            str(output_path.resolve()),
        ]
    else:
        total_duration = get_video_duration(str(narration_audio.resolve()))
        if target_video_duration and target_video_duration > total_duration:
            total_duration = target_video_duration

        vol_str = f"{max(0.0, min(1.0, bgm_volume)):.2f}"
        fade_out_dur = min(1.5, max(0.2, total_duration * 0.2))
        fade_out_start = max(0.0, total_duration - fade_out_dur)
        fade_in_dur = min(0.4, max(0.1, total_duration * 0.1))

        filter_complex = (
            f"[0:a]{chain},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[vox];"
            f"[1:a]volume={vol_str},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"afade=t=in:st=0:d={fade_in_dur:.2f},afade=t=out:st={fade_out_start:.2f}:d={fade_out_dur:.2f}[bgm];"
            f"[vox][bgm]sidechaincompress=threshold=0.08:ratio=4:attack=20:release=250[ducked];"
            f"[ducked]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[out]"
        )

        cmd = [
            _binary("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(narration_audio.resolve()),
            "-stream_loop", "-1",
            "-i", str(Path(bgm_path).resolve()),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-t", f"{total_duration:.2f}",
            "-c:a", "aac",
            "-b:a", "320k",
            "-ar", "48000",
            str(output_path.resolve()),
        ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=MEDIA_PROCESS_TIMEOUT_SECONDS,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    if result.returncode != 0:
        raise RuntimeError(f"Audio mixing failed: {result.stderr.strip()}")

    return output_path


def generate_news_transition_sting(output_path: Path) -> Path:
    """Acquire or synthesize a punchy, broadcast television news transition chime / cue."""
    output_path = Path(output_path).resolve()
    if output_path.is_file() and output_path.stat().st_size > 5000:
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    asset_sting = Path(__file__).resolve().parent.parent / "assets" / "sounds" / "news_transition.wav"
    if asset_sting.is_file() and asset_sting.stat().st_size > 5000:
        try:
            shutil.copy2(str(asset_sting), str(output_path))
            return output_path
        except Exception as exc:
            logger.debug("Could not copy pre-packaged transition sting: %s", exc)

    try:
        sr = 48000
        dur = 0.45
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        decay = np.exp(-t * 9.0)

        f1, f2, f3 = 587.33, 880.0, 1174.66
        sig = (
            0.45 * np.sin(2 * np.pi * f1 * t)
            + 0.35 * np.sin(2 * np.pi * f2 * t)
            + 0.20 * np.sin(2 * np.pi * f3 * t)
        )
        sig *= decay
        sig_i16 = (sig * 28000).astype(np.int16)

        with wave.open(str(output_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(sig_i16.tobytes())

        return output_path
    except Exception as exc:
        logger.warning("Could not synthesize transition cue: %s", exc)
        return output_path


def _generate_silent_audio(output_path: Path, duration_sec: float = 3.0) -> None:
    """Generate a clean silent audio track with exact duration as safety fallback."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _binary("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", "anullsrc=r=48000:cl=stereo",
            "-t", f"{duration_sec:.2f}",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_path.resolve()),
        ],
        capture_output=True,
        timeout=30.0,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def generate_scenes_narration(
    scenes: List[ArticleScene],
    config: ArticleProjectConfig,
    output_dir: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[Event] = None,
) -> None:
    """Synthesize speech audio for all article scenes, computing real durations and timeline offsets.

    Supports single-voice or studio multi-speaker rotation (3 voices: Nam Minh, Hoài My, and Analyst).
    """
    from haizflow.pipeline.tts import generate_single_voice

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(scenes)
    current_timeline_ms = 0

    provider = config.voice_provider or "edge"
    raw_voice_cfg = str(config.voice_id or "vi-VN-NamMinhNeural").strip()
    is_multi_trio = raw_voice_cfg.lower() in ("multi_trio", "rotation", "multi_speaker", "random", "trio")

    # 3-speaker profiles for television studio broadcast:
    # Speaker 0: BTV Nam chính (Nam Minh - Hà Nội, Trầm ấm chuẩn VTV)
    # Speaker 1: BTV Nữ chính (Hoài My - Sài Gòn, Truyền cảm nhẹ nhàng)
    # Speaker 2: Chuyên gia phân tích / Bình luận viên (Nam Minh pitch 0.88 - Trầm dày uy tín)
    trio_speakers = [
        {"voice": "vi-VN-NamMinhNeural", "pitch_shift": None, "label": "BTV Nam Minh"},
        {"voice": "vi-VN-HoaiMyNeural", "pitch_shift": None, "label": "BTV Hoài My"},
        {"voice": "vi-VN-NamMinhNeural", "pitch_shift": 0.88, "label": "Chuyên gia phân tích"},
    ]
    current_speaker_idx = 0

    for idx, scene in enumerate(scenes):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("TTS generation cancelled by user.")

        scene_text = scene.text.strip()
        if not scene_text:
            continue

        audio_dest = output_dir / f"scene_{scene.scene_index:03d}.mp3"

        # Determine speaker for this scene
        if is_multi_trio:
            if idx == 0:
                current_speaker_idx = 0
            elif getattr(scene, "has_transition_cue", False):
                current_speaker_idx = (current_speaker_idx + 1) % len(trio_speakers)
            active_speaker = trio_speakers[current_speaker_idx]
            scene_voice = active_speaker["voice"]
            pitch_shift = active_speaker["pitch_shift"]
            spk_label = active_speaker["label"]
        else:
            scene_voice = raw_voice_cfg
            pitch_shift = None
            spk_label = "Phát thanh viên"

        # Synthesize audio if not already existing
        if not scene.audio_path or not Path(scene.audio_path).is_file() or Path(scene.audio_path).stat().st_size == 0:
            if progress_callback:
                pct = int(5 + (idx / max(1, total)) * 25)
                progress_callback(
                    pct,
                    f"Đang tạo giọng đọc AI ({spk_label}) phân cảnh {idx + 1}/{total}...",
                )

            success = False
            # Try configured provider first
            try:
                generate_single_voice(
                    text=scene_text,
                    output_path=str(audio_dest),
                    voice=scene_voice,
                    video_id=f"article_scene_{idx}",
                    provider=provider,
                    target_language="vi",
                )
                success = audio_dest.is_file() and audio_dest.stat().st_size > 512
            except Exception as exc:
                logger.warning(
                    "TTS provider '%s' failed for scene %d with voice '%s' (%s). Falling back to alternate voice.",
                    provider, idx, scene_voice, exc,
                )

            # Fallback to alternate Edge-TTS voice if primary failed
            if not success:
                fallback_voice = "vi-VN-NamMinhNeural" if "HoaiMy" in scene_voice else "vi-VN-HoaiMyNeural"
                time.sleep(1.0)
                try:
                    generate_single_voice(
                        text=scene_text,
                        output_path=str(audio_dest),
                        voice=fallback_voice,
                        video_id=f"article_scene_{idx}_fallback",
                        provider="edge",
                        target_language="vi",
                    )
                    success = audio_dest.is_file() and audio_dest.stat().st_size > 512
                except Exception as exc2:
                    logger.warning(
                        "Fallback voice '%s' also failed for scene %d (%s).",
                        fallback_voice, idx, exc2,
                    )

            # Direct Edge-TTS rescue loop before giving up to silent audio
            if not success or not audio_dest.is_file() or audio_dest.stat().st_size < 512:
                try:
                    import asyncio
                    import edge_tts

                    async def _rescue_edge_tts(txt: str, target_p: Path) -> bool:
                        for v in [scene_voice, "vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"]:
                            for attempt in range(2):
                                try:
                                    comm = edge_tts.Communicate(txt, v)
                                    await comm.save(str(target_p))
                                    if target_p.is_file() and target_p.stat().st_size > 512:
                                        return True
                                except Exception:
                                    await asyncio.sleep(1.0)
                        return False

                    logger.info("Attempting direct Edge-TTS rescue for scene %d...", idx)
                    if asyncio.run(_rescue_edge_tts(scene_text, audio_dest)):
                        success = True
                        logger.info("Direct Edge-TTS rescue succeeded for scene %d", idx)
                except Exception as rescue_exc:
                    logger.warning("Direct Edge-TTS rescue failed for scene %d: %s", idx, rescue_exc)

            # Apply pitch shift transformation if specified (e.g. for Analyst voice)
            if success and pitch_shift and audio_dest.is_file() and audio_dest.stat().st_size > 512:
                pitched_tmp = output_dir / f"pitched_{scene.scene_index:03d}.mp3"
                try:
                    res_pitch = subprocess.run(
                        ["ffmpeg", "-y", "-i", str(audio_dest), "-filter:a", f"rubberband=pitch={pitch_shift}", str(pitched_tmp)],
                        capture_output=True,
                        check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    if res_pitch.returncode == 0 and pitched_tmp.is_file() and pitched_tmp.stat().st_size > 512:
                        os.replace(pitched_tmp, audio_dest)
                    else:
                        res_fb = subprocess.run(
                            ["ffmpeg", "-y", "-i", str(audio_dest), "-filter:a", f"asetrate=44100*{pitch_shift},atempo={1.0/pitch_shift:.3f},aresample=44100", str(pitched_tmp)],
                            capture_output=True,
                            check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                        if res_fb.returncode == 0 and pitched_tmp.is_file() and pitched_tmp.stat().st_size > 512:
                            os.replace(pitched_tmp, audio_dest)
                except Exception as pe:
                    logger.warning("Pitch shifting failed for scene %d: %s", idx, pe)
                finally:
                    if pitched_tmp.is_file():
                        try:
                            pitched_tmp.unlink()
                        except Exception:
                            pass

            # Emergency fallback: generate silent audio matching estimated speech duration so video is preserved
            if not success or not audio_dest.is_file() or audio_dest.stat().st_size < 512:
                logger.error(
                    "All TTS voices failed for scene %d. Generating silent audio fallback to preserve video render.",
                    idx,
                )
                word_count = len(scene_text.split())
                approx_dur = max(3.0, min(15.0, word_count / 3.0))
                _generate_silent_audio(audio_dest, duration_sec=approx_dur)

            # Mix transition sting cue if requested
            if getattr(scene, "has_transition_cue", False):
                try:
                    sting_path = output_dir / "cue_sting.wav"
                    generate_news_transition_sting(sting_path)
                    if sting_path.is_file():
                        cued_dest = output_dir / f"scene_{scene.scene_index:03d}_cued.wav"
                        mix_cmd = [
                            _binary("ffmpeg"),
                            "-y",
                            "-hide_banner",
                            "-loglevel", "error",
                            "-i", str(audio_dest.resolve()),
                            "-i", str(sting_path.resolve()),
                            "-filter_complex",
                            "[0:a]adelay=320|320[delayed_voice];[1:a]volume=0.45[cue];"
                            "[delayed_voice][cue]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[mixed]",
                            "-map", "[mixed]",
                            "-c:a", "pcm_s16le",
                            str(cued_dest.resolve()),
                        ]
                        res_mix = subprocess.run(
                            mix_cmd,
                            capture_output=True,
                            text=True,
                            timeout=30.0,
                            check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                        if res_mix.returncode == 0 and cued_dest.is_file() and cued_dest.stat().st_size > 1000:
                            audio_dest = cued_dest
                except Exception as cue_exc:
                    logger.warning("Could not mix transition sting into scene %d: %s", idx, cue_exc)

            scene.audio_path = str(audio_dest.resolve())

        # Measure exact audio duration and timeline offset
        duration_sec = get_video_duration(scene.audio_path)
        scene.duration_ms = max(1000, int(round(duration_sec * 1000)))
        scene.start_time_ms = current_timeline_ms
        current_timeline_ms += scene.duration_ms


def compose_article_video(
    project: ArticleVideoProject,
    output_video_path: Path,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event: Optional[Event] = None,
) -> Path:
    """Full pipeline execution: Synthesizes TTS, renders motion slides, mixes audio, embeds subs, exports 1080p MP4."""
    if not project.scenes:
        raise ValueError("Project contains no scenes to render.")

    output_video_path = Path(output_video_path).resolve()
    output_video_path.parent.mkdir(parents=True, exist_ok=True)

    staging_dir = output_video_path.parent / f".staging-{project.project_id}"
    staging_dir.mkdir(parents=True, exist_ok=True)

    def report(pct: int, msg: str) -> None:
        if progress_callback:
            progress_callback(pct, msg)

    acquire_prevent_sleep()
    try:
        # Check if narration needs synthesis
        scenes_needing_audio = any(
            not s.audio_path or not Path(s.audio_path).is_file() or Path(s.audio_path).stat().st_size == 0
            for s in project.scenes
            if s.text.strip()
        )
        if scenes_needing_audio:
            report(5, "Đang tổng hợp giọng đọc AI cho các phân cảnh...")
            audio_staging = staging_dir / "narration_audio"
            generate_scenes_narration(
                scenes=project.scenes,
                config=project.config,
                output_dir=audio_staging,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )

        report(30, "Đang tính toán timeline và hiệu ứng chuyển động...")

        # 1. Calculate slide specs
        slide_specs = calculate_slide_specs(project.scenes)
        if not slide_specs:
            raise ValueError("No slides could be constructed from project scenes.")

        total_slides = len(slide_specs)
        rendered_slide_paths: List[Path] = []

        branding_pool = None
        if getattr(project.config, "branding_enabled", False):
            from haizflow.pipeline.branding import BrandingOverlayPool

            b_w, b_h = resolution_for_aspect_ratio(project.config.aspect_ratio)
            branding_pool = BrandingOverlayPool(
                b_w, b_h, staging_dir / "branding", seed=project.project_id
            )

        ticker_spec = None
        ticker_text = str(getattr(project.config, "ticker_text", "") or "").strip()
        if ticker_text:
            try:
                from haizflow.pipeline.ticker import build_ticker

                t_w, t_h = resolution_for_aspect_ratio(project.config.aspect_ratio)
                ticker_spec = build_ticker(
                    t_w,
                    t_h,
                    ticker_text,
                    staging_dir / "ticker",
                    label=getattr(project.config, "ticker_label", "TIN MỚI"),
                )
            except Exception as ticker_exc:
                logger.warning("News ticker unavailable, rendering without it: %s", ticker_exc)
        timeline_offset = 0.0

        # Subscribe CTA Animation & SFX setup
        cta_video_file: Optional[Path] = None
        cta_sfx_file: Optional[Path] = None
        if total_slides >= 1:
            try:
                from haizflow.pipeline.subscribe_cta import get_or_build_subscribe_cta

                c_w, c_h = resolution_for_aspect_ratio(project.config.aspect_ratio)
                cta_video_file, cta_sfx_file = get_or_build_subscribe_cta(
                    width=c_w,
                    height=c_h,
                    staging_dir=staging_dir / "cta",
                )
            except Exception as cta_setup_err:
                logger.warning("Subscribe CTA assets unavailable: %s", cta_setup_err)
                cta_video_file, cta_sfx_file = None, None

        # 2. Render each motion slide clip
        for i, spec in enumerate(slide_specs, start=1):
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Video composition cancelled.")

            step_pct = int(35 + (i / total_slides) * 30)
            report(step_pct, f"Đang dựng slide chuyển động {i}/{total_slides} ({spec.effect})...")

            slide_dest = staging_dir / f"slide_{i:03d}.mp4"
            slide_overlay = None
            if branding_pool:
                if hasattr(branding_pool, "next_overlay"):
                    slide_overlay = branding_pool.next_overlay()
                elif hasattr(branding_pool, "get_overlay"):
                    slide_overlay = branding_pool.get_overlay(
                        slide_index=i - 1,
                        total_slides=total_slides,
                        time_offset=timeline_offset,
                    )

            slide_cta_video = None
            slide_cta_start = 0.5
            if i == total_slides and cta_video_file and cta_video_file.is_file():
                slide_cta_video = cta_video_file
                if spec.duration_seconds > 4.5:
                    slide_cta_start = spec.duration_seconds - 4.2
                else:
                    slide_cta_start = 0.4

            render_single_slide(
                spec=spec,
                output_path=slide_dest,
                aspect_ratio=project.config.aspect_ratio,
                fps=30,
                cancel_event=cancel_event,
                overlay_path=slide_overlay,
                ticker=ticker_spec,
                cta_video_path=slide_cta_video,
                cta_start_sec=slide_cta_start,
            )
            rendered_slide_paths.append(slide_dest)
            timeline_offset += spec.duration_seconds

        report(65, "Đang ghép nối các slide chuyển cảnh...")
        video_track = staging_dir / "composed_video.mp4"
        concatenate_video_clips(rendered_slide_paths, video_track)

        # 3. Concatenate and mix audio
        report(70, "Đang xử lý và hòa âm giọng đọc...")

        # Mix CTA SFX into the last scene's narration
        if cta_sfx_file and project.scenes and total_slides >= 1:
            last_scene = project.scenes[-1]
            if last_scene.audio_path and Path(last_scene.audio_path).is_file():
                try:
                    from haizflow.pipeline.subscribe_cta import mix_cta_sfx_into_audio

                    last_dur = slide_specs[-1].duration_seconds
                    cta_delay = max(0.4, last_dur - 4.2) if last_dur > 4.5 else 0.4
                    sfx_dest = staging_dir / "last_scene_with_cta_sfx.wav"
                    mixed_audio = mix_cta_sfx_into_audio(
                        scene_audio_path=Path(last_scene.audio_path),
                        sfx_path=cta_sfx_file,
                        delay_sec=cta_delay,
                        output_path=sfx_dest,
                    )
                    last_scene.audio_path = str(mixed_audio)
                except Exception as sfx_mix_err:
                    logger.warning("Could not mix CTA SFX into scene audio: %s", sfx_mix_err)

        narration_clips = [Path(s.audio_path) for s in project.scenes if s.audio_path and Path(s.audio_path).is_file()]

        if narration_clips:
            unified_narration = staging_dir / "narration.wav"
            concatenate_audio_clips(narration_clips, unified_narration)
            master_audio = staging_dir / "master_audio.aac"

            resolved_bgm = None
            bgm_setting = str(project.config.background_music_path or "").strip().lower()
            if bgm_setting in ("none", "off", "false", "disabled"):
                resolved_bgm = None
            elif bgm_setting in ("default", "news", "true") or not project.config.background_music_path:
                resolved_bgm = get_or_generate_news_bgm()
            else:
                custom_p = Path(project.config.background_music_path)
                if custom_p.is_file():
                    resolved_bgm = custom_p
                else:
                    resolved_bgm = get_or_generate_news_bgm()

            total_video_dur = sum(s.duration_seconds for s in slide_specs)
            is_war = getattr(project.config, "category", "") == "war" or "chiensu" in getattr(project.config, "article_text", "").lower()[:200]
            chosen_voice_chain = WAR_VOICE_MASTER_CHAIN if is_war else VOICE_MASTER_CHAIN
            mix_master_audio(
                narration_audio=unified_narration,
                output_path=master_audio,
                bgm_path=resolved_bgm,
                bgm_volume=project.config.background_music_volume,
                voice_chain=chosen_voice_chain,
                target_video_duration=total_video_dur,
            )
            has_audio = True
        else:
            has_audio = False

        # 4. Export SRT Subtitle file
        srt_file = staging_dir / "subtitles.srt"
        export_subtitles_to_srt(project.scenes, srt_file)

        report(85, "Đang muxing và xuất bản video YouTube 1080p...")

        # 5. Final muxing with FFmpeg
        input_args: List[str] = ["-i", str(video_track.resolve())]
        video_idx = 0

        audio_idx = -1
        if has_audio:
            audio_idx = len(input_args) // 2
            input_args.extend(["-i", str(master_audio.resolve())])

        sub_idx = -1
        has_sub = bool(
            project.config.subtitle_enabled
            and srt_file.is_file()
            and srt_file.stat().st_size > 0
        )
        if has_sub:
            sub_idx = len(input_args) // 2
            input_args.extend(["-i", str(srt_file.resolve())])

        output_args: List[str] = [
            "-c:v", "copy",
            "-map", f"{video_idx}:v:0",
        ]

        if has_audio:
            output_args.extend([
                "-c:a", "copy",
                "-map", f"{audio_idx}:a:0",
            ])

        if has_sub:
            output_args.extend([
                "-c:s", "mov_text",
                "-map", f"{sub_idx}:s:0",
                "-metadata:s:s:0", "language=vie",
            ])

        output_args.extend([
            "-movflags", "+faststart",
            str(output_video_path.resolve()),
        ])

        final_cmd = [
            _binary("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            *input_args,
            *output_args,
        ]

        result = subprocess.run(
            final_cmd,
            capture_output=True,
            text=True,
            timeout=MEDIA_PROCESS_TIMEOUT_SECONDS,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode != 0:
            raise RuntimeError(f"Final video muxing failed: {result.stderr.strip()}")

        # Ensure YouTube Shorts hard duration ceiling: <= 25.0s
        is_short_aspect = getattr(project.config, "aspect_ratio", "") == "9:16"
        is_short_cat = getattr(project.config, "category", "") in ("viral", "hope", "tinla", "docla", "tinvui", "hyvong")
        if is_short_aspect or is_short_cat:
            from haizflow.utils.ffmpeg import get_video_duration
            actual_dur = get_video_duration(str(output_video_path.resolve()))
            max_short_sec = 25.0
            if actual_dur > max_short_sec:
                logger.info(
                    "Shorts video duration (%.2fs) exceeds %.1fs limit. Applying dynamic adjustment to guarantee <= %.1fs.",
                    actual_dur, max_short_sec, max_short_sec
                )
                capped_tmp = output_video_path.parent / f"capped_{output_video_path.name}"
                target_dur = 24.8
                speed_ratio = actual_dur / target_dur
                if speed_ratio <= 1.30:
                    cap_cmd = [
                        _binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(output_video_path.resolve()),
                        "-filter:v", f"setpts=PTS/{speed_ratio:.4f}",
                        "-filter:a", f"atempo={speed_ratio:.4f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-c:a", "aac", "-b:a", "320k",
                        "-movflags", "+faststart",
                        str(capped_tmp.resolve())
                    ]
                else:
                    fade_st = max_short_sec - 0.5
                    cap_cmd = [
                        _binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(output_video_path.resolve()),
                        "-t", f"{max_short_sec:.2f}",
                        "-filter:a", f"afade=t=out:st={fade_st:.2f}:d=0.5",
                        "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "320k",
                        "-movflags", "+faststart",
                        str(capped_tmp.resolve())
                    ]
                res_cap = subprocess.run(
                    cap_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120.0,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if res_cap.returncode == 0 and capped_tmp.is_file() and capped_tmp.stat().st_size > 1000:
                    os.replace(capped_tmp, output_video_path)
                    logger.info("Capped Shorts video duration successfully to %.2fs", get_video_duration(str(output_video_path.resolve())))
                else:
                    if capped_tmp.is_file():
                        try:
                            capped_tmp.unlink()
                        except Exception:
                            pass

        report(100, "Xuất video YouTube hoàn tất!")
        return output_video_path

    finally:
        release_prevent_sleep()
        # Clean up staging directory
        try:
            shutil.rmtree(staging_dir, ignore_errors=True)
        except OSError:
            pass
