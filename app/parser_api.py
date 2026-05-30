from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests

from app.config import Config
from app.link_extractor import detect_platform
from app.models import LivePhotoItem, MediaResult, MusicInfo


def _is_success(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("code")
    return str(code) == "200"


def _bugpk_params(config: Config, link: str) -> dict[str, str]:
    params = {"url": link}
    if config.bugpk_key:
        params["key"] = config.bugpk_key
    return params


def _get_json(url: str, config: Config, *, params: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=config.request_timeout,
    )
    response.raise_for_status()
    return response.json()


def _format_timestamp(value: Any) -> str:
    if value in (None, "", 0):
        return "未获取"
    try:
        number = int(value)
        if number > 0:
            return datetime.fromtimestamp(number).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return str(value)


def _first_string(*values: Any, default: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and value not in (0,):
            return str(value)
    return default


def _normalize_author(author: Any, fallback_name: str = "") -> tuple[str, str, str]:
    if isinstance(author, dict):
        name = _first_string(author.get("name"), author.get("nickname"), fallback_name, default="未获取")
        author_id = _first_string(author.get("id"), author.get("userId"), author.get("uid"), default="")
        avatar = _first_string(author.get("avatar"), default="")
        return name, author_id, avatar
    return _first_string(author, fallback_name, default="未获取"), "", ""


def _normalize_bugpk_video(payload: dict[str, Any], link: str, api_used: str, platform_hint: str) -> MediaResult:
    if not _is_success(payload):
        return MediaResult(ok=False, platform=platform_hint, source_url=link, api_used=api_used, message=str(payload.get("msg", "解析失败")), raw=payload)

    data = payload.get("data") or {}
    if not isinstance(data, dict):
        return MediaResult(ok=False, platform=platform_hint, source_url=link, api_used=api_used, message="接口未返回 data 对象", raw=payload)

    author_name, author_id, _avatar = _normalize_author(data.get("author"), fallback_name=data.get("author", ""))
    if author_name == "未获取":
        author_name = _first_string(data.get("author"), default="未获取")
    if not author_id:
        author_id = _first_string(data.get("uid"), data.get("userId"), default="")

    video_backups: list[str] = []
    backups_raw = data.get("video_backup") or []
    if isinstance(backups_raw, list):
        for item in backups_raw:
            if isinstance(item, dict) and item.get("url"):
                video_backups.append(str(item["url"]))
            elif isinstance(item, str):
                video_backups.append(item)

    images = [str(x) for x in (data.get("images") or []) if isinstance(x, str) and x.strip()]
    live_photos: list[LivePhotoItem] = []
    for item in data.get("live_photo") or []:
        if isinstance(item, dict) and item.get("image") and item.get("video"):
            live_photos.append(LivePhotoItem(image_url=str(item["image"]), video_url=str(item["video"])))

    music_raw = data.get("music") or {}
    music = MusicInfo()
    if isinstance(music_raw, dict):
        music = MusicInfo(
            title=_first_string(music_raw.get("title"), default=""),
            author=_first_string(music_raw.get("author"), default=""),
            url=_first_string(music_raw.get("url"), default=""),
            cover=_first_string(music_raw.get("cover"), music_raw.get("avatar"), default=""),
        )

    media_type = _first_string(data.get("type"), default="")
    if live_photos or media_type == "live":
        media_type = "live"
    elif media_type in {"image", "images"} or (images and not data.get("url")):
        media_type = "image"
    elif data.get("url") or video_backups:
        media_type = "video"
    else:
        media_type = "unknown"

    return MediaResult(
        ok=True,
        media_type=media_type,
        platform=platform_hint,
        title=_first_string(data.get("title"), data.get("desc"), default="未命名作品"),
        desc=_first_string(data.get("desc"), default=""),
        author_name=author_name,
        author_id=author_id,
        like_count=_first_string(data.get("like"), data.get("likes"), default="未获取"),
        publish_time=_format_timestamp(data.get("time") or data.get("publish_time") or data.get("create_time")),
        source_url=link,
        cover_url=_first_string(data.get("cover"), default=""),
        video_url=_first_string(data.get("url"), default=""),
        video_backups=video_backups,
        images=images,
        live_photos=live_photos,
        music=music,
        api_used=api_used,
        message=str(payload.get("msg", "解析成功")),
        raw=payload,
    )


def _normalize_xhsimg(payload: dict[str, Any], link: str, api_used: str) -> MediaResult:
    if not _is_success(payload):
        return MediaResult(ok=False, platform="小红书", source_url=link, api_used=api_used, message=str(payload.get("msg", "解析失败")), raw=payload)
    data = payload.get("data") or {}
    images = [str(x) for x in (data.get("images") or []) if isinstance(x, str) and x.strip()]
    return MediaResult(
        ok=True,
        media_type="image" if images else "unknown",
        platform="小红书",
        title=_first_string(data.get("title"), data.get("desc"), default="小红书图文"),
        desc=_first_string(data.get("desc"), default=""),
        author_name=_first_string(data.get("author"), default="未获取"),
        author_id=_first_string(data.get("userId"), default=""),
        source_url=link,
        cover_url=_first_string(data.get("cover"), default=""),
        images=images,
        api_used=api_used,
        message=str(payload.get("msg", "解析成功")),
        raw=payload,
    )


def _normalize_apicx_xhs(payload: dict[str, Any], link: str, api_used: str) -> MediaResult:
    if not _is_success(payload):
        return MediaResult(ok=False, platform="小红书", source_url=link, api_used=api_used, message=str(payload.get("msg", "解析失败")), raw=payload)
    data = payload.get("data") or {}
    note_info = data.get("note_info") or {}
    images = [str(x) for x in (data.get("images") or []) if isinstance(x, str) and x.strip()]
    videos = [str(x) for x in (data.get("videos") or []) if isinstance(x, str) and x.strip()]
    return MediaResult(
        ok=True,
        media_type="video" if videos else "image" if images else "unknown",
        platform="小红书",
        title=_first_string(note_info.get("title"), note_info.get("desc"), default="小红书笔记"),
        desc=_first_string(note_info.get("desc"), default=""),
        author_name=_first_string(note_info.get("nickname"), default="未获取"),
        author_id=_first_string(note_info.get("userId"), note_info.get("noteId"), default=""),
        source_url=link,
        cover_url=_first_string(note_info.get("avatar"), default=""),
        video_url=videos[0] if videos else "",
        images=images,
        api_used=api_used,
        message=str(payload.get("msg", "解析成功")),
        raw=payload,
    )


def _normalize_apicx_douyin_live(payload: dict[str, Any], link: str, api_used: str) -> MediaResult:
    if not _is_success(payload):
        return MediaResult(ok=False, platform="抖音", source_url=link, api_used=api_used, message=str(payload.get("msg", "解析失败")), raw=payload)
    parsed = (((payload.get("data") or {}).get("解析结果") or {}))
    return _normalize_bugpk_video(parsed, link, api_used, "抖音")


def _normalize_qsmusic(payload: dict[str, Any], link: str, api_used: str) -> MediaResult:
    if not _is_success(payload):
        return MediaResult(ok=False, media_type="music", platform="汽水音乐", source_url=link, api_used=api_used, message=str(payload.get("msg", "解析失败")), raw=payload)
    data = payload.get("data") or {}
    title = _first_string(data.get("albumname"), data.get("title"), default="未命名歌曲")
    author = _first_string(data.get("artistsname"), data.get("author"), default="未获取")
    music = MusicInfo(
        title=title,
        author=author,
        url=_first_string(data.get("url"), default=""),
        format=_first_string(data.get("Format"), data.get("format"), default=""),
        codec=_first_string(data.get("Codec"), data.get("codec"), default=""),
        size=_first_string(data.get("Size"), data.get("size"), default=""),
        lyric=_first_string(data.get("lyric"), default=""),
        album=_first_string(data.get("albumname"), default=""),
    )
    return MediaResult(
        ok=bool(music.url),
        media_type="music",
        platform="汽水音乐",
        title=title,
        author_name=author,
        source_url=link,
        music=music,
        api_used=api_used,
        message=str(payload.get("msg", "获取成功")),
        raw=payload,
    )


def _try_call(name: str, call_fn) -> MediaResult:
    try:
        return call_fn()
    except requests.RequestException as exc:
        return MediaResult(ok=False, api_used=name, message=f"请求失败：{exc}")
    except ValueError as exc:
        return MediaResult(ok=False, api_used=name, message=f"JSON 解析失败：{exc}")
    except Exception as exc:
        return MediaResult(ok=False, api_used=name, message=f"未知错误：{exc}")


def parse_music(config: Config, link: str) -> MediaResult:
    if not config.qsmusic_api:
        return MediaResult(
            ok=False,
            media_type="music",
            platform="汽水音乐",
            source_url=link,
            api_used="qsmusic",
            message="未配置 QSMUSIC_API，请先在 .env 中填写音乐解析接口地址。",
        )
    return _try_call("qsmusic", lambda: _normalize_qsmusic(
        _get_json(config.qsmusic_api, config, params=_bugpk_params(config, link)),
        link,
        "qsmusic",
    ))


def parse_link(config: Config, link: str, force_music: bool = False) -> MediaResult:
    platform = detect_platform(link)
    if force_music or platform == "汽水音乐":
        return parse_music(config, link)

    attempts: list[tuple[str, Any]] = []

    if platform == "抖音":
        if config.douyin_api:
            attempts.append(("douyin", lambda: _normalize_bugpk_video(
                _get_json(config.douyin_api, config, params=_bugpk_params(config, link)), link, "douyin", platform)))
        if config.short_videos_api:
            attempts.append(("short_videos", lambda: _normalize_bugpk_video(
                _get_json(config.short_videos_api, config, params=_bugpk_params(config, link)), link, "short_videos", platform)))
        if config.svparse_api:
            attempts.append(("svparse", lambda: _normalize_bugpk_video(
                _get_json(config.svparse_api, config, params=_bugpk_params(config, link)), link, "svparse", platform)))
        if config.apicx_douyin_live_api and (config.apicx_token or config.apicx_auth):
            headers = {"Authorization": config.apicx_auth or config.apicx_token}
            params = {"url": link}
            if config.apicx_token:
                params["token"] = config.apicx_token
            attempts.append(("douyin_live_backup", lambda: _normalize_apicx_douyin_live(
                _get_json(config.apicx_douyin_live_api, config, params=params, headers=headers), link, "douyin_live_backup")))
    elif platform == "小红书":
        if config.xhsimg_api:
            attempts.append(("xhsimg", lambda: _normalize_xhsimg(
                _get_json(config.xhsimg_api, config, params=_bugpk_params(config, link)), link, "xhsimg")))
        if config.short_videos_api:
            attempts.append(("short_videos", lambda: _normalize_bugpk_video(
                _get_json(config.short_videos_api, config, params=_bugpk_params(config, link)), link, "short_videos", platform)))
        if config.svparse_api:
            attempts.append(("svparse", lambda: _normalize_bugpk_video(
                _get_json(config.svparse_api, config, params=_bugpk_params(config, link)), link, "svparse", platform)))
        if config.apicx_xhs_api and (config.apicx_token or config.apicx_auth):
            headers = {"Authorization": config.apicx_auth or config.apicx_token}
            params = {"url": link}
            if config.apicx_token:
                params["token"] = config.apicx_token
            attempts.append(("xhs_backup", lambda: _normalize_apicx_xhs(
                _get_json(config.apicx_xhs_api, config, params=params, headers=headers), link, "xhs_backup")))
    else:
        if config.short_videos_api:
            attempts.append(("short_videos", lambda: _normalize_bugpk_video(
                _get_json(config.short_videos_api, config, params=_bugpk_params(config, link)), link, "short_videos", platform)))
        if config.svparse_api:
            attempts.append(("svparse", lambda: _normalize_bugpk_video(
                _get_json(config.svparse_api, config, params=_bugpk_params(config, link)), link, "svparse", platform)))

    if not attempts:
        return MediaResult(
            ok=False,
            platform=platform,
            source_url=link,
            api_used="none",
            message="未配置任何解析接口，请先在 .env 中填写 DOUYIN_API、XHSIMG_API、SHORT_VIDEOS_API 或 SVPARSE_API。",
        )

    errors: list[str] = []
    for name, call_fn in attempts:
        result = _try_call(name, call_fn)
        if result.ok:
            return result
        errors.append(f"{name}: {result.message}")
        time.sleep(0.2)

    return MediaResult(
        ok=False,
        platform=platform,
        source_url=link,
        api_used="; ".join(name for name, _ in attempts),
        message="全部接口失败：" + " | ".join(errors),
    )
