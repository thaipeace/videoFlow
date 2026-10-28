"""Article Video Desktop Controller.

Connects QML UI with CharacterCatalogService, StoryDirectorService,
ImageGenerationService, and SlideComposer pipeline.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from PySide6.QtCore import Property, QObject, Signal, Slot
    from PySide6.QtQml import QmlNamedElement
except ImportError:  # pragma: no cover
    # Graceful stubs for headless/CI test environments without GUI libraries
    class QObject:  # type: ignore[no-redef]
        def __init__(self, parent=None):
            self._parent = parent

    def Signal(*args, **kwargs):  # type: ignore[no-redef]
        class _Signal:
            def __init__(self):
                self._slots = []

            def connect(self, slot):
                self._slots.append(slot)

            def emit(self, *a, **kw):
                for s in list(self._slots):
                    try:
                        s(*a, **kw)
                    except Exception:
                        pass
        return _Signal()

    def Slot(*args, **kwargs):  # type: ignore[no-redef]
        def decorator(fn):
            return fn
        return decorator

    def Property(*args, **kwargs):  # type: ignore[no-redef]
        def decorator(fn):
            return property(fn)
        return decorator

    def QmlNamedElement(name):  # type: ignore[no-redef]
        def decorator(cls):
            return cls
        return decorator

from haizflow.config import STORAGE_DIR
from haizflow.core.paths import runtime_data_dir
from haizflow.desktop.audio_preview_controller import AudioPreviewController
from haizflow.pipeline.slide_composer import compose_article_video, generate_scenes_narration
from haizflow.schemas.article_video import (
    ArticleProjectConfig,
    ArticleScene,
    ArticleVideoProject,
    AspectRatio,
    CharacterPreset,
    ImageStyle,
    VoiceProvider,
)
from haizflow.services.character_catalog import (
    add_custom_character,
    get_character_by_id,
    list_characters,
    reset_custom_characters,
    resolve_character_avatar_path,
)
from haizflow.services.image_generator import (
    generate_scene_image,
    generate_scenes_images,
    get_effective_gemini_api_key,
    get_effective_pollen_key,
    import_custom_scene_image,
)
from haizflow.services.story_director import direct_article

LOGGER = logging.getLogger(__name__)

QML_IMPORT_NAME = "HaizFlow"
QML_IMPORT_MAJOR_VERSION = 1


@QmlNamedElement("ArticleVideoController")
class ArticleVideoController(QObject):
    """Controller managing the Article-to-Video lifecycle and UI presentation."""

    # UI Notification Signals
    articleTextChanged = Signal()
    selectedCharacterIdChanged = Signal()
    imageCountTargetChanged = Signal()
    imageStyleChanged = Signal()
    aspectRatioChanged = Signal()
    ttsProviderChanged = Signal()
    ttsVoiceChanged = Signal()
    ttsSpeedChanged = Signal()
    configSavedMessageChanged = Signal()
    bgmPathChanged = Signal()
    bgmFileNameChanged = Signal()
    bgmVolumeChanged = Signal()
    bgmPreviewSourceChanged = Signal()
    bgmPreviewStateChanged = Signal()
    statusChanged = Signal()
    progressPercentChanged = Signal()
    progressMessageChanged = Signal()
    scenesChanged = Signal()
    charactersChanged = Signal()
    outputVideoPathChanged = Signal()
    lastErrorMessageChanged = Signal()
    operationCompleted = Signal(str)
    operationFailed = Signal(str, str)
    voicePreviewSourceChanged = Signal()
    voicePreviewStateChanged = Signal()
    googleApiKeyConfiguredChanged = Signal()
    youtubeConnectedChanged = Signal()
    youtubeChannelTitleChanged = Signal()
    isUploadingYoutubeChanged = Signal()
    youtubeUploadProgressChanged = Signal()
    youtubeUploadMessageChanged = Signal()
    youtubeVideoUrlChanged = Signal()
    youtubePrivacyChanged = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._article_text: str = ""
        self._selected_character_id: str = "none"
        self._image_count_target: int = 1
        self._image_style: ImageStyle = "anime_2d"
        self._aspect_ratio: AspectRatio = "16:9"
        self._tts_provider: VoiceProvider = "edge"
        self._tts_voice: str = "vi-VN-NamMinhNeural"
        self._tts_speed: float = 1.0
        self._config_saved_message: str = ""
        self._bgm_path: str = ""
        self._bgm_volume: float = 0.15
        self._bgm_preview_source: str = ""
        self._is_bgm_preview_playing: bool = False
        self._bgm_preview_status: str = ""

        self._voice_preview_source: str = ""
        self._is_voice_preview_playing: bool = False
        self._voice_preview_status: str = ""

        self._youtube_connected: bool = False
        self._youtube_channel_title: str = ""
        self._is_uploading_youtube: bool = False
        self._youtube_upload_progress: int = 0
        self._youtube_upload_message: str = ""
        self._youtube_video_url: str = ""
        self._youtube_privacy: str = "private"

        self._status: str = "idle"  # idle, analyzing, generating_images, rendering_video, done, error
        self._progress_percent: int = 0
        self._progress_message: str = ""
        self._scenes: List[Dict[str, Any]] = []
        self._characters: List[Dict[str, Any]] = []
        self._output_video_path: str = ""
        self._last_error_message: str = ""

        self._current_project: Optional[ArticleVideoProject] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._cancel_requested: threading.Event = threading.Event()

        # Initialize character catalog and YouTube status
        self.loadCharacters()
        self.refreshYouTubeStatus()

    def _sync_active_config(self) -> None:
        """Synchronize all active UI configuration values to the project manifest."""
        if not self._current_project:
            return
        cfg = self._current_project.config
        cfg.aspect_ratio = self._aspect_ratio
        cfg.image_style = self._image_style
        cfg.voice_provider = self._tts_provider
        cfg.voice_id = self._tts_voice
        cfg.voice_rate = self._tts_speed
        cfg.character_id = self._selected_character_id
        cfg.image_count_target = self._image_count_target
        cfg.background_music_path = self._bgm_path
        cfg.background_music_volume = self._bgm_volume

    def _invalidate_project_narration(self) -> None:
        """Clear cached audio paths on scenes when voice/speed settings change."""
        if not self._current_project:
            return
        for scene in self._current_project.scenes:
            scene.audio_path = ""
            scene.duration_ms = 0
        self._sync_scenes_model()

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @Property(str, notify=articleTextChanged)
    def articleText(self) -> str:
        return self._article_text

    @Slot(str)
    def setArticleText(self, text: str) -> None:
        val = str(text or "")
        if self._article_text != val:
            self._article_text = val
            if self._current_project:
                self._current_project.config.article_text = val
            self.articleTextChanged.emit()

    @Property(str, notify=selectedCharacterIdChanged)
    def selectedCharacterId(self) -> str:
        return self._selected_character_id

    @Slot(str)
    def selectCharacter(self, character_id: str) -> None:
        val = str(character_id or "").strip()
        if self._selected_character_id != val:
            self._selected_character_id = val
            if self._current_project:
                self._current_project.config.character_id = val
            self.selectedCharacterIdChanged.emit()

    @Property(int, notify=imageCountTargetChanged)
    def imageCountTarget(self) -> int:
        return self._image_count_target

    @Slot(int)
    def setImageCountTarget(self, count: int) -> None:
        val = max(1, min(10, int(count)))
        if self._image_count_target != val:
            self._image_count_target = val
            if self._current_project:
                self._current_project.config.image_count_target = val
            self.imageCountTargetChanged.emit()

    @Property(str, notify=imageStyleChanged)
    def imageStyle(self) -> str:
        return self._image_style

    @Slot(str)
    def setImageStyle(self, style: str) -> None:
        val = str(style or "anime_2d").strip()
        if val in ("anime_2d", "manhwa_webtoon", "watercolor", "cyberpunk", "comic_book", "cinematic"):
            self._image_style = val  # type: ignore[assignment]
            if self._current_project:
                self._current_project.config.image_style = val  # type: ignore[assignment]
            self.imageStyleChanged.emit()

    @Property(str, notify=aspectRatioChanged)
    def aspectRatio(self) -> str:
        return self._aspect_ratio

    @Slot(str)
    def setAspectRatio(self, ratio: str) -> None:
        val = str(ratio or "16:9").strip()
        if val in ("16:9", "9:16", "1:1"):
            self._aspect_ratio = val  # type: ignore[assignment]
            if self._current_project:
                self._current_project.config.aspect_ratio = val  # type: ignore[assignment]
            self.aspectRatioChanged.emit()

    @Property(str, notify=ttsProviderChanged)
    def ttsProvider(self) -> str:
        return self._tts_provider

    @Slot(str)
    def setTtsProvider(self, provider: str) -> None:
        val = str(provider or "edge").strip().lower()
        if val in ("vieneu", "vieneu-gpu", "edge", "omnivoice"):
            self._tts_provider = val  # type: ignore[assignment]
            if self._current_project:
                self._current_project.config.voice_provider = val  # type: ignore[assignment]
                self._invalidate_project_narration()
            self.ttsProviderChanged.emit()

    @Property(str, notify=ttsVoiceChanged)
    def ttsVoice(self) -> str:
        return self._tts_voice

    @Slot(str)
    def setTtsVoice(self, voice: str) -> None:
        val = str(voice or "").strip()
        if self._tts_voice != val:
            self._tts_voice = val
            if self._current_project:
                self._current_project.config.voice_id = val
                self._invalidate_project_narration()
            self.ttsVoiceChanged.emit()

    @Property(float, notify=ttsSpeedChanged)
    def ttsSpeed(self) -> float:
        return self._tts_speed

    @Slot(float)
    def setTtsSpeed(self, speed: float) -> None:
        val = max(0.5, min(2.0, float(speed)))
        if abs(self._tts_speed - val) > 0.01:
            self._tts_speed = val
            if self._current_project:
                self._current_project.config.voice_rate = val
                self._invalidate_project_narration()
            self.ttsSpeedChanged.emit()

    @Property(str, notify=configSavedMessageChanged)
    def configSavedMessage(self) -> str:
        return self._config_saved_message

    @Slot()
    def saveConfig(self) -> None:
        """Explicitly confirm and save current voice, ratio, and style settings."""
        self._sync_active_config()
        ratio_label = "9:16 (Shorts)" if self._aspect_ratio == "9:16" else ("1:1 (Vuông)" if self._aspect_ratio == "1:1" else "16:9 (YouTube)")
        voice_label = self._tts_voice.split(":")[-1] if ":" in self._tts_voice else self._tts_voice
        msg = f"Đã lưu & áp dụng cấu hình: Tỷ lệ {ratio_label} • Giọng {voice_label} • Tốc độ {self._tts_speed:.1f}x • Phong cách {self._image_style}"
        self._config_saved_message = msg
        self.configSavedMessageChanged.emit()
        self._set_status("idle", 100, msg)
        self.operationCompleted.emit("save_config")

    @Property(str, notify=bgmPathChanged)
    def bgmPath(self) -> str:
        return self._bgm_path

    @Property(str, notify=bgmFileNameChanged)
    def bgmFileName(self) -> str:
        if not self._bgm_path:
            return ""
        clean = str(self._bgm_path).strip().lower()
        if clean in ("none", "off"):
            return "Tắt nhạc nền"
        if clean in ("default", "news", "true"):
            return "Nhạc nền mặc định (Inspiring)"
        return Path(self._bgm_path).name

    def _resolve_bgm_path(self) -> Optional[Path]:
        clean = str(self._bgm_path or "").strip().lower()
        if clean in ("none", "off"):
            return None
        if not self._bgm_path or clean in ("default", "news", "true"):
            try:
                from haizflow.pipeline.slide_composer import get_or_generate_news_bgm
                bgm = get_or_generate_news_bgm()
                return bgm if bgm.is_file() else None
            except Exception:
                return None
        p = Path(self._bgm_path)
        if p.is_file():
            return p
        try:
            from haizflow.pipeline.slide_composer import get_or_generate_news_bgm
            bgm = get_or_generate_news_bgm()
            return bgm if bgm.is_file() else None
        except Exception:
            return None

    @Property(str, notify=bgmPreviewSourceChanged)
    def bgmPreviewSource(self) -> str:
        return self._bgm_preview_source

    @Property(bool, notify=bgmPreviewStateChanged)
    def isBgmPreviewPlaying(self) -> bool:
        return self._is_bgm_preview_playing

    @Property(str, notify=bgmPreviewStateChanged)
    def bgmPreviewStatus(self) -> str:
        return self._bgm_preview_status

    @Slot(str)
    def setBgmPath(self, path: str) -> None:
        clean = str(path or "").strip()
        if clean.startswith("file:///"):
            clean = clean.replace("file:///", "")
        elif clean.startswith("file://"):
            clean = clean.replace("file://", "")
        if sys.platform == "win32" and "/" in clean:
            clean = clean.replace("/", "\\")

        if self._bgm_path != clean:
            self._bgm_path = clean
            if self._current_project:
                self._current_project.config.background_music_path = clean
            self.bgmPathChanged.emit()
            self.bgmFileNameChanged.emit()
            if self._is_bgm_preview_playing:
                self.stopBgmPreview()

    @Slot()
    def setDefaultBgm(self) -> None:
        self.setBgmPath("default")

    @Slot()
    def disableBgm(self) -> None:
        self.setBgmPath("none")

    @Property(float, notify=bgmVolumeChanged)
    def bgmVolume(self) -> float:
        return self._bgm_volume

    @Slot(float)
    def setBgmVolume(self, volume: float) -> None:
        val = max(0.0, min(1.0, float(volume)))
        if abs(self._bgm_volume - val) > 0.01:
            self._bgm_volume = val
            if self._current_project:
                self._current_project.config.background_music_volume = val
            self.bgmVolumeChanged.emit()

    @Slot(result=str)
    def previewBgm(self) -> str:
        """Resolve and trigger playback for the selected background music file."""
        bgm_file = self._resolve_bgm_path()
        if not bgm_file or not bgm_file.is_file():
            self._bgm_preview_status = "Đã tắt nhạc nền hoặc tệp không tồn tại."
            self.bgmPreviewStateChanged.emit()
            return ""

        url = bgm_file.resolve().as_uri()
        self._bgm_preview_source = url
        self._is_bgm_preview_playing = True
        self._bgm_preview_status = f"Đang phát: {bgm_file.name}"
        self.bgmPreviewSourceChanged.emit()
        self.bgmPreviewStateChanged.emit()
        return url

    @Slot()
    def stopBgmPreview(self) -> None:
        """Stop background music preview playback."""
        self._is_bgm_preview_playing = False
        self._bgm_preview_status = ""
        self.bgmPreviewStateChanged.emit()

    # -------------------------------------------------------------------------
    # YouTube Integration
    # -------------------------------------------------------------------------

    def refreshYouTubeStatus(self) -> None:
        """Refresh local YouTube connection state and channel title."""
        try:
            from haizflow.services import youtube_direct
            token = youtube_direct.get_saved_token()
            self._youtube_connected = bool(token)
            if self._youtube_connected:
                info = youtube_direct.get_channel_info()
                self._youtube_channel_title = str(info.get("title", "") or "Kênh YouTube")
            else:
                self._youtube_channel_title = ""
        except Exception as exc:
            LOGGER.debug("Could not refresh YouTube status: %s", exc)
            try:
                from haizflow.services import youtube_direct
                self._youtube_connected = bool(youtube_direct.get_saved_token())
            except Exception:
                self._youtube_connected = False
            self._youtube_channel_title = "Kênh đã kết nối" if self._youtube_connected else ""
        self.youtubeConnectedChanged.emit()
        self.youtubeChannelTitleChanged.emit()

    @Property(bool, notify=youtubeConnectedChanged)
    def youtubeConnected(self) -> bool:
        return self._youtube_connected

    @Property(str, notify=youtubeChannelTitleChanged)
    def youtubeChannelTitle(self) -> str:
        return self._youtube_channel_title

    @Property(bool, notify=isUploadingYoutubeChanged)
    def isUploadingYoutube(self) -> bool:
        return self._is_uploading_youtube

    @Property(int, notify=youtubeUploadProgressChanged)
    def youtubeUploadProgress(self) -> int:
        return self._youtube_upload_progress

    @Property(str, notify=youtubeUploadMessageChanged)
    def youtubeUploadMessage(self) -> str:
        return self._youtube_upload_message

    @Property(str, notify=youtubeVideoUrlChanged)
    def youtubeVideoUrl(self) -> str:
        return self._youtube_video_url

    @Property(str, notify=youtubePrivacyChanged)
    def youtubePrivacy(self) -> str:
        return self._youtube_privacy

    @Slot(str)
    def setYoutubePrivacy(self, privacy: str) -> None:
        val = str(privacy or "public").strip().lower()
        if val not in ("public", "unlisted", "private"):
            val = "public"
        if self._youtube_privacy != val:
            self._youtube_privacy = val
            self.youtubePrivacyChanged.emit()

    @Slot()
    def checkYouTubeConnection(self) -> None:
        self.refreshYouTubeStatus()

    @Slot()
    def connectYouTube(self) -> None:
        """Start YouTube OAuth flow in background."""
        def worker() -> None:
            try:
                from haizflow.services import youtube_direct
                youtube_direct.start_oauth_flow()
                self.refreshYouTubeStatus()
            except Exception as exc:
                LOGGER.warning("YouTube OAuth failed: %s", exc)
                self._set_error(f"Lỗi xác thực YouTube: {exc}")
        threading.Thread(target=worker, name="article-yt-oauth", daemon=True).start()

    @Slot()
    def disconnectYouTube(self) -> None:
        """Remove saved YouTube token."""
        try:
            from haizflow.services import youtube_direct
            youtube_direct.clear_saved_token()
            self._youtube_connected = False
            self._youtube_channel_title = ""
            self.youtubeConnectedChanged.emit()
            self.youtubeChannelTitleChanged.emit()
        except Exception as exc:
            LOGGER.warning("Disconnect YouTube error: %s", exc)

    @Slot()
    def uploadToYouTube(self) -> None:
        self.uploadToYouTubeWithParams("", "", "")

    @Slot(str, str, str)
    def uploadToYouTubeWithParams(self, custom_title: str = "", custom_desc: str = "", custom_tags: str = "") -> None:
        """Upload current rendered video to YouTube / Shorts."""
        if self._is_uploading_youtube:
            return
        if not self._output_video_path or not Path(self._output_video_path).is_file():
            self._set_error("Chưa có video được xuất bản để tải lên YouTube. Hãy bấm 'Xuất Video 1080p' trước.")
            return

        from haizflow.services import youtube_direct
        if not youtube_direct.get_saved_token():
            self._set_error("Chưa kết nối tài khoản YouTube. Vui lòng kết nối tài khoản trước.")
            return

        self._sync_active_config()
        self._is_uploading_youtube = True
        self._youtube_upload_progress = 0
        self._youtube_upload_message = "Đang kết nối Google YouTube API..."
        self._youtube_video_url = ""
        self.isUploadingYoutubeChanged.emit()
        self.youtubeUploadProgressChanged.emit()
        self.youtubeUploadMessageChanged.emit()
        self.youtubeVideoUrlChanged.emit()

        # Format title, description, tags
        is_shorts = (self._aspect_ratio == "9:16")
        default_title = self._current_project.project_name if self._current_project else "Phim Ngắn Đọc Truyện AI"
        raw_title = custom_title.strip() if custom_title.strip() else default_title
        if is_shorts and "#Shorts" not in raw_title and "#shorts" not in raw_title:
            title = f"{raw_title[:88].strip()} #Shorts"
        else:
            title = raw_title[:100]

        if custom_desc.strip():
            desc = custom_desc.strip()
        else:
            excerpt = (self._article_text[:400] + "...") if len(self._article_text) > 400 else self._article_text
            if is_shorts:
                desc = f"{title}\n\n{excerpt}\n\n#Shorts #TruyenNgan #PhimNgan #KichBanAI"
            else:
                desc = f"{title}\n\n{excerpt}\n\nVideo được tạo tự động bởi AI."

        if custom_tags.strip():
            tags = [t.strip("# ") for t in custom_tags.split() if t.strip("# ") and t.strip("# ").lower() != "haizflow"]
        else:
            tags = ["Shorts", "TruyenNgan", "PhimNgan", "AI"] if is_shorts else ["TruyenNgan", "PhimNgan", "AI"]

        def worker() -> None:
            try:
                def progress_cb(pct: int, msg: str):
                    self._youtube_upload_progress = pct
                    self._youtube_upload_message = msg
                    self.youtubeUploadProgressChanged.emit()
                    self.youtubeUploadMessageChanged.emit()

                res = youtube_direct.upload_video_to_youtube(
                    video_path=self._output_video_path,
                    title=title,
                    description=desc,
                    tags=tags,
                    privacy_status=self._youtube_privacy,
                    progress_callback=progress_cb,
                    cancel_event=self._cancel_requested,
                )
                v_id = res.get("video_id", "")
                v_url = res.get("url", f"https://youtu.be/{v_id}")
                self._youtube_video_url = v_url
                self._youtube_upload_progress = 100
                self._youtube_upload_message = f"Đã đăng lên YouTube thành công! Link: {v_url}"
                self._is_uploading_youtube = False
                self.youtubeVideoUrlChanged.emit()
                self.youtubeUploadProgressChanged.emit()
                self.youtubeUploadMessageChanged.emit()
                self.isUploadingYoutubeChanged.emit()
                self.operationCompleted.emit("youtube_upload")
            except Exception as exc:
                LOGGER.exception("YouTube upload failed")
                self._is_uploading_youtube = False
                self._youtube_upload_message = f"Lỗi tải lên YouTube: {exc}"
                self._set_error(f"Lỗi tải lên YouTube: {exc}")
                self.isUploadingYoutubeChanged.emit()
                self.youtubeUploadMessageChanged.emit()
                self.operationFailed.emit("youtube_upload", str(exc))

        threading.Thread(target=worker, name="article-yt-upload", daemon=True).start()

    @Slot()
    def openYouTubeVideo(self) -> None:
        """Open the uploaded YouTube video in browser."""
        if self._youtube_video_url:
            import webbrowser
            webbrowser.open(self._youtube_video_url)

    @Slot(bool)
    def setBgmPreviewPlaying(self, playing: bool) -> None:
        """Update playback state from QML MediaPlayer."""
        self._is_bgm_preview_playing = bool(playing)
        if not playing:
            self._bgm_preview_status = ""
        self.bgmPreviewStateChanged.emit()

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(bool, notify=statusChanged)
    def isBusy(self) -> bool:
        return self._status in ("analyzing", "generating_images", "rendering_video")

    @Property(int, notify=progressPercentChanged)
    def progressPercent(self) -> int:
        return self._progress_percent

    @Property(str, notify=progressMessageChanged)
    def progressMessage(self) -> str:
        return self._progress_message

    @Property("QVariantList", notify=scenesChanged)
    def scenes(self) -> List[Dict[str, Any]]:
        return self._scenes

    @Property(int, notify=scenesChanged)
    def scenesCount(self) -> int:
        return len(self._scenes)

    @Property("QVariantList", notify=charactersChanged)
    def characters(self) -> List[Dict[str, Any]]:
        return self._characters

    @Property(str, notify=outputVideoPathChanged)
    def outputVideoPath(self) -> str:
        return self._output_video_path

    @Property(str, notify=lastErrorMessageChanged)
    def lastErrorMessage(self) -> str:
        return self._last_error_message

    @Property(bool, notify=scenesChanged)
    def hasProject(self) -> bool:
        return self._current_project is not None and len(self._scenes) > 0

    @Property(str, notify=voicePreviewSourceChanged)
    def voicePreviewSource(self) -> str:
        return self._voice_preview_source

    @Property(bool, notify=voicePreviewStateChanged)
    def isVoicePreviewPlaying(self) -> bool:
        return self._is_voice_preview_playing

    @Property(str, notify=voicePreviewStateChanged)
    def voicePreviewStatus(self) -> str:
        return self._voice_preview_status

    @Property(bool, notify=googleApiKeyConfiguredChanged)
    def hasGoogleApiKey(self) -> bool:
        return bool(get_effective_gemini_api_key())

    @Property(str, notify=googleApiKeyConfiguredChanged)
    def googleApiKeyMasked(self) -> str:
        key = get_effective_gemini_api_key()
        if not key:
            return ""
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    @Property(bool, notify=googleApiKeyConfiguredChanged)
    def hasPollenKey(self) -> bool:
        return bool(get_effective_pollen_key())

    @Property(str, notify=googleApiKeyConfiguredChanged)
    def pollenKeyMasked(self) -> str:
        key = get_effective_pollen_key()
        if not key:
            return ""
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    @Property(str, notify=googleApiKeyConfiguredChanged)
    def activeAiEngineName(self) -> str:
        if self.hasPollenKey:
            return "Pollinations AI (Tốc độ cao - Không giới hạn)"
        return "Cổng AI Trực tuyến Miễn phí (Pollinations)"

    @Property(str, notify=googleApiKeyConfiguredChanged)
    def activeAiEngineSubtitle(self) -> str:
        if self.hasPollenKey:
            return f"Pollen Key: {self.pollenKeyMasked} • Tạo ảnh liên tục không chờ"
        if self.hasGoogleApiKey:
            return f"Google Key: {self.googleApiKeyMasked} (Dùng cho Kịch bản) • Tạo ảnh miễn phí thuần Việt"
        return "Miễn phí 100%, tự động tạo ảnh thuần Việt sắc nét."

    # -------------------------------------------------------------------------
    # Core Operations
    # -------------------------------------------------------------------------

    @Slot()
    def loadCharacters(self) -> None:
        """Load character presets from the 2D library."""
        presets = list_characters()
        character_list: List[Dict[str, Any]] = []
        for p in presets:
            character_list.append({
                "id": p.id,
                "name": p.display_name,
                "gender": p.gender,
                "age_group": p.age_group,
                "thumbnail": p.thumbnail or "",
                "description": p.description,
                "style_tag": p.style_tag,
            })
        self._characters = character_list
        if self._selected_character_id and self._selected_character_id != "none":
            if not any(c["id"] == self._selected_character_id for c in character_list):
                self._selected_character_id = "none"
                self.selectedCharacterIdChanged.emit()
        self.charactersChanged.emit()

    def _sync_scenes_model(self) -> None:
        """Synchronize _scenes list from _current_project.scenes."""
        if not self._current_project:
            self._scenes = []
        else:
            self._scenes = [
                {
                    "scene_index": s.scene_index,
                    "text": s.text,
                    "duration_ms": s.duration_ms,
                    "duration_sec": s.duration_ms / 1000.0,
                    "image_path": s.image_path or "",
                    "image_prompt": s.image_prompt,
                    "visual_priority_score": s.visual_priority_score,
                    "has_image": s.has_image,
                    "has_image_file": bool(s.image_path and Path(s.image_path).is_file()),
                }
                for s in self._current_project.scenes
            ]
        self.scenesChanged.emit()

    @Slot()
    def analyzeStory(self) -> None:
        """Analyze article text, direct scenes, and attach character prompt anchors."""
        if self.isBusy:
            return

        text = self._article_text.strip()
        if not text:
            self._set_error("Vui lòng nhập nội dung bài viết trước khi phân tích.")
            return

        self._set_status("analyzing", 10, "Đang phân tích bài viết và phân đoạn kịch bản...")
        self._cancel_requested.clear()

        def worker() -> None:
            try:
                config = ArticleProjectConfig(
                    article_text=text,
                    voice_provider=self._tts_provider,
                    voice_id=self._tts_voice,
                    voice_rate=self._tts_speed,
                    image_style=self._image_style,
                    character_id=self._selected_character_id,
                    image_count_target=self._image_count_target,
                    aspect_ratio=self._aspect_ratio,
                    background_music_path=self._bgm_path,
                    background_music_volume=self._bgm_volume,
                )

                scenes = direct_article(config)

                title = text[:40].replace("\n", " ").strip()
                self._current_project = ArticleVideoProject(
                    project_id=uuid.uuid4().hex[:12],
                    project_name=title,
                    config=config,
                    scenes=scenes,
                    status="analyzed",
                )
                self._sync_scenes_model()
                self._set_status("idle", 100, f"Phân tích hoàn tất: {len(scenes)} phân cảnh đã sẵn sàng.")
                self.operationCompleted.emit("analyze")
            except Exception as exc:
                LOGGER.exception("Failed to direct article story")
                self._set_error(f"Lỗi phân tích kịch bản: {exc}")
                self.operationFailed.emit("analyze", str(exc))

        self._worker_thread = threading.Thread(target=worker, name="article-director", daemon=True)
        self._worker_thread.start()

    @Slot()
    def generateImages(self) -> None:
        """Generate illustrations for all scenes requiring visual imagery."""
        if self.isBusy:
            return
        if not self._current_project or not self._current_project.scenes:
            self._set_error("Chưa có phân cảnh nào để tạo ảnh. Hãy bấm 'Phân tích kịch bản' trước.")
            return

        self._sync_active_config()
        self._set_status("generating_images", 5, "Đang khởi động tiến trình tạo ảnh minh họa...")
        self._cancel_requested.clear()

        def worker() -> None:
            try:
                output_dir = Path(STORAGE_DIR) / "article_projects" / self._current_project.project_id / "images"
                output_dir.mkdir(parents=True, exist_ok=True)

                def progress_cb(pct: int, msg: str) -> None:
                    if self._cancel_requested.is_set():
                        return
                    self._set_status("generating_images", pct, msg)

                generate_scenes_images(
                    scenes=self._current_project.scenes,
                    config=self._current_project.config,
                    output_dir=output_dir,
                    progress_callback=progress_cb,
                    cancel_event=self._cancel_requested,
                )

                self._current_project.status = "images_ready"
                self._sync_scenes_model()
                self._set_status("idle", 100, "Đã tạo đầy đủ ảnh minh họa cho các phân cảnh!")
                self.operationCompleted.emit("generate_images")
            except Exception as exc:
                LOGGER.exception("Failed to generate scene images")
                self._set_error(f"Lỗi tạo ảnh minh họa: {exc}")
                self.operationFailed.emit("generate_images", str(exc))

        self._worker_thread = threading.Thread(target=worker, name="article-image-gen", daemon=True)
        self._worker_thread.start()

    @Slot(int, str)
    def replaceSceneImage(self, scene_index: int, image_file_path: str) -> None:
        """Import a local custom image for a specific scene."""
        if not self._current_project or not self._current_project.scenes:
            return
        if scene_index < 0 or scene_index >= len(self._current_project.scenes):
            return

        path = Path(image_file_path.strip().replace("file:///", "").replace("file://", ""))
        if not path.is_file():
            self._set_error("Tệp hình ảnh không tồn tại.")
            return

        try:
            target_scene = self._current_project.scenes[scene_index]
            output_dir = Path(STORAGE_DIR) / "article_projects" / self._current_project.project_id / "images"
            output_dir.mkdir(parents=True, exist_ok=True)
            dest_file = output_dir / f"scene_{target_scene.scene_index:03d}_custom.jpg"

            import_custom_scene_image(
                source_path=path,
                destination_path=dest_file,
                aspect_ratio=self._aspect_ratio,
            )
            target_scene.image_path = str(dest_file.resolve())
            target_scene.has_image = True
            self._sync_scenes_model()
            self._set_status("idle", 100, f"Đã thay thế ảnh cho phân cảnh {scene_index + 1}!")
            self.operationCompleted.emit("replace_image")
        except Exception as exc:
            LOGGER.exception("Failed to import custom scene image")
            self._set_error(f"Lỗi thay thế ảnh: {exc}")

    @Slot(int)
    def pickSceneImage(self, scene_index: int) -> None:
        """Open native file dialog to replace a scene's illustration with a local image."""
        try:
            from haizflow.desktop.localization import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                None,
                f"Chọn ảnh minh họa cho phân cảnh {scene_index + 1}",
                "",
                "Image Files (*.jpg *.jpeg *.png *.webp *.bmp);;All Files (*.*)"
            )
            if path:
                self.replaceSceneImage(scene_index, path)
        except Exception as exc:
            LOGGER.warning("Could not open file dialog for scene image: %s", exc)

    @Slot(int)
    def regenerateSceneImage(self, scene_index: int) -> None:
        """Regenerate illustration for a single scene."""
        self.regenerateSceneImageWithNote(scene_index, "")

    @Slot(int, str)
    def regenerateSceneImageWithNote(self, scene_index: int, note: str = "") -> None:
        """Regenerate illustration for a single scene with optional user refinement note."""
        if self.isBusy:
            return
        if not self._current_project or scene_index < 0 or scene_index >= len(self._current_project.scenes):
            return

        target_scene = self._current_project.scenes[scene_index]
        self._set_status("generating_images", 15, f"Đang tạo lại ảnh cho phân cảnh {scene_index + 1}...")
        self._cancel_requested.clear()

        def worker() -> None:
            try:
                import random
                output_dir = Path(STORAGE_DIR) / "article_projects" / self._current_project.project_id / "images"
                output_dir.mkdir(parents=True, exist_ok=True)
                dest_file = output_dir / f"scene_{target_scene.scene_index:03d}_v{int(time.time())}.jpg"

                base_prompt = target_scene.image_prompt if target_scene.image_prompt else target_scene.text
                clean_note = str(note or "").strip()
                if clean_note:
                    from haizflow.services.story_director import translate_scene_text_to_english
                    note_lower = clean_note.lower()
                    if any(k in note_lower for k in ("chỉ có nền", "không có chi tiết", "thiếu chi tiết", "nền trống", "vẽ lại", "vẽ thêm")):
                        extra_dir = (
                            "vibrant richly detailed scene, prominent focal subjects and human action, "
                            "authentic Vietnamese characters with natural Vietnamese facial features, "
                            "authentic Vietnamese scenery and architecture, detailed background, "
                            "strictly no text, no watermark, no captions, no blank background"
                        )
                        note_en = translate_scene_text_to_english(clean_note)
                        prompt = f"{base_prompt}, specific visual direction: {extra_dir}, {note_en}"
                    else:
                        note_en = translate_scene_text_to_english(clean_note)
                        prompt = f"{base_prompt}, specific visual direction: {note_en}"
                    target_scene.image_prompt = prompt
                else:
                    prompt = base_prompt

                char_sheet: Optional[Path] = None
                char_id = target_scene.character_id or self._selected_character_id
                if char_id and char_id != "none":
                    char_preset = get_character_by_id(char_id)
                    if char_preset and char_preset.thumbnail:
                        resolved = resolve_character_avatar_path(char_preset.thumbnail)
                        if resolved.is_file():
                            char_sheet = resolved

                def scene_progress_cb(detail_msg: str) -> None:
                    if self._cancel_requested.is_set():
                        return
                    self._set_status("generating_images", 40, detail_msg)

                api_key = get_effective_gemini_api_key()
                fresh_seed = random.randint(100000, 99999999)
                generate_scene_image(
                    prompt=prompt,
                    destination_path=dest_file,
                    aspect_ratio=self._aspect_ratio,
                    style=self._image_style,
                    api_key=api_key,
                    use_cache=False,  # Bypass cache on deliberate regenerate
                    character_image_path=char_sheet,
                    progress_callback=scene_progress_cb,
                    cancel_event=self._cancel_requested,
                    seed=fresh_seed,
                )
                target_scene.image_path = str(dest_file.resolve())
                target_scene.has_image = True
                self._sync_scenes_model()
                self._set_status("idle", 100, f"Đã tạo lại ảnh phân cảnh {scene_index + 1} thành công!")
                self.operationCompleted.emit("regenerate_image")
            except Exception as exc:
                LOGGER.exception("Failed to regenerate scene image")
                self._set_error(f"Lỗi tạo lại ảnh: {exc}")
                self.operationFailed.emit("regenerate_image", str(exc))

        self._worker_thread = threading.Thread(target=worker, name="article-regen-img", daemon=True)
        self._worker_thread.start()

    @Slot()
    def renderVideo(self) -> None:
        """Render the complete YouTube video with Ken Burns motion, narration, and BGM."""
        if self.isBusy:
            return
        if not self._current_project or not self._current_project.scenes:
            self._set_error("Chưa có dự án hoặc phân cảnh nào để dựng video.")
            return

        # Ensure project config carries current UI choices (Ratio, Voice, Speed, Style, BGM, etc.)
        self._sync_active_config()

        is_shorts = (self._aspect_ratio == "9:16")
        init_status = "Đang chuẩn bị dựng video YouTube Shorts (9:16)..." if is_shorts else "Đang chuẩn bị dựng video YouTube chuẩn 1080p..."
        self._set_status("rendering_video", 5, init_status)
        self._cancel_requested.clear()

        def worker() -> None:
            try:
                output_dir = Path(STORAGE_DIR) / "article_videos"
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = int(time.time())
                output_file = output_dir / f"article_video_{'shorts_' if is_shorts else ''}{timestamp}.mp4"

                # 1. Synthesize narration audio for all scenes
                audio_dir = Path(STORAGE_DIR) / "article_projects" / self._current_project.project_id / "audio"
                self._set_status("rendering_video", 5, "Đang tổng hợp giọng đọc AI cho các phân cảnh...")
                generate_scenes_narration(
                    scenes=self._current_project.scenes,
                    config=self._current_project.config,
                    output_dir=audio_dir,
                    progress_callback=lambda pct, msg: self._set_status("rendering_video", pct, msg) if not self._cancel_requested.is_set() else None,
                    cancel_event=self._cancel_requested,
                )

                # 2. Ensure scene images exist if any scene needs an image
                img_dir = Path(STORAGE_DIR) / "article_projects" / self._current_project.project_id / "images"
                generate_scenes_images(
                    scenes=self._current_project.scenes,
                    config=self._current_project.config,
                    output_dir=img_dir,
                    cancel_event=self._cancel_requested,
                )

                def progress_cb(pct: int, msg: str) -> None:
                    if self._cancel_requested.is_set():
                        return
                    self._set_status("rendering_video", pct, msg)

                final_path = compose_article_video(
                    project=self._current_project,
                    output_video_path=output_file,
                    progress_callback=progress_cb,
                    cancel_event=self._cancel_requested,
                )

                self._output_video_path = str(final_path)
                self._current_project.status = "rendered"
                self.outputVideoPathChanged.emit()
                done_msg = f"Xuất video YouTube Shorts (9:16) thành công! File: {final_path.name}" if is_shorts else f"Xuất video YouTube 1080p thành công! File: {final_path.name}"
                self._set_status("done", 100, done_msg)
                self.operationCompleted.emit("render")
            except Exception as exc:
                LOGGER.exception("Failed to compose article video")
                self._set_error(f"Lỗi dựng video: {exc}")
                self.operationFailed.emit("render", str(exc))

        self._worker_thread = threading.Thread(target=worker, name="article-video-render", daemon=True)
        self._worker_thread.start()

    @Slot()
    def openOutputVideo(self) -> None:
        """Open the rendered video with the OS default player."""
        if not self._output_video_path or not Path(self._output_video_path).is_file():
            return
        flags = 0x08000000 if sys.platform == "win32" else 0
        try:
            if sys.platform == "win32":
                os.startfile(self._output_video_path)
            else:
                subprocess.Popen(["xdg-open", self._output_video_path], creationflags=flags)
        except Exception as exc:
            LOGGER.warning("Could not launch default player for %s: %s", self._output_video_path, exc)

    @Slot()
    def openOutputFolder(self) -> None:
        """Open Windows Explorer highlighting the rendered video."""
        if not self._output_video_path or not Path(self._output_video_path).is_file():
            return
        flags = 0x08000000 if sys.platform == "win32" else 0
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer.exe", f"/select,{self._output_video_path}"], creationflags=flags)
            else:
                subprocess.Popen(["xdg-open", str(Path(self._output_video_path).parent)], creationflags=flags)
        except Exception as exc:
            LOGGER.warning("Could not open folder for %s: %s", self._output_video_path, exc)

    @Slot(str)
    def importArticleFromFile(self, file_path: str) -> None:
        """Load article text from a UTF-8 text file."""
        clean_path = Path(file_path.strip().replace("file:///", "").replace("file://", ""))
        if not clean_path.is_file():
            self._set_error(f"Tệp không tồn tại: {clean_path}")
            return
        try:
            content = clean_path.read_text(encoding="utf-8")
            self.setArticleText(content)
        except Exception as exc:
            self._set_error(f"Không thể đọc tệp văn bản: {exc}")

    @Slot(result=str)
    def pickArticleTextFile(self) -> str:
        """Open native dialog to pick a UTF-8 text file."""
        try:
            from haizflow.desktop.localization import QFileDialog
            path, _ = QFileDialog.getOpenFileName(None, "Chọn tệp văn bản bài viết", "", "Text Files (*.txt);;All Files (*.*)")
            if path:
                self.importArticleFromFile(path)
                return str(path)
        except Exception as exc:
            LOGGER.warning("Could not open file dialog: %s", exc)
        return ""

    @Slot(int, result=str)
    def pickSceneImage(self, scene_index: int) -> str:
        """Open native dialog to pick an image for a specific scene."""
        try:
            from haizflow.desktop.localization import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                None, "Chọn hình ảnh thay thế", "",
                "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)"
            )
            if path:
                self.replaceSceneImage(scene_index, path)
                return str(path)
        except Exception as exc:
            LOGGER.warning("Could not open file dialog: %s", exc)
        return ""

    @Slot(result=str)
    def pickBgmFile(self) -> str:
        """Open native dialog to pick background music audio."""
        try:
            from haizflow.desktop.localization import QFileDialog, native_media_dialog_directory

            start_dir = ""
            if self._bgm_path and Path(self._bgm_path).parent.is_dir():
                start_dir = str(Path(self._bgm_path).parent)
            else:
                start_dir = native_media_dialog_directory()

            path, _ = QFileDialog.getOpenFileName(
                None, "Chọn tệp nhạc nền", start_dir,
                "Audio Files (*.mp3 *.wav *.m4a *.aac *.ogg *.flac);;All Files (*.*)"
            )
            if path:
                self.setBgmPath(path)
                return str(path)
        except Exception as exc:
            LOGGER.warning("Could not open file dialog: %s", exc)
        return ""

    @Slot()
    def cancel(self) -> None:
        """Signal running background workers to stop."""
        self._cancel_requested.set()
        self._set_status("idle", 0, "Đã hủy tác vụ.")

    @Slot()
    def resetProject(self) -> None:
        """Reset current article video project."""
        self.stopBgmPreview()
        self.stopVoicePreview()
        self._current_project = None
        self._output_video_path = ""
        self._scenes = []
        self._set_status("idle", 0, "")
        self.outputVideoPathChanged.emit()
        self.scenesChanged.emit()

    # -------------------------------------------------------------------------
    # Voice Preview Operations
    # -------------------------------------------------------------------------

    @Slot(result=str)
    def previewVoice(self) -> str:
        """Resolve and trigger playback for the pre-recorded voice sample."""
        provider = str(self._tts_provider).strip().lower()
        voice = str(self._tts_voice).strip()

        sample_path = AudioPreviewController._packaged_sample_path(provider, voice, "vi")
        if not sample_path and provider.startswith("vieneu"):
            sample_path = AudioPreviewController._packaged_sample_path("vieneu", voice, "vi")
        if not sample_path and provider.startswith("edge"):
            sample_path = AudioPreviewController._packaged_sample_path("edge", voice, "vi")

        if sample_path and Path(sample_path).is_file():
            url = Path(sample_path).resolve().as_uri()
            self._voice_preview_source = url
            self._is_voice_preview_playing = True
            self._voice_preview_status = f"Đang phát mẫu: {voice}"
            self.voicePreviewSourceChanged.emit()
            self.voicePreviewStateChanged.emit()
            return url
        else:
            self._voice_preview_status = "Chưa có file mẫu sẵn cho giọng đọc này."
            self.voicePreviewStateChanged.emit()
            return ""

    @Slot()
    def stopVoicePreview(self) -> None:
        """Stop voice preview playback."""
        self._is_voice_preview_playing = False
        self._voice_preview_status = ""
        self.voicePreviewStateChanged.emit()

    @Slot(bool)
    def setVoicePreviewPlaying(self, playing: bool) -> None:
        """Update playback state from QML MediaPlayer."""
        self._is_voice_preview_playing = bool(playing)
        if not playing:
            self._voice_preview_status = ""
        self.voicePreviewStateChanged.emit()

    # -------------------------------------------------------------------------
    # Character Turnaround Sheet Import
    # -------------------------------------------------------------------------

    @Slot(str, str, str, result=str)
    def importCharacterSheet(self, file_path: str, display_name: str = "", prompt_anchor: str = "") -> str:
        """Import a character turnaround model sheet image from disk."""
        clean = Path(file_path.strip().replace("file:///", "").replace("file://", ""))
        if not clean.is_file():
            self._set_error(f"Tệp ảnh không tồn tại: {clean}")
            return ""

        from PIL import Image as PilImage
        try:
            with PilImage.open(clean) as img:
                img.verify()
        except Exception as exc:
            self._set_error(f"Tệp không phải là hình ảnh hợp lệ: {exc}")
            return ""

        char_id = f"char_custom_{uuid.uuid4().hex[:8]}"
        name = display_name.strip() or clean.stem.replace("_", " ").replace("-", " ").title()

        char_dir = runtime_data_dir() / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)
        dest_filename = f"{char_id}_sheet{clean.suffix.lower()}"
        dest_path = char_dir / dest_filename
        import shutil
        shutil.copy2(clean, dest_path)

        anchor = prompt_anchor.strip()
        if not anchor:
            anchor = (
                f"Consistent character portrait based on {name} reference, "
                f"highly detailed facial features, signature costume, front-facing clean portrait consistency"
            )

        preset = CharacterPreset(
            id=char_id,
            display_name=f"{name} (Tùy chỉnh)",
            gender="other",
            age_group="Tùy chỉnh",
            thumbnail=str(dest_path.resolve()),
            reference_images=[str(dest_path.resolve())],
            style_tag=self._image_style,
            prompt_anchor=anchor,
            description="Ảnh chân dung nhân vật chính diện nhập từ máy tính.",
        )

        add_custom_character(preset)
        self.loadCharacters()
        self.selectCharacter(char_id)
        self._set_status("idle", 100, f"Đã nhập ảnh chân dung nhân vật '{name}' thành công!")
        self.operationCompleted.emit("import_character")
        return char_id

    @Slot(result=str)
    def pickAndImportCharacterSheet(self) -> str:
        """Open native file dialog to import a character portrait image."""
        try:
            from haizflow.desktop.localization import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                None,
                "Chọn ảnh chân dung chính diện nhân vật (Portrait)",
                "",
                "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)"
            )
            if path:
                return self.importCharacterSheet(path)
        except Exception as exc:
            LOGGER.warning("Could not open file dialog: %s", exc)
        return ""

    @Slot(str)
    def deleteCharacter(self, character_id: str) -> None:
        """Delete an individual character preset (bundled or custom) by ID."""
        target_id = str(character_id or "").strip()
        if not target_id or target_id == "none":
            return
        from haizflow.services import character_catalog
        character_catalog.delete_character(target_id)
        if self._selected_character_id == target_id:
            self.selectCharacter("none")
        self.loadCharacters()
        self._set_status("idle", 100, "Đã xóa nhân vật khỏi danh sách.")
        self.operationCompleted.emit("delete_character")

    @Slot()
    def deleteAllCharacters(self) -> None:
        """Delete all character presets so stories generate images freely."""
        from haizflow.services import character_catalog
        character_catalog.delete_all_characters()
        self.selectCharacter("none")
        self.loadCharacters()
        self._set_status("idle", 100, "Đã xóa tất cả nhân vật. Chế độ tạo ảnh tự do đã kích hoạt.")
        self.operationCompleted.emit("delete_all_characters")

    @Slot()
    def restoreDefaultCharacters(self) -> None:
        """Restore canonical bundled character presets."""
        from haizflow.services import character_catalog
        character_catalog.restore_bundled_characters()
        self.loadCharacters()
        self._set_status("idle", 100, "Đã khôi phục danh sách nhân vật mẫu.")
        self.operationCompleted.emit("restore_characters")

    @Slot()
    def resetToDefaultCharacters(self) -> None:
        """Reset character catalog to default canonical characters."""
        from haizflow.services import character_catalog
        character_catalog.reset_custom_characters()
        character_catalog.restore_bundled_characters()
        self.loadCharacters()
        self.selectCharacter("char_my_dung")
        self._set_status("idle", 100, "Đã khôi phục danh sách nhân vật mẫu mặc định.")
        self.operationCompleted.emit("reset_characters")


    @Slot(str, result=bool)
    def saveGoogleApiKey(self, key_text: str) -> bool:
        """Save a new Google Gemini API key to secure credentials."""
        clean = str(key_text or "").strip()
        if not clean:
            self._set_error("Vui lòng nhập API Key hợp lệ.")
            return False
        try:
            from haizflow.services.gemini_translation import save_key
            save_key(clean)
            self.googleApiKeyConfiguredChanged.emit()
            self._set_status("idle", 100, "Đã lưu Google API Key thành công! Google Imagen 3 đã kích hoạt.")
            self.operationCompleted.emit("save_api_key")
            return True
        except Exception as exc:
            self._set_error(f"Không thể lưu API Key: {exc}")
            return False

    @Slot(result=bool)
    def clearGoogleApiKey(self) -> bool:
        """Clear the stored Google Gemini API key."""
        try:
            from haizflow.services.gemini_translation import clear_key
            clear_key()
            self.googleApiKeyConfiguredChanged.emit()
            self._set_status("idle", 100, "Đã xóa Google API Key. Đang dùng công cụ AI miễn phí.")
            self.operationCompleted.emit("clear_api_key")
            return True
        except Exception as exc:
            self._set_error(f"Không thể xóa API Key: {exc}")
            return False

    @Slot(str, result=bool)
    def savePollenKey(self, key_text: str) -> bool:
        """Save a new Pollen / Pollinations API key to secure credentials."""
        clean = str(key_text or "").strip()
        if not clean:
            self._set_error("Vui lòng nhập Pollen API Key hợp lệ.")
            return False
        try:
            from haizflow.services.secure_credentials import write_secret
            write_secret("HaizFlow/Pollinations/APIKey", clean)
            self.googleApiKeyConfiguredChanged.emit()
            self._set_status("idle", 100, "Đã lưu Pollen Key thành công! Kích hoạt tạo ảnh tốc độ cao không cần chờ.")
            self.operationCompleted.emit("save_pollen_key")
            return True
        except Exception as exc:
            self._set_error(f"Không thể lưu Pollen Key: {exc}")
            return False

    @Slot(result=bool)
    def clearPollenKey(self) -> bool:
        """Clear the stored Pollen / Pollinations API key."""
        try:
            from haizflow.services.secure_credentials import delete_secret
            delete_secret("HaizFlow/Pollinations/APIKey")
            self.googleApiKeyConfiguredChanged.emit()
            self._set_status("idle", 100, "Đã xóa Pollen Key. Quay lại chế độ AI miễn phí có giãn cách.")
            self.operationCompleted.emit("clear_pollen_key")
            return True
        except Exception as exc:
            self._set_error(f"Không thể xóa Pollen Key: {exc}")
            return False

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _set_status(self, status: str, progress: int, message: str) -> None:
        self._status = status
        self._progress_percent = progress
        self._progress_message = message
        self.statusChanged.emit()
        self.progressPercentChanged.emit()
        self.progressMessageChanged.emit()

    def _set_error(self, message: str) -> None:
        LOGGER.error("[ArticleVideo] %s", message)
        self._last_error_message = message
        self._status = "error"
        self._progress_message = message
        self.lastErrorMessageChanged.emit()
        self.statusChanged.emit()
        self.progressMessageChanged.emit()
