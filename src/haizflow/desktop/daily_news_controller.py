"""Daily News Desktop Controller.

Connects QML UI with Daily World News generation pipeline,
history archives, Windows Task Scheduler, and automated social uploading
(YouTube & Facebook).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PySide6.QtCore import Property, QObject, Signal, Slot
    from PySide6.QtQml import QmlNamedElement
except ImportError:  # pragma: no cover
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

from haizflow.config import RUNTIME_DATA_DIR
from haizflow.core.paths import runtime_data_dir
from haizflow.services.daily_news import (
    ensure_date_in_title,
    export_editorial_script_file,
    format_youtube_description_with_sources,
    get_editorial_scripts_dir,
    produce_daily_news_video,
    retroactive_export_all_daily_news_scripts,
)
from haizflow.services import youtube_direct, zernio, zernio_keys

LOGGER = logging.getLogger(__name__)

SETTINGS_FILE = Path(RUNTIME_DATA_DIR) / "daily_news_settings.json"
QML_IMPORT_NAME = "HaizFlow"
QML_IMPORT_MAJOR_VERSION = 1


@QmlNamedElement("DailyNewsController")
class DailyNewsController(QObject):
    """Controller managing the Daily World News production flow and social upload UI."""

    # UI Notification Signals
    isBusyChanged = Signal()
    progressPercentChanged = Signal()
    progressMessageChanged = Signal()
    statusChanged = Signal()
    maxTopicsChanged = Signal()
    aspectRatioChanged = Signal()
    voiceIdChanged = Signal()
    detailLevelChanged = Signal()
    bgmEnabledChanged = Signal()
    bgmVolumeChanged = Signal()
    autoUploadYoutubeChanged = Signal()
    autoUploadFacebookChanged = Signal()
    youtubePrivacyChanged = Signal()
    autoAddToPlaylistChanged = Signal()
    youtubePlaylistWorldChanged = Signal()
    youtubePlaylistWarChanged = Signal()
    youtubePlaylistTechChanged = Signal()
    youtubePlaylistSportsChanged = Signal()
    youtubePlaylistViralChanged = Signal()
    youtubePlaylistHopeChanged = Signal()
    currentCategoryPlaylistChanged = Signal()
    youtubeConnectedChanged = Signal()
    youtubeChannelTitleChanged = Signal()
    hasYouTubeClientSecretChanged = Signal()
    scheduleTimeChanged = Signal()
    scheduleWakeUpChanged = Signal()
    scheduleActiveChanged = Signal()
    categorySchedulesChanged = Signal()
    lastVideoPathChanged = Signal()
    lastManifestChanged = Signal()
    historyListChanged = Signal()
    selectedCategoryChanged = Signal()
    uploadingChanged = Signal()
    uploadMessageChanged = Signal()
    productionCompleted = Signal(str)
    productionFailed = Signal(str)
    uploadCompleted = Signal(str, str)
    uploadFailed = Signal(str, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._is_busy: bool = False
        self._progress_percent: int = 0
        self._progress_message: str = "Sẵn sàng"
        self._status: str = "idle"  # idle, crawling, scripting, illustrating, rendering, uploading, completed, error

        self._selected_category: str = "tin_moi"
        self._max_topics: int = 8
        self._aspect_ratio: str = "16:9"
        self._voice_id: str = "vi-VN-NamMinhNeural"
        self._detail_level: str = "standard"
        self._bgm_enabled: bool = True
        self._bgm_volume: float = 0.08
        has_yt = False
        try:
            from haizflow.services import youtube_direct
            has_yt = bool(youtube_direct.get_saved_token())
        except Exception:
            pass
        self._auto_upload_youtube: bool = has_yt
        self._auto_upload_facebook: bool = False
        self._youtube_privacy: str = "public"
        self._auto_add_to_playlist: bool = True
        self._youtube_playlist_tin_moi: str = "Bản tin thế giới"
        self._youtube_playlist_tin_nong: str = "Bản tin thế giới"
        self._youtube_playlist_hope: str = "Bản tin thế giới"
        self._youtube_playlist_viral: str = "Bản tin thế giới"
        self._youtube_playlist_world: str = "Bản tin thế giới"
        self._youtube_playlist_war: str = "Bản tin thế giới"
        self._youtube_playlist_tech: str = "Bản tin thế giới"
        self._youtube_playlist_sports: str = "Bản tin thế giới"

        self._schedule_time: str = "05:30"
        self._schedule_wake_up: bool = True
        self._schedule_active: bool = False
        self._schedules: Dict[str, Dict[str, Any]] = {
            "tin_moi": {"time": "05:30", "wake_up": True, "active": False},
            "hope": {"time": "11:30", "wake_up": True, "active": False},
            "viral": {"time": "12:00", "wake_up": True, "active": False},
            "tin_nong": {"time": "17:30", "wake_up": True, "active": False},
            "world": {"time": "05:00", "wake_up": True, "active": False},
            "war": {"time": "05:10", "wake_up": True, "active": False},
            "tech": {"time": "05:20", "wake_up": True, "active": False},
            "sports": {"time": "05:40", "wake_up": True, "active": False},
        }

        self._last_video_path: str = ""
        self._last_manifest: Dict[str, Any] = {}
        self._history_list: List[Dict[str, Any]] = []

        self._uploading: bool = False
        self._upload_message: str = ""

        self._worker_thread: Optional[threading.Thread] = None
        self._cancel_event: threading.Event = threading.Event()

        self._load_settings()
        self.refreshHistory()
        self.refreshScheduleStatus()

    # -------------------------------------------------------------------------
    # Settings Persistence
    # -------------------------------------------------------------------------

    def _load_settings(self) -> None:
        try:
            if SETTINGS_FILE.is_file():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                self._selected_category = str(data.get("selected_category", "tin_moi"))
                if self._selected_category not in self._schedules:
                    self._selected_category = "tin_moi"
                self._max_topics = int(data.get("max_topics", 8))
                self._aspect_ratio = str(data.get("aspect_ratio", "16:9"))
                self._voice_id = str(data.get("voice_id", "vi-VN-NamMinhNeural"))
                self._detail_level = str(data.get("detail_level", "standard"))
                self._bgm_enabled = bool(data.get("bgm_enabled", True))
                self._bgm_volume = float(data.get("bgm_volume", 0.08))
                has_yt = False
                try:
                    from haizflow.services import youtube_direct
                    has_yt = bool(youtube_direct.get_saved_token())
                except Exception:
                    pass
                self._auto_upload_youtube = bool(data.get("auto_upload_youtube", has_yt))
                self._auto_upload_facebook = bool(data.get("auto_upload_facebook", False))
                self._youtube_privacy = str(data.get("youtube_privacy", "public"))
                self._auto_add_to_playlist = bool(data.get("auto_add_to_playlist", True))
                self._youtube_playlist_tin_moi = str(data.get("youtube_playlist_tin_moi", "Bản tin thế giới"))
                self._youtube_playlist_tin_nong = str(data.get("youtube_playlist_tin_nong", "Bản tin thế giới"))
                self._youtube_playlist_hope = str(data.get("youtube_playlist_hope", "Bản tin thế giới"))
                self._youtube_playlist_viral = str(data.get("youtube_playlist_viral", "Bản tin thế giới"))
                self._youtube_playlist_world = str(data.get("youtube_playlist_world", "Bản tin thế giới"))
                self._youtube_playlist_war = str(data.get("youtube_playlist_war", "Bản tin thế giới"))
                self._youtube_playlist_tech = str(data.get("youtube_playlist_tech", "Bản tin thế giới"))
                self._youtube_playlist_sports = str(data.get("youtube_playlist_sports", "Bản tin thế giới"))
                self._schedule_time = str(data.get("schedule_time", "05:30"))
                self._schedule_wake_up = bool(data.get("schedule_wake_up", True))
                if "schedules" in data and isinstance(data["schedules"], dict):
                    for cat in self._schedules:
                        c_data = data["schedules"].get(cat, {})
                        if isinstance(c_data, dict):
                            if "time" in c_data:
                                self._schedules[cat]["time"] = str(c_data["time"])
                            if "wake_up" in c_data:
                                self._schedules[cat]["wake_up"] = bool(c_data["wake_up"])
                else:
                    self._schedules["tin_moi"]["time"] = self._schedule_time
                    self._schedules["tin_moi"]["wake_up"] = self._schedule_wake_up

                cur_s = self._schedules.get(self._selected_category, self._schedules["tin_moi"])
                self._schedule_time = cur_s["time"]
                self._schedule_wake_up = cur_s["wake_up"]
        except Exception as exc:
            LOGGER.warning("Could not load daily news settings: %s", exc)

    def _save_settings(self) -> None:
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "selected_category": self._selected_category,
                "max_topics": self._max_topics,
                "aspect_ratio": self._aspect_ratio,
                "voice_id": self._voice_id,
                "detail_level": self._detail_level,
                "bgm_enabled": self._bgm_enabled,
                "bgm_volume": self._bgm_volume,
                "auto_upload_youtube": self._auto_upload_youtube,
                "auto_upload_facebook": self._auto_upload_facebook,
                "youtube_privacy": self._youtube_privacy,
                "auto_add_to_playlist": self._auto_add_to_playlist,
                "youtube_playlist_tin_moi": self._youtube_playlist_tin_moi,
                "youtube_playlist_tin_nong": self._youtube_playlist_tin_nong,
                "youtube_playlist_hope": self._youtube_playlist_hope,
                "youtube_playlist_viral": self._youtube_playlist_viral,
                "youtube_playlist_world": self._youtube_playlist_world,
                "youtube_playlist_war": self._youtube_playlist_war,
                "youtube_playlist_tech": self._youtube_playlist_tech,
                "youtube_playlist_sports": self._youtube_playlist_sports,
                "schedule_time": self._schedule_time,
                "schedule_wake_up": self._schedule_wake_up,
                "schedules": {
                    cat: {
                        "time": self._schedules[cat]["time"],
                        "wake_up": self._schedules[cat]["wake_up"],
                    }
                    for cat in self._schedules
                },
            }
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            LOGGER.warning("Could not save daily news settings: %s", exc)

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @Property(bool, notify=isBusyChanged)
    def isBusy(self) -> bool:
        return self._is_busy

    @Property(int, notify=progressPercentChanged)
    def progressPercent(self) -> int:
        return self._progress_percent

    @Property(str, notify=progressMessageChanged)
    def progressMessage(self) -> str:
        return self._progress_message

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=selectedCategoryChanged)
    def selectedCategory(self) -> str:
        return self._selected_category

    @Slot(str)
    def setSelectedCategory(self, val: str) -> None:
        norm = str(val or "tin_moi").strip().lower()
        if norm in ("tin_moi", "tinmoi", "morning", "world_sports", "thegioi_thethao"):
            norm = "tin_moi"
        elif norm in ("tin_nong", "tinnong", "evening", "war_tech", "chiensu_congnghe"):
            norm = "tin_nong"
        elif norm in ("war", "chiensu", "conflict", "chientranh", "chien_su", "war_news"):
            norm = "war"
        elif norm in ("tech", "congnghe", "technology"):
            norm = "tech"
        elif norm in ("sports", "thethao", "sport"):
            norm = "sports"
        elif norm in ("viral", "tinla", "tin_la", "docla", "doc_la", "curiosities", "hot_viral", "la_hot", "shorts"):
            norm = "viral"
        elif norm in ("hope", "tinvui", "tin_vui", "goodnews", "good_news", "sangche", "phatminh", "hyvong"):
            norm = "hope"
        elif norm in ("world", "thoisu"):
            norm = "world"
        else:
            norm = "tin_moi"
        if self._selected_category != norm:
            prev_cat = self._selected_category
            self._selected_category = norm
            sched = self._schedules.get(norm, {"time": "05:30", "wake_up": True, "active": False})
            self._schedule_time = sched["time"]
            self._schedule_wake_up = sched["wake_up"]
            self._schedule_active = sched["active"]

            # Auto-adapt video format: Only viral and hope are 9:16 Shorts, all other categories are 16:9
            if norm in ("viral", "hope"):
                if self._aspect_ratio != "9:16":
                    self._aspect_ratio = "9:16"
                    self.aspectRatioChanged.emit()
                if self._max_topics in (7, 8):
                    self._max_topics = 3
                    self.maxTopicsChanged.emit()
            else:
                if self._aspect_ratio != "16:9":
                    self._aspect_ratio = "16:9"
                    self.aspectRatioChanged.emit()
                if self._max_topics == 3:
                    self._max_topics = 8
                    self.maxTopicsChanged.emit()

            self.selectedCategoryChanged.emit()
            self.scheduleTimeChanged.emit()
            self.scheduleWakeUpChanged.emit()
            self.scheduleActiveChanged.emit()
            self.currentCategoryPlaylistChanged.emit()
            self._save_settings()

    @Property(int, notify=maxTopicsChanged)
    def maxTopics(self) -> int:
        return self._max_topics

    @Slot(int)
    def setMaxTopics(self, val: int) -> None:
        if self._max_topics != val:
            self._max_topics = max(2, min(15, int(val)))
            self.maxTopicsChanged.emit()
            self._save_settings()

    @Property(str, notify=aspectRatioChanged)
    def aspectRatio(self) -> str:
        return self._aspect_ratio

    @Slot(str)
    def setAspectRatio(self, val: str) -> None:
        norm = "9:16" if "9:16" in val or val.strip().startswith("9") else "16:9"
        if self._aspect_ratio != norm:
            self._aspect_ratio = norm
            self.aspectRatioChanged.emit()
            self._save_settings()

    @Property(str, notify=voiceIdChanged)
    def voiceId(self) -> str:
        return self._voice_id

    @Slot(str)
    def setVoiceId(self, val: str) -> None:
        if self._voice_id != val:
            self._voice_id = str(val or "vi-VN-NamMinhNeural")
            self.voiceIdChanged.emit()
            self._save_settings()

    @Property(str, notify=detailLevelChanged)
    def detailLevel(self) -> str:
        return self._detail_level

    @Slot(str)
    def setDetailLevel(self, val: str) -> None:
        if self._detail_level != val:
            self._detail_level = val if val in ("concise", "standard", "deep") else "standard"
            self.detailLevelChanged.emit()
            self._save_settings()

    @Property(bool, notify=bgmEnabledChanged)
    def bgmEnabled(self) -> bool:
        return self._bgm_enabled

    @Slot(bool)
    def setBgmEnabled(self, val: bool) -> None:
        if self._bgm_enabled != val:
            self._bgm_enabled = bool(val)
            self.bgmEnabledChanged.emit()
            self._save_settings()

    @Property(float, notify=bgmVolumeChanged)
    def bgmVolume(self) -> float:
        return self._bgm_volume

    @Slot(float)
    def setBgmVolume(self, val: float) -> None:
        v = max(0.01, min(0.30, float(val)))
        if abs(self._bgm_volume - v) > 0.001:
            self._bgm_volume = v
            self.bgmVolumeChanged.emit()
            self._save_settings()

    @Property(bool, notify=autoUploadYoutubeChanged)
    def autoUploadYoutube(self) -> bool:
        return self._auto_upload_youtube

    @Slot(bool)
    def setAutoUploadYoutube(self, val: bool) -> None:
        if self._auto_upload_youtube != val:
            self._auto_upload_youtube = bool(val)
            self.autoUploadYoutubeChanged.emit()
            self._save_settings()
            if sys.platform == "win32":
                threading.Thread(target=self._syncActiveSchedules, daemon=True).start()

    @Property(bool, notify=autoUploadFacebookChanged)
    def autoUploadFacebook(self) -> bool:
        return self._auto_upload_facebook

    @Slot(bool)
    def setAutoUploadFacebook(self, val: bool) -> None:
        if self._auto_upload_facebook != val:
            self._auto_upload_facebook = bool(val)
            self.autoUploadFacebookChanged.emit()
            self._save_settings()

    @Property(str, notify=youtubePrivacyChanged)
    def youtubePrivacy(self) -> str:
        return self._youtube_privacy

    @Slot(str)
    def setYoutubePrivacy(self, val: str) -> None:
        if self._youtube_privacy != val:
            self._youtube_privacy = val if val in ("public", "unlisted", "private") else "public"
            self.youtubePrivacyChanged.emit()
            self._save_settings()

    @Property(bool, notify=autoAddToPlaylistChanged)
    def autoAddToPlaylist(self) -> bool:
        return self._auto_add_to_playlist

    @Slot(bool)
    def setAutoAddToPlaylist(self, val: bool) -> None:
        if self._auto_add_to_playlist != bool(val):
            self._auto_add_to_playlist = bool(val)
            self.autoAddToPlaylistChanged.emit()
            self._save_settings()

    @Property(str, notify=youtubePlaylistWorldChanged)
    def youtubePlaylistWorld(self) -> str:
        return self._youtube_playlist_world

    @Slot(str)
    def setYoutubePlaylistWorld(self, val: str) -> None:
        v = str(val or "Bản tin thế giới").strip()
        if self._youtube_playlist_world != v:
            self._youtube_playlist_world = v
            self.youtubePlaylistWorldChanged.emit()
            self.currentCategoryPlaylistChanged.emit()
            self._save_settings()

    @Property(str, notify=youtubePlaylistWarChanged)
    def youtubePlaylistWar(self) -> str:
        return self._youtube_playlist_war

    @Slot(str)
    def setYoutubePlaylistWar(self, val: str) -> None:
        v = str(val or "Bản tin thế giới").strip()
        if self._youtube_playlist_war != v:
            self._youtube_playlist_war = v
            self.youtubePlaylistWarChanged.emit()
            self.currentCategoryPlaylistChanged.emit()
            self._save_settings()

    @Property(str, notify=youtubePlaylistTechChanged)
    def youtubePlaylistTech(self) -> str:
        return self._youtube_playlist_tech

    @Slot(str)
    def setYoutubePlaylistTech(self, val: str) -> None:
        v = str(val or "Bản tin thế giới").strip()
        if self._youtube_playlist_tech != v:
            self._youtube_playlist_tech = v
            self.youtubePlaylistTechChanged.emit()
            self.currentCategoryPlaylistChanged.emit()
            self._save_settings()

    @Property(str, notify=youtubePlaylistSportsChanged)
    def youtubePlaylistSports(self) -> str:
        return self._youtube_playlist_sports

    @Slot(str)
    def setYoutubePlaylistSports(self, val: str) -> None:
        v = str(val or "Bản tin thế giới").strip()
        if self._youtube_playlist_sports != v:
            self._youtube_playlist_sports = v
            self.youtubePlaylistSportsChanged.emit()
            self.currentCategoryPlaylistChanged.emit()
            self._save_settings()

    @Property(str, notify=youtubePlaylistViralChanged)
    def youtubePlaylistViral(self) -> str:
        return self._youtube_playlist_viral

    @Slot(str)
    def setYoutubePlaylistViral(self, val: str) -> None:
        v = str(val or "Bản tin thế giới").strip()
        if self._youtube_playlist_viral != v:
            self._youtube_playlist_viral = v
            self.youtubePlaylistViralChanged.emit()
            self.currentCategoryPlaylistChanged.emit()
            self._save_settings()

    @Property(str, notify=youtubePlaylistHopeChanged)
    def youtubePlaylistHope(self) -> str:
        return self._youtube_playlist_hope

    @Slot(str)
    def setYoutubePlaylistHope(self, val: str) -> None:
        v = str(val or "Bản tin thế giới").strip()
        if self._youtube_playlist_hope != v:
            self._youtube_playlist_hope = v
            self.youtubePlaylistHopeChanged.emit()
            self.currentCategoryPlaylistChanged.emit()
            self._save_settings()

    @Property(str, notify=currentCategoryPlaylistChanged)
    def currentCategoryPlaylist(self) -> str:
        if self._selected_category == "war":
            return self._youtube_playlist_war
        elif self._selected_category == "tech":
            return self._youtube_playlist_tech
        elif self._selected_category == "sports":
            return self._youtube_playlist_sports
        elif self._selected_category == "viral":
            return self._youtube_playlist_viral
        elif self._selected_category == "hope":
            return self._youtube_playlist_hope
        return self._youtube_playlist_world

    @Slot(str)
    def setCurrentCategoryPlaylist(self, val: str) -> None:
        if self._selected_category == "war":
            self.setYoutubePlaylistWar(val)
        elif self._selected_category == "tech":
            self.setYoutubePlaylistTech(val)
        elif self._selected_category == "sports":
            self.setYoutubePlaylistSports(val)
        elif self._selected_category == "viral":
            self.setYoutubePlaylistViral(val)
        elif self._selected_category == "hope":
            self.setYoutubePlaylistHope(val)
        else:
            self.setYoutubePlaylistWorld(val)

    @Slot(int, str, str, bool, float, bool, str, bool, str)
    def saveProductionSettings(
        self,
        max_topics: int,
        aspect_ratio: str,
        voice_id: str,
        bgm_enabled: bool,
        bgm_volume: float,
        auto_upload_youtube: bool,
        youtube_privacy: str,
        auto_add_playlist: bool,
        playlist_title: str,
    ) -> None:
        """Batch save all production settings in one atomic operation to eliminate UI lag."""
        topics_val = max(2, min(15, int(max_topics)))
        if self._max_topics != topics_val:
            self._max_topics = topics_val
            self.maxTopicsChanged.emit()

        if self._selected_category in ("viral", "hope"):
            norm_ar = "9:16"
        else:
            norm_ar = "16:9"
        if self._aspect_ratio != norm_ar:
            self._aspect_ratio = norm_ar
            self.aspectRatioChanged.emit()

        v_id = str(voice_id or "vi-VN-NamMinhNeural")
        if self._voice_id != v_id:
            self._voice_id = v_id
            self.voiceIdChanged.emit()

        bgm_en = bool(bgm_enabled)
        if self._bgm_enabled != bgm_en:
            self._bgm_enabled = bgm_en
            self.bgmEnabledChanged.emit()

        vol = max(0.01, min(0.30, float(bgm_volume)))
        if abs(self._bgm_volume - vol) > 0.001:
            self._bgm_volume = vol
            self.bgmVolumeChanged.emit()

        yt_changed = (self._auto_upload_youtube != bool(auto_upload_youtube))
        if yt_changed:
            self._auto_upload_youtube = bool(auto_upload_youtube)
            self.autoUploadYoutubeChanged.emit()

        priv = youtube_privacy if youtube_privacy in ("public", "unlisted", "private") else "public"
        if self._youtube_privacy != priv:
            self._youtube_privacy = priv
            self.youtubePrivacyChanged.emit()

        add_pl = bool(auto_add_playlist)
        if self._auto_add_to_playlist != add_pl:
            self._auto_add_to_playlist = add_pl
            self.autoAddToPlaylistChanged.emit()

        p_title = str(playlist_title or "").strip()
        if p_title:
            if self._selected_category == "war":
                if self._youtube_playlist_war != p_title:
                    self._youtube_playlist_war = p_title
                    self.youtubePlaylistWarChanged.emit()
            elif self._selected_category == "tech":
                if self._youtube_playlist_tech != p_title:
                    self._youtube_playlist_tech = p_title
                    self.youtubePlaylistTechChanged.emit()
            elif self._selected_category == "sports":
                if self._youtube_playlist_sports != p_title:
                    self._youtube_playlist_sports = p_title
                    self.youtubePlaylistSportsChanged.emit()
            elif self._selected_category == "viral":
                if self._youtube_playlist_viral != p_title:
                    self._youtube_playlist_viral = p_title
                    self.youtubePlaylistViralChanged.emit()
            elif self._selected_category == "hope":
                if self._youtube_playlist_hope != p_title:
                    self._youtube_playlist_hope = p_title
                    self.youtubePlaylistHopeChanged.emit()
            else:
                if self._youtube_playlist_world != p_title:
                    self._youtube_playlist_world = p_title
                    self.youtubePlaylistWorldChanged.emit()
            self.currentCategoryPlaylistChanged.emit()

        self._save_settings()

        if yt_changed and sys.platform == "win32":
            threading.Thread(target=self._syncActiveSchedules, daemon=True).start()

    @Property(bool, notify=youtubeConnectedChanged)
    def hasYouTubePlaylistScope(self) -> bool:
        return youtube_direct.has_playlist_permission()

    @Property(str, notify=scheduleTimeChanged)
    def scheduleTime(self) -> str:
        return self._schedule_time

    @Slot(str)
    def setScheduleTime(self, val: str) -> None:
        if self._schedule_time != val:
            self._schedule_time = str(val or "05:00")
            if self._selected_category in self._schedules:
                self._schedules[self._selected_category]["time"] = self._schedule_time
            self.scheduleTimeChanged.emit()
            self.categorySchedulesChanged.emit()
            self._save_settings()

    @Property(bool, notify=scheduleWakeUpChanged)
    def scheduleWakeUp(self) -> bool:
        return self._schedule_wake_up

    @Slot(bool)
    def setScheduleWakeUp(self, val: bool) -> None:
        if self._schedule_wake_up != val:
            self._schedule_wake_up = bool(val)
            if self._selected_category in self._schedules:
                self._schedules[self._selected_category]["wake_up"] = self._schedule_wake_up
            self.scheduleWakeUpChanged.emit()
            self.categorySchedulesChanged.emit()
            self._save_settings()

    @Property(bool, notify=scheduleActiveChanged)
    def scheduleActive(self) -> bool:
        return self._schedule_active

    @Property("QVariantList", notify=categorySchedulesChanged)
    def categorySchedules(self) -> List[Dict[str, Any]]:
        meta = {
            "tin_moi": {"label": "Tin Mới (Sáng 5h30)", "icon": "globe", "tag": "Thế giới + Thể thao", "tagColor": "#0078D4", "default_time": "05:30"},
            "hope": {"label": "Shorts Tin Vui (Trưa 11h30)", "icon": "favorite", "tag": "Shorts • Hy vọng", "tagColor": "#10B981", "default_time": "11:30"},
            "viral": {"label": "Shorts Tin Độc Lạ (Trưa 12h00)", "icon": "sparkle", "tag": "Shorts • Lạ & Hài", "tagColor": "#FF5722", "default_time": "12:00"},
            "tin_nong": {"label": "Tin Nóng (Tối 17h30)", "icon": "shield", "tag": "Chiến sự + Công nghệ", "tagColor": "#E53935", "default_time": "17:30"},
        }
        result = []
        for cat in ("tin_moi", "hope", "viral", "tin_nong"):
            m = meta[cat]
            s = self._schedules.get(cat, {"time": m["default_time"], "wake_up": True, "active": False})
            result.append({
                "category": cat,
                "label": m["label"],
                "icon": m["icon"],
                "tag": m["tag"],
                "tagColor": m["tagColor"],
                "time": s["time"],
                "wake_up": s["wake_up"],
                "active": bool(s.get("active", False)),
            })
        return result

    @Property(str, notify=lastVideoPathChanged)
    def lastVideoPath(self) -> str:
        return self._last_video_path

    @Property("QVariantMap", notify=lastManifestChanged)
    def lastManifest(self) -> Dict[str, Any]:
        return self._last_manifest

    @Property("QVariantList", notify=historyListChanged)
    def historyList(self) -> List[Dict[str, Any]]:
        return self._history_list

    @Property(bool, notify=uploadingChanged)
    def uploading(self) -> bool:
        return self._uploading

    @Property(str, notify=uploadMessageChanged)
    def uploadMessage(self) -> str:
        return self._upload_message

    @Property(bool, notify=youtubeConnectedChanged)
    def youtubeConnected(self) -> bool:
        token = youtube_direct.get_saved_token()
        return bool(token and token.get("refresh_token"))

    @Property(str, notify=youtubeChannelTitleChanged)
    def youtubeChannelTitle(self) -> str:
        token = youtube_direct.get_saved_token()
        if token:
            return str(token.get("channel_title") or "Kênh YouTube đã kết nối")
        return ""

    @Property(bool, notify=hasYouTubeClientSecretChanged)
    def hasYouTubeClientSecret(self) -> bool:
        c_id, c_secret = youtube_direct.get_client_credentials()
        return bool(c_id and c_secret)

    # -------------------------------------------------------------------------
    # Production Workflow
    # -------------------------------------------------------------------------

    @Slot()
    @Slot(str)
    def startProduction(self, category: Optional[str] = None) -> None:
        """Trigger the complete automated world news production pipeline for chosen category."""
        if self._is_busy:
            return

        cat = category.strip().lower() if category and category.strip() else self._selected_category
        if cat in ("tin_moi", "tinmoi", "morning", "world_sports", "thegioi_thethao"):
            cat = "tin_moi"
        elif cat in ("tin_nong", "tinnong", "evening", "war_tech", "chiensu_congnghe"):
            cat = "tin_nong"
        elif cat in ("war", "chiensu", "conflict", "chientranh", "chien_su", "war_news"):
            cat = "war"
        elif cat in ("tech", "congnghe", "technology"):
            cat = "tech"
        elif cat in ("sports", "thethao", "sport"):
            cat = "sports"
        elif cat in ("viral", "tinla", "tin_la", "docla", "doc_la", "curiosities", "hot_viral", "shorts"):
            cat = "viral"
        elif cat in ("hope", "tinvui", "tin_vui", "goodnews", "sangche", "phatminh", "hyvong"):
            cat = "hope"
        elif cat in ("world", "thoisu"):
            cat = "world"
        else:
            cat = "tin_moi"

        cat_label = "Tin Mới" if cat == "tin_moi" else ("Tin Nóng" if cat == "tin_nong" else ("Chiến sự" if cat == "war" else ("Tin vui" if cat == "hope" else ("Công nghệ" if cat == "tech" else ("Bóng đá" if cat == "sports" else ("Tin độc lạ" if cat == "viral" else "Thời sự"))))))

        self._is_busy = True
        self._status = "crawling"
        self._progress_percent = 5
        self._progress_message = f"Đang cào tin tức {cat_label.lower()} quốc tế từ các hãng thông tấn..."
        self._upload_message = ""
        self._cancel_event.clear()

        self.isBusyChanged.emit()
        self.statusChanged.emit()
        self.progressPercentChanged.emit()
        self.progressMessageChanged.emit()
        self.uploadMessageChanged.emit()

        def worker():
            try:
                def progress_cb(pct: int, msg: str):
                    self._progress_percent = pct
                    self._progress_message = msg
                    if pct < 20:
                        self._status = "crawling"
                    elif pct < 50:
                        self._status = "scripting"
                    elif pct < 70:
                        self._status = "illustrating"
                    else:
                        self._status = "rendering"

                    self.progressPercentChanged.emit()
                    self.progressMessageChanged.emit()
                    self.statusChanged.emit()

                bgm_arg = "default" if self._bgm_enabled else ""

                video_path = produce_daily_news_video(
                    aspect_ratio=self._aspect_ratio,
                    voice_id=self._voice_id,
                    mock_news=False,
                    detail_level=self._detail_level,
                    max_topics=self._max_topics,
                    bgm_path=bgm_arg,
                    bgm_volume=self._bgm_volume,
                    category=cat,
                    progress_callback=progress_cb,
                )

                self._last_video_path = str(video_path.resolve())
                manifest_file = video_path.parent / "social_publish_manifest.json"
                if manifest_file.is_file():
                    try:
                        self._last_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                        self.lastManifestChanged.emit()
                    except Exception:
                        pass

                self._progress_percent = 100
                self._progress_message = f"Hoàn tất xuất bản: {video_path.name}"
                self._status = "completed"
                self.progressPercentChanged.emit()
                self.progressMessageChanged.emit()
                self.statusChanged.emit()
                self.lastVideoPathChanged.emit()
                self.refreshHistory()

                # Automated social upload if enabled
                if self._auto_upload_youtube:
                    self._trigger_upload("youtube", self._last_video_path, self._last_manifest)
                if self._auto_upload_facebook:
                    self._trigger_upload("facebook", self._last_video_path, self._last_manifest)

                self.productionCompleted.emit(self._last_video_path)

            except Exception as exc:
                LOGGER.exception("Production pipeline failed: %s", exc)
                self._status = "error"
                self._progress_message = f"Lỗi quy trình: {exc}"
                self.statusChanged.emit()
                self.progressMessageChanged.emit()
                self.productionFailed.emit(str(exc))
            finally:
                self._is_busy = False
                self.isBusyChanged.emit()

        self._worker_thread = threading.Thread(target=worker, daemon=True)
        self._worker_thread.start()

    @Slot()
    def cancelProduction(self) -> None:
        """Cancel ongoing production."""
        self._cancel_event.set()
        self._progress_message = "Đã gửi yêu cầu dừng..."
        self.progressMessageChanged.emit()

    # -------------------------------------------------------------------------
    # Social Publishing (YouTube / Facebook)
    # -------------------------------------------------------------------------

    def _trigger_upload(self, platform: str, video_path: str, manifest: Dict[str, Any]) -> None:
        """Perform background upload to social platform."""
        self._uploading = True
        self._upload_message = f"Đang tải lên {platform.upper()}..."
        self.uploadingChanged.emit()
        self.uploadMessageChanged.emit()

        def upload_worker():
            try:
                # 1. Check if Zernio API key is active
                api_key = zernio_keys.active_key()
                title = ensure_date_in_title(manifest.get("title", "Bản Tin Thời Sự Thế Giới"), manifest.get("created_at"))
                summary = manifest.get("summary", "")
                raw_hashtags = manifest.get("hashtags", "#tintucthegioi #thoisu24h")
                hashtags = " ".join([t for t in raw_hashtags.split() if t.lower().lstrip("#") != "haizflow"])
                if platform == "youtube":
                    content = format_youtube_description_with_sources(
                        manifest,
                        title=title,
                        summary=summary,
                        hashtags=hashtags,
                    )
                else:
                    content = f"{title}\n\n{summary}\n\n{hashtags}".strip()

                # Option 1: Direct Google YouTube API
                if platform == "youtube" and youtube_direct.get_saved_token():
                    self._upload_message = "Đang kết nối Google YouTube API để tải video lên..."
                    self.uploadMessageChanged.emit()

                    def yt_cb(pct: int, msg: str):
                        self._upload_message = msg
                        self.uploadMessageChanged.emit()

                    tags = [t.strip("# ") for t in hashtags.split() if t and t.lower().strip("# ") != "haizflow"]

                    # Determine target playlist based on category
                    cat = manifest.get("category", self._selected_category)
                    target_playlist = None
                    if self._auto_add_to_playlist:
                        if cat in ("tin_moi", "morning"):
                            target_playlist = self._youtube_playlist_tin_moi or self._youtube_playlist_world
                        elif cat in ("tin_nong", "evening"):
                            target_playlist = self._youtube_playlist_tin_nong or self._youtube_playlist_world
                        elif cat in ("war", "chiensu", "conflict", "chientranh"):
                            target_playlist = self._youtube_playlist_war
                        elif cat in ("tech", "congnghe"):
                            target_playlist = self._youtube_playlist_tech
                        elif cat in ("sports", "thethao"):
                            target_playlist = self._youtube_playlist_sports
                        elif cat in ("viral", "tinla", "docla"):
                            target_playlist = self._youtube_playlist_viral
                        elif cat in ("hope", "tinvui", "tin_vui", "goodnews", "sangche", "phatminh", "hyvong"):
                            target_playlist = self._youtube_playlist_hope
                        else:
                            target_playlist = self._youtube_playlist_world

                    res = youtube_direct.upload_video_to_youtube(
                        video_path=video_path,
                        title=title,
                        description=content,
                        tags=tags,
                        privacy_status=self._youtube_privacy,
                        playlist_name=target_playlist,
                        progress_callback=yt_cb,
                        cancel_event=self._cancel_event,
                        thumbnail_path=manifest.get("thumbnail_path") or None,
                    )
                    v_id = res.get("video_id", "")
                    v_url = res.get("url", f"https://www.youtube.com/watch?v={v_id}")
                    LOGGER.info("Uploaded to YouTube directly via Google API: %s", v_url)

                    pl_note = ""
                    pl_title = ""
                    pl_id = ""
                    if res.get("playlist", {}).get("added"):
                        pl_title = res["playlist"]["playlist_name"]
                        pl_id = res["playlist"].get("playlist_id", "")
                        self._upload_message = f"✓ Đã xuất bản thành công lên YouTube ({self._youtube_privacy}) và thêm vào playlist '{pl_title}'!"
                        pl_note = f" (Playlist: {pl_title})"
                    elif res.get("playlist", {}).get("scope_insufficient"):
                        self._upload_message = f"✓ Đã xuất bản lên YouTube ({self._youtube_privacy}). (Cần cấp lại quyền để tự động thêm playlist)"
                    else:
                        self._upload_message = f"✓ Đã xuất bản thành công lên YouTube ({self._youtube_privacy}): {v_url}"

                    self.updateYouTubeStatus(
                        video_path=video_path,
                        published=True,
                        video_url=v_url,
                        note=f"Đã xuất bản qua Google YouTube API{pl_note}",
                        playlist_title=pl_title,
                        playlist_id=pl_id,
                    )
                    self.uploadCompleted.emit("youtube", v_id)
                    return

                # Option 2: Fallback to Zernio API if configured
                api_key = zernio_keys.active_key()
                if api_key:
                    client = zernio.ZernioClient(api_key)
                    accounts = client.list_accounts(platforms=(platform,))
                    if not accounts:
                        raise ValueError(f"Chưa kết nối tài khoản {platform.title()} trong Zernio.")

                    account_id = accounts[0]["id"]
                    # Presign & upload
                    presign = client.presign_video(video_path)
                    upload_url = presign.get("uploadUrl") or presign.get("url")
                    media_url = presign.get("mediaUrl") or presign.get("url")
                    if upload_url:
                        client.upload_file(upload_url, video_path)

                    post = client.create_video_post(
                        platform=platform,
                        account_id=account_id,
                        content=content,
                        media_url=media_url,
                        publish_now=True,
                        request_id=f"news_{manifest.get('digest_id', uuid.uuid4().hex[:8])}_{platform}",
                        title=title[:100],
                        privacy_level=self._youtube_privacy if platform == "youtube" else "",
                    )
                    post_id = str(post.get("id") or post.get("postId") or "")
                    LOGGER.info("Uploaded to %s successfully: Post ID %s", platform, post_id)
                    self._upload_message = f"Đã đăng thành công lên {platform.upper()}!"
                    if platform == "youtube":
                        self.updateYouTubeStatus(
                            video_path=video_path,
                            published=True,
                            video_url=f"https://www.youtube.com/watch?v={post_id}" if post_id else "",
                            note="Đã xuất bản qua Zernio API",
                        )
                    self.uploadCompleted.emit(platform, post_id)
                else:
                    if platform == "youtube":
                        msg = "Chưa kết nối Google YouTube API. Vui lòng bấm 'Kết nối kênh YouTube' hoặc nhập client_secret.json."
                    else:
                        msg = f"Đã chuẩn bị nội dung và video cho {platform.upper()}. Kết nối tài khoản để tự động đẩy."
                    self._upload_message = msg
                    LOGGER.info(msg)
                    self.uploadCompleted.emit(platform, "local_ready")

            except Exception as exc:
                LOGGER.warning("Social upload to %s failed: %s", platform, exc)
                err_text = str(exc).strip()
                if "SERVICE_DISABLED" in err_text or "has not been used in project" in err_text:
                    clean_msg = "Chưa kích hoạt YouTube Data API v3 trên Google Cloud. Hãy bấm BẬT (ENABLE) trên Google Cloud Console."
                elif "{" in err_text:
                    clean_msg = err_text.split("{")[0].strip().rstrip(":") or "Lỗi từ dịch vụ YouTube."
                else:
                    clean_msg = err_text.split("\n")[0]
                self._upload_message = f"Upload {platform.upper()} thất bại: {clean_msg}"
                self.uploadFailed.emit(platform, clean_msg)
            finally:
                self._uploading = False
                self.uploadingChanged.emit()
                self.uploadMessageChanged.emit()

        thread = threading.Thread(target=upload_worker, daemon=True)
        thread.start()
        return thread

    @Slot()
    def clearUploadMessage(self) -> None:
        """Clear current upload notification message."""
        self._upload_message = ""
        self.uploadMessageChanged.emit()

    @Slot()
    def dismissBanner(self) -> None:
        """Dismiss progress banner and clear upload message."""
        self._upload_message = ""
        if self._status in ("completed", "error"):
            self._status = "idle"
            self.statusChanged.emit()
        self.uploadMessageChanged.emit()

    @Slot(str)
    def openExternalUrl(self, url: str) -> None:
        """Open an external URL in the user's default browser."""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if url:
            QDesktopServices.openUrl(QUrl(url))

    @Slot(str, str)
    def publishVideo(self, video_path: str, platform: str) -> None:
        """Manually trigger publish of a specific video."""
        v_path = Path(video_path)
        manifest_file = v_path.parent / "social_publish_manifest.json"
        manifest = {}
        if manifest_file.is_file():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self._trigger_upload(platform.lower(), str(v_path.resolve()), manifest)

    # -------------------------------------------------------------------------
    # YouTube Direct Google OAuth Slots
    # -------------------------------------------------------------------------

    @Slot()
    def connectYouTube(self) -> None:
        """Start Google OAuth 2.0 flow to link user's YouTube channel."""
        def auth_worker():
            try:
                self._uploading = True
                self._upload_message = "Đang mở trình duyệt để xác thực cấp quyền YouTube từ Google..."
                self.uploadingChanged.emit()
                self.uploadMessageChanged.emit()

                token_resp = youtube_direct.start_oauth_flow()
                ch_title = token_resp.get("channel_title") or "Kênh YouTube"
                self._upload_message = f"✓ Kết nối thành công với: {ch_title}!"
                self.youtubeConnectedChanged.emit()
                self.youtubeChannelTitleChanged.emit()
            except Exception as exc:
                LOGGER.warning("YouTube OAuth failed: %s", exc)
                self._upload_message = f"Kết nối YouTube thất bại: {exc}"
            finally:
                self._uploading = False
                self.uploadingChanged.emit()
                self.uploadMessageChanged.emit()

        threading.Thread(target=auth_worker, daemon=True).start()

    @Slot()
    def disconnectYouTube(self) -> None:
        """Unlink YouTube channel."""
        youtube_direct.clear_saved_token()
        self._upload_message = "Đã ngắt kết nối kênh YouTube."
        self.youtubeConnectedChanged.emit()
        self.youtubeChannelTitleChanged.emit()
        self.uploadMessageChanged.emit()

    @Slot()
    def pickAndImportClientSecret(self) -> None:
        """Open native dialog to pick client_secret.json from Google Cloud."""
        try:
            from haizflow.desktop.localization import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(
                None, "Chọn tệp client_secret.json từ Google Cloud", "", "JSON Files (*.json);;All Files (*.*)"
            )
            if file_path:
                youtube_direct.import_client_secret_file(file_path)
                self._upload_message = f"Đã nạp file xác thực Google: {Path(file_path).name}"
                self.hasYouTubeClientSecretChanged.emit()
                self.uploadMessageChanged.emit()
                self.connectYouTube()
        except Exception as exc:
            self._upload_message = f"Lỗi nạp tệp: {exc}"
            self.uploadMessageChanged.emit()

    @Slot(str, str)
    def saveYouTubeCredentials(self, client_id: str, client_secret: str) -> None:
        """Save manual Google OAuth Client ID and Secret."""
        try:
            youtube_direct.save_client_credentials(client_id, client_secret)
            self._upload_message = "Đã lưu Google Client ID & Secret."
            self.hasYouTubeClientSecretChanged.emit()
            self.uploadMessageChanged.emit()
            self.connectYouTube()
        except Exception as exc:
            self._upload_message = f"Lỗi lưu Client ID: {exc}"
            self.uploadMessageChanged.emit()

    # -------------------------------------------------------------------------
    # History & Archives
    # -------------------------------------------------------------------------

    @Slot()
    def refreshHistory(self) -> None:
        """Scan runtime/data/daily_news for all generated video broadcasts."""
        base_dir = runtime_data_dir() / "daily_news"
        if not base_dir.is_dir():
            self._history_list = []
            self.historyListChanged.emit()
            return

        try:
            retroactive_export_all_daily_news_scripts()
        except Exception as retro_exc:
            LOGGER.debug("Could not run retroactive script export: %s", retro_exc)

        entries: List[Dict[str, Any]] = []
        for run_dir in base_dir.iterdir():
            if not run_dir.is_dir():
                continue
            manifest_path = run_dir / "social_publish_manifest.json"
            video_files = list(run_dir.glob("*_news_*.mp4")) or list(run_dir.glob("*.mp4"))
            if not video_files:
                continue

            v_file = video_files[0]
            size_mb = round(v_file.stat().st_size / (1024 * 1024), 1)

            # Detect category from file/folder name as default fallback
            category = "world"
            v_lower = v_file.name.lower()
            dir_lower = run_dir.name.lower()
            if "war" in v_lower or "war" in dir_lower or "chiensu" in v_lower or "chiensu" in dir_lower or "conflict" in dir_lower:
                category = "war"
            elif "hope" in v_lower or "hope" in dir_lower or "tinvui" in v_lower or "tinvui" in dir_lower or "tin_vui" in dir_lower:
                category = "hope"
            elif "viral" in v_lower or "viral" in dir_lower or "shorts" in v_lower or "shorts" in dir_lower:
                category = "viral"
            elif "tech" in v_lower or "tech" in dir_lower:
                category = "tech"
            elif "sports" in v_lower or "sports" in dir_lower or "thethao" in dir_lower:
                category = "sports"

            cat_label = "Chiến sự" if category == "war" else ("Tin vui" if category == "hope" else ("Tin Lạ & Hài" if category == "viral" else ("Công nghệ" if category == "tech" else ("Thể thao" if category == "sports" else "Thời sự"))))
            base_default_title = "Bản Tin Chiến Sự Thế Giới" if category == "war" else ("Tin Vui Thế Giới: Đột Phá Mới #Shorts" if category == "hope" else ("Tin Nóng & Độc Lạ Thế Giới #Shorts" if category == "viral" else ("Bản Tin Công Nghệ Thế Giới" if category == "tech" else ("Bản Tin Thể Thao Quốc Tế" if category == "sports" else "Bản Tin Thời Sự Thế Giới"))))
            default_title = ensure_date_in_title(base_default_title, run_dir.name)

            raw_script_file = run_dir / "script_raw.txt"
            script_file_str = str(raw_script_file.resolve()) if raw_script_file.is_file() else ""

            entry: Dict[str, Any] = {
                "folder": str(run_dir.resolve()),
                "video_path": str(v_file.resolve()),
                "video_name": v_file.name,
                "size_mb": size_mb,
                "created_at": run_dir.name,
                "title": default_title,
                "summary": "",
                "hashtags": "",
                "category": category,
                "category_label": cat_label,
                "scenes_count": 0,
                "detail_level": "standard",
                "aspect_ratio": "16:9",
                "bgm_enabled": True,
                "script_scenes": [],
                "script_file": script_file_str,
                "script_exists": bool(script_file_str),
                "youtube_published": False,
                "youtube_video_id": "",
                "youtube_url": "",
                "youtube_published_at": "",
                "custom_note": "",
                "youtube_playlist_title": "",
                "youtube_playlist_id": "",
            }

            if manifest_path.is_file():
                try:
                    m = json.loads(manifest_path.read_text(encoding="utf-8"))
                    raw_title = m.get("title") or entry["title"]
                    dated_title = ensure_date_in_title(raw_title, m.get("created_at") or run_dir.name)
                    entry["title"] = dated_title
                    if raw_title != dated_title:
                        try:
                            m["title"] = dated_title
                            manifest_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception:
                            pass
                    entry["summary"] = m.get("summary", "")
                    entry["hashtags"] = m.get("hashtags", "")
                    entry["category"] = m.get("category", entry["category"])
                    entry["category_label"] = m.get("category_label", entry["category_label"])
                    entry["scenes_count"] = m.get("scenes_count", 0)
                    entry["detail_level"] = m.get("detail_level", "standard")
                    entry["aspect_ratio"] = m.get("aspect_ratio", "16:9")
                    entry["bgm_enabled"] = m.get("bgm_enabled", True)
                    entry["created_at"] = m.get("created_at", entry["created_at"])
                    entry["script_scenes"] = m.get("script_scenes", [])
                    entry["youtube_published"] = bool(m.get("youtube_published", False))
                    entry["youtube_video_id"] = str(m.get("youtube_video_id") or "")
                    entry["youtube_url"] = str(m.get("youtube_url") or "")
                    entry["youtube_published_at"] = str(m.get("youtube_published_at") or "")
                    entry["custom_note"] = str(m.get("custom_note") or "")
                    entry["youtube_playlist_title"] = str(
                        m.get("youtube_playlist_title")
                        or (m.get("youtube_playlist", {}).get("playlist_name") if isinstance(m.get("youtube_playlist"), dict) else "")
                        or ""
                    )
                    entry["youtube_playlist_id"] = str(
                        m.get("youtube_playlist_id")
                        or (m.get("youtube_playlist", {}).get("playlist_id") if isinstance(m.get("youtube_playlist"), dict) else "")
                        or ""
                    )
                except Exception:
                    pass

            entries.append(entry)

        # Sort newest runs first
        entries.sort(key=lambda x: x["created_at"], reverse=True)
        self._history_list = entries
        self.historyListChanged.emit()

    @Slot(str, bool, str, str, result=bool)
    @Slot(str, bool, str, str, str, result=bool)
    @Slot(str, bool, str, str, str, str, result=bool)
    @Slot(str, bool, str, str, str, str, str, result=bool)
    def updateYouTubeStatus(
        self,
        video_path: str,
        published: bool,
        video_url: str = "",
        note: str = "",
        playlist_title: str = "",
        playlist_id: str = "",
        title: str = "",
    ) -> bool:
        """Update or customize the YouTube publishing status and metadata for a video."""
        try:
            v_path = Path(video_path).resolve()
            run_dir = v_path.parent
            manifest_file = run_dir / "social_publish_manifest.json"

            manifest: Dict[str, Any] = {}
            if manifest_file.is_file():
                try:
                    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}

            clean_url = str(video_url or "").strip()
            video_id = ""
            if clean_url:
                if clean_url.startswith("http://") or clean_url.startswith("https://"):
                    if "v=" in clean_url:
                        video_id = clean_url.split("v=")[1].split("&")[0]
                    elif "youtu.be/" in clean_url:
                        video_id = clean_url.split("youtu.be/")[1].split("?")[0]
                else:
                    video_id = clean_url
                    clean_url = f"https://www.youtube.com/watch?v={video_id}"

            manifest["youtube_published"] = bool(published)
            manifest["youtube_url"] = clean_url
            if video_id:
                manifest["youtube_video_id"] = video_id
            if published:
                if not manifest.get("youtube_published_at"):
                    manifest["youtube_published_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                manifest["youtube_published_at"] = ""

            manifest["custom_note"] = str(note or "").strip()
            if playlist_title:
                manifest["youtube_playlist_title"] = str(playlist_title).strip()
            if playlist_id:
                manifest["youtube_playlist_id"] = str(playlist_id).strip()
            if title:
                manifest["title"] = ensure_date_in_title(title, manifest.get("created_at") or run_dir.name)

            manifest_file.parent.mkdir(parents=True, exist_ok=True)
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            state_label = "Đã đăng" if published else "Chưa đăng"
            self._upload_message = f"Đã cập nhật trạng thái YouTube: {state_label}"
            self.uploadMessageChanged.emit()
            self.refreshHistory()
            return True
        except Exception as exc:
            LOGGER.error("Failed to update YouTube status for %s: %s", video_path, exc)
            self._upload_message = f"Lỗi cập nhật trạng thái: {exc}"
            self.uploadMessageChanged.emit()
            return False

    @Slot(str, result=bool)
    def toggleYouTubeStatus(self, video_path: str) -> bool:
        """Quick 1-click toggle of YouTube publication status."""
        v_path = Path(video_path).resolve()
        manifest_file = v_path.parent / "social_publish_manifest.json"
        is_published = False
        url = ""
        note = ""
        if manifest_file.is_file():
            try:
                m = json.loads(manifest_file.read_text(encoding="utf-8"))
                is_published = bool(m.get("youtube_published", False))
                url = str(m.get("youtube_url") or "")
                note = str(m.get("custom_note") or "")
            except Exception:
                pass
        return self.updateYouTubeStatus(video_path, not is_published, url, note)

    @Slot(str, result=bool)
    def deleteVideo(self, video_path: str) -> bool:
        """Permanently delete a video and clean up its run folder from the daily news archives."""
        try:
            v_path = Path(video_path).resolve()
            if not v_path.exists():
                LOGGER.warning("Video file not found for deletion: %s", video_path)
                return False

            run_dir = v_path.parent
            base_dir = runtime_data_dir() / "daily_news"

            # 1. Delete video file first
            try:
                v_path.unlink(missing_ok=True)
                LOGGER.info("Deleted video file: %s", v_path)
            except Exception as exc:
                LOGGER.error("Failed to delete video file %s: %s", v_path, exc)
                self._upload_message = f"Lỗi xóa video: {exc}"
                self.uploadMessageChanged.emit()
                return False

            # 2. If parent folder is inside daily_news runtime directory, clean up the run directory safely
            try:
                if base_dir.resolve() in run_dir.resolve().parents or run_dir.parent.resolve() == base_dir.resolve():
                    import shutil
                    shutil.rmtree(run_dir, ignore_errors=True)
                    LOGGER.info("Cleaned up daily news run directory: %s", run_dir)
            except Exception as exc:
                LOGGER.debug("Could not completely remove run dir %s: %s", run_dir, exc)

            # Clear last video path if it was deleted
            if self._last_video_path == str(v_path):
                self._last_video_path = ""
                self._last_manifest = {}
                self.lastVideoPathChanged.emit()
                self.lastManifestChanged.emit()

            self._upload_message = "Đã xóa bản tin thành công khỏi hệ thống."
            self.uploadMessageChanged.emit()
            self.refreshHistory()
            return True
        except Exception as exc:
            LOGGER.error("Unexpected error deleting video %s: %s", video_path, exc)
            self._upload_message = f"Lỗi xóa video: {exc}"
            self.uploadMessageChanged.emit()
            return False

    # -------------------------------------------------------------------------
    # Video Title & Playlist Batch & Item Actions
    # -------------------------------------------------------------------------

    @Slot(str, str, result=bool)
    def updateVideoTitle(self, video_path: str, new_title: str) -> bool:
        """Update video title with date validation and persist in manifest."""
        try:
            v_path = Path(video_path).resolve()
            run_dir = v_path.parent
            manifest_file = run_dir / "social_publish_manifest.json"
            if not manifest_file.is_file():
                return False
            m = json.loads(manifest_file.read_text(encoding="utf-8"))
            m["title"] = ensure_date_in_title(new_title, m.get("created_at") or run_dir.name)
            manifest_file.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
            self.refreshHistory()
            return True
        except Exception as exc:
            LOGGER.error("Could not update video title: %s", exc)
            return False

    @Slot()
    def ensureDatesInAllArchiveTitles(self) -> None:
        """Scan all history archives and ensure date is included in all titles."""
        base_dir = runtime_data_dir() / "daily_news"
        if not base_dir.is_dir():
            return
        count = 0
        for run_dir in base_dir.iterdir():
            if not run_dir.is_dir():
                continue
            manifest_file = run_dir / "social_publish_manifest.json"
            if not manifest_file.is_file():
                continue
            try:
                m = json.loads(manifest_file.read_text(encoding="utf-8"))
                old_title = m.get("title", "")
                new_title = ensure_date_in_title(old_title, m.get("created_at") or run_dir.name)
                if new_title != old_title:
                    m["title"] = new_title
                    manifest_file.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
                    count += 1
            except Exception:
                pass
        self.refreshHistory()
        if count > 0:
            self._upload_message = f"Đã cập nhật ngày tháng cho {count} tiêu đề bản tin."
            self.uploadMessageChanged.emit()

    @Slot()
    def setAllPlaylistsToWorldNews(self) -> None:
        """Set target playlist for all categories (world, war, tech, sports, viral, hope) to 'Bản tin thế giới'."""
        self._youtube_playlist_world = "Bản tin thế giới"
        self._youtube_playlist_war = "Bản tin thế giới"
        self._youtube_playlist_tech = "Bản tin thế giới"
        self._youtube_playlist_sports = "Bản tin thế giới"
        self._youtube_playlist_viral = "Bản tin thế giới"
        self._youtube_playlist_hope = "Bản tin thế giới"
        self.youtubePlaylistWorldChanged.emit()
        self.youtubePlaylistWarChanged.emit()
        self.youtubePlaylistTechChanged.emit()
        self.youtubePlaylistSportsChanged.emit()
        self.youtubePlaylistViralChanged.emit()
        self.youtubePlaylistHopeChanged.emit()
        self.currentCategoryPlaylistChanged.emit()
        self._save_settings()
        self._upload_message = "Đã chuyển tất cả chủ đề sang playlist 'Bản tin thế giới'."
        self.uploadMessageChanged.emit()

    @Slot(str, result=bool)
    @Slot(str, str, result=bool)
    def addVideoToPlaylist(self, video_path: str, playlist_name: str = "Bản tin thế giới") -> bool:
        """Add a specific published YouTube video to a target playlist."""
        try:
            v_path = Path(video_path).resolve()
            manifest_file = v_path.parent / "social_publish_manifest.json"
            if not manifest_file.is_file():
                self._upload_message = "Không tìm thấy dữ liệu xuất bản của bản tin này."
                self.uploadMessageChanged.emit()
                return False

            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            video_id = str(manifest.get("youtube_video_id") or "")
            if not video_id:
                url = str(manifest.get("youtube_url") or "")
                if "v=" in url:
                    video_id = url.split("v=")[1].split("&")[0]
                elif "youtu.be/" in url:
                    video_id = url.split("youtu.be/")[1].split("?")[0]

            if not video_id:
                self._upload_message = "Bản tin này chưa được tải lên YouTube. Hãy bấm 'Đăng lên YouTube' trước."
                self.uploadMessageChanged.emit()
                return False

            pl_name = str(playlist_name or "Bản tin thế giới").strip()
            self._upload_message = f"Đang thêm video vào playlist '{pl_name}'..."
            self.uploadMessageChanged.emit()

            pl_id, pl_title = youtube_direct.get_or_create_playlist(pl_name, privacy_status=self._youtube_privacy)
            res = youtube_direct.add_video_to_playlist(video_id=video_id, playlist_id=pl_id)

            if res.get("success"):
                manifest["youtube_playlist_title"] = pl_title
                manifest["youtube_playlist_id"] = pl_id
                manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                if res.get("already_in_playlist"):
                    self._upload_message = f"Video đã có sẵn trong playlist '{pl_title}'."
                else:
                    self._upload_message = f"✓ Đã thêm video vào playlist '{pl_title}' thành công!"
                self.uploadMessageChanged.emit()
                self.refreshHistory()
                return True
            else:
                if res.get("reason") == "scope_insufficient":
                    self._upload_message = "Cần cấp quyền quản lý Playlist trên Google. Bấm 'Cấp quyền Playlist' để tiếp tục."
                else:
                    self._upload_message = f"Không thể thêm vào playlist: {res.get('message', 'Lỗi không xác định')}"
                self.uploadMessageChanged.emit()
                return False
        except Exception as exc:
            LOGGER.error("Failed to add video %s to playlist: %s", video_path, exc)
            self._upload_message = f"Lỗi thêm vào playlist: {exc}"
            self.uploadMessageChanged.emit()
            return False

    @Slot()
    @Slot(str)
    def addAllVideosToPlaylist(self, playlist_name: str = "Bản tin thế giới") -> None:
        """Add all published YouTube videos in the archive to the specified playlist in background."""
        pl_name = str(playlist_name or "Bản tin thế giới").strip()

        def worker():
            try:
                self._uploading = True
                self._upload_message = f"Đang kết nối playlist '{pl_name}'..."
                self.uploadingChanged.emit()
                self.uploadMessageChanged.emit()

                candidates: List[Tuple[Dict[str, Any], str]] = []
                for item in self._history_list:
                    v_id = str(item.get("youtube_video_id") or "")
                    if not v_id:
                        url = str(item.get("youtube_url") or "")
                        if "v=" in url:
                            v_id = url.split("v=")[1].split("&")[0]
                        elif "youtu.be/" in url:
                            v_id = url.split("youtu.be/")[1].split("?")[0]
                    if v_id:
                        candidates.append((item, v_id))

                if not candidates:
                    self._upload_message = "Không có video nào đã đăng trên YouTube trong kho lưu trữ."
                    return

                pl_id, pl_title = youtube_direct.get_or_create_playlist(pl_name, privacy_status=self._youtube_privacy)

                added_count = 0
                already_count = 0
                failed_count = 0

                for idx, (item, v_id) in enumerate(candidates, 1):
                    item_title = item.get("title") or item.get("video_name") or v_id
                    self._upload_message = f"Đang thêm ({idx}/{len(candidates)}): {item_title[:40]}..."
                    self.uploadMessageChanged.emit()

                    res = youtube_direct.add_video_to_playlist(video_id=v_id, playlist_id=pl_id)
                    if res.get("success"):
                        if res.get("already_in_playlist"):
                            already_count += 1
                        else:
                            added_count += 1
                        try:
                            v_path = Path(item["video_path"]).resolve()
                            mf = v_path.parent / "social_publish_manifest.json"
                            if mf.is_file():
                                m = json.loads(mf.read_text(encoding="utf-8"))
                            else:
                                m = {}
                            m["youtube_playlist_title"] = pl_title
                            m["youtube_playlist_id"] = pl_id
                            mf.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception:
                            pass
                    else:
                        if res.get("reason") == "scope_insufficient":
                            self._upload_message = "Cần cấp quyền quản lý Playlist trên Google. Vui lòng bấm 'Cấp quyền Playlist'."
                            return
                        failed_count += 1

                parts = []
                if added_count > 0:
                    parts.append(f"✓ Đã thêm {added_count} video")
                if already_count > 0:
                    parts.append(f"{already_count} video đã có sẵn")
                if failed_count > 0:
                    parts.append(f"{failed_count} video lỗi")
                summary = ", ".join(parts) or "Hoàn tất"
                self._upload_message = f"{summary} trong playlist '{pl_title}'!"
                self.refreshHistory()
            except Exception as exc:
                LOGGER.error("Failed to add all videos to playlist: %s", exc)
                self._upload_message = f"Lỗi khi thêm video vào playlist: {exc}"
            finally:
                self._uploading = False
                self.uploadingChanged.emit()
                self.uploadMessageChanged.emit()

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------------------
    # System Integration & Scheduling
    # -------------------------------------------------------------------------

    @Slot(str)
    def openVideoFile(self, video_path: str) -> None:
        """Open video file in the default OS player."""
        p = Path(video_path).resolve()
        if p.is_file():
            if sys.platform == "win32":
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @Slot(str)
    def openOutputDir(self, dir_path: str) -> None:
        """Open the target folder in Windows Explorer."""
        p = Path(dir_path).resolve()
        if p.is_file():
            p = p.parent
        if p.is_dir():
            if sys.platform == "win32":
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @Slot(result=str)
    def openScriptsFolder(self) -> str:
        """Open the central editorial scripts folder (Proof of Work Archive) in Windows Explorer."""
        try:
            s_dir = get_editorial_scripts_dir()
            if sys.platform == "win32":
                os.startfile(str(s_dir))
            else:
                subprocess.Popen(["xdg-open", str(s_dir)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return str(s_dir)
        except Exception as exc:
            LOGGER.error("Failed to open scripts folder: %s", exc)
            return ""

    @Slot(str, result=str)
    def openScriptForVideo(self, video_path: str) -> str:
        """Open the specific raw text script file for a given video in the default text editor."""
        try:
            v_path = Path(video_path).resolve()
            run_dir = v_path.parent
            script_file = run_dir / "script_raw.txt"

            # If not yet generated, attempt to generate it from manifest
            if not script_file.is_file():
                manifest_path = run_dir / "social_publish_manifest.json"
                if manifest_path.is_file():
                    m = json.loads(manifest_path.read_text(encoding="utf-8"))
                    export_editorial_script_file(m, output_dir=run_dir)

            if script_file.is_file():
                if sys.platform == "win32":
                    os.startfile(str(script_file))
                else:
                    subprocess.Popen(["xdg-open", str(script_file)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return str(script_file)

            # Fallback to opening the central folder
            return self.openScriptsFolder()
        except Exception as exc:
            LOGGER.error("Failed to open script for video %s: %s", video_path, exc)
            return ""

    @Slot(result=int)
    def exportAllScripts(self) -> int:
        """Scan and export raw scripts for all existing broadcast archives."""
        try:
            exported = retroactive_export_all_daily_news_scripts()
            self._upload_message = f"Đã xuất {len(exported)} hồ sơ kịch bản thô (Proof of Work) thành công."
            self.uploadMessageChanged.emit()
            self.refreshHistory()
            return len(exported)
        except Exception as exc:
            LOGGER.error("Failed to retroactively export all scripts: %s", exc)
            return 0

    @Slot()
    def refreshScheduleStatus(self) -> None:
        """Check if Windows Task Scheduler task exists for each category."""
        if sys.platform != "win32":
            for cat in self._schedules:
                self._schedules[cat]["active"] = False
            self._schedule_active = False
            self.scheduleActiveChanged.emit()
            self.categorySchedulesChanged.emit()
            return

        script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "manage_schedule.py"
        python_exe = sys.executable

        for cat in ("tin_moi", "hope", "viral", "tin_nong"):
            try:
                res = subprocess.run(
                    [python_exe, str(script_path), "--action", "status", "--category", cat],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self._schedules[cat]["active"] = (res.returncode == 0)
            except Exception:
                self._schedules[cat]["active"] = False

        self._schedule_active = self._schedules.get(self._selected_category, {}).get("active", False)
        self.scheduleActiveChanged.emit()
        self.categorySchedulesChanged.emit()

    def _syncActiveSchedules(self) -> None:
        """Update any currently active Windows scheduled tasks with current settings."""
        script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "manage_schedule.py"
        python_exe = sys.executable
        for cat, cfg in self._schedules.items():
            if cfg.get("active"):
                t_str = cfg.get("time", "05:30" if cat == "tin_moi" else ("11:30" if cat == "hope" else ("12:00" if cat == "viral" else "17:30")))
                wake_up = cfg.get("wake_up", True)
                ar = "9:16" if cat in ("viral", "hope") else "16:9"
                mt = str(min(self._max_topics, 8 if cat == "viral" else 7)) if cat in ("viral", "hope") else str(self._max_topics)
                cmd = [
                    python_exe,
                    str(script_path),
                    "--action", "create",
                    "--category", cat,
                    "--time", t_str,
                    "--aspect-ratio", ar,
                    "--max-topics", mt,
                ]
                if not wake_up:
                    cmd.append("--no-wake")
                if self._auto_upload_youtube:
                    cmd.append("--youtube")
                else:
                    cmd.append("--no-youtube")
                try:
                    subprocess.run(
                        cmd,
                        capture_output=True,
                        check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except Exception as exc:
                    LOGGER.warning("Could not sync schedule for %s: %s", cat, exc)

    @Slot(str, str, bool, result=bool)
    def configureCategorySchedule(self, category: str, time_str: str, wake_up: bool) -> bool:
        """Create or update daily Windows Task Scheduler job for a specific category."""
        norm_cat = str(category or "tin_moi").strip().lower()
        if norm_cat not in self._schedules:
            norm_cat = "tin_moi"
        default_times = {
            "tin_moi": "05:30",
            "hope": "11:30",
            "viral": "12:00",
            "tin_nong": "17:30",
        }
        t_str = time_str.strip() or default_times.get(norm_cat, "05:30")

        self._schedules[norm_cat]["time"] = t_str
        self._schedules[norm_cat]["wake_up"] = wake_up

        if norm_cat == self._selected_category:
            self._schedule_time = t_str
            self._schedule_wake_up = wake_up
            self.scheduleTimeChanged.emit()
            self.scheduleWakeUpChanged.emit()

        self.categorySchedulesChanged.emit()
        self._save_settings()

        script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "manage_schedule.py"
        python_exe = sys.executable

        try:
            ar = "9:16" if norm_cat in ("viral", "hope") else "16:9"
            mt = str(self._max_topics)
            cmd = [
                python_exe,
                str(script_path),
                "--action", "create",
                "--category", norm_cat,
                "--time", t_str,
                "--aspect-ratio", ar,
                "--max-topics", mt,
            ]
            if not wake_up:
                cmd.append("--no-wake")
            if self._auto_upload_youtube:
                cmd.append("--youtube")
            else:
                cmd.append("--no-youtube")

            res = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.refreshScheduleStatus()
            return res.returncode == 0
        except Exception as exc:
            LOGGER.warning("Could not set up schedule for %s: %s", norm_cat, exc)
            self.refreshScheduleStatus()
            return False

    @Slot(str, result=bool)
    def removeCategorySchedule(self, category: str) -> bool:
        """Remove scheduled job from Windows Task Scheduler for a specific category."""
        norm_cat = str(category or "world").strip().lower()
        script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "manage_schedule.py"
        python_exe = sys.executable

        try:
            res = subprocess.run(
                [python_exe, str(script_path), "--action", "delete", "--category", norm_cat],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.refreshScheduleStatus()
            return res.returncode == 0
        except Exception as exc:
            LOGGER.warning("Could not delete schedule for %s: %s", norm_cat, exc)
            self.refreshScheduleStatus()
            return False

    @Slot(str, str)
    def setCategoryScheduleTime(self, category: str, time_str: str) -> None:
        cat = str(category or "world").strip().lower()
        if cat in self._schedules:
            self._schedules[cat]["time"] = time_str.strip()
            if cat == self._selected_category:
                self._schedule_time = time_str.strip()
                self.scheduleTimeChanged.emit()
            self.categorySchedulesChanged.emit()
            self._save_settings()

    @Slot(str, bool)
    def setCategoryScheduleWakeUp(self, category: str, wake_up: bool) -> None:
        cat = str(category or "world").strip().lower()
        if cat in self._schedules:
            self._schedules[cat]["wake_up"] = bool(wake_up)
            if cat == self._selected_category:
                self._schedule_wake_up = bool(wake_up)
                self.scheduleWakeUpChanged.emit()
            self.categorySchedulesChanged.emit()
            self._save_settings()

    @Slot(str, bool, result=bool)
    def configureSchedule(self, time_str: str, wake_up: bool) -> bool:
        return self.configureCategorySchedule(self._selected_category, time_str, wake_up)

    @Slot(result=bool)
    def removeSchedule(self) -> bool:
        return self.removeCategorySchedule(self._selected_category)
