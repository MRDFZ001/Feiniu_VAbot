from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LivePhotoItem:
    image_url: str
    video_url: str


@dataclass
class MusicInfo:
    title: str = ""
    author: str = ""
    url: str = ""
    cover: str = ""
    format: str = ""
    codec: str = ""
    size: str = ""
    lyric: str = ""
    album: str = ""


@dataclass
class MediaResult:
    ok: bool
    media_type: str = "unknown"  # video / image / live / music / unknown
    platform: str = "未识别"
    title: str = "未获取"
    desc: str = ""
    author_name: str = "未获取"
    author_id: str = ""
    author_fans: str = "未获取"
    like_count: str = "未获取"
    publish_time: str = "未获取"
    source_url: str = ""
    cover_url: str = ""
    video_url: str = ""
    video_backups: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    live_photos: list[LivePhotoItem] = field(default_factory=list)
    music: MusicInfo = field(default_factory=MusicInfo)
    api_used: str = ""
    message: str = ""
    raw: dict[str, Any] | None = None

    @property
    def display_type(self) -> str:
        mapping = {
            "video": "普通视频",
            "image": "图文",
            "live": "动图/实况",
            "music": "音乐",
            "audio": "仅提取音频",
            "unknown": "未知",
        }
        return mapping.get(self.media_type, self.media_type)
