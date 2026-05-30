from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import requests

from app.config import Config
from app.filename import ext_from_content_type, guess_ext_from_url, safe_filename, unique_path
from app.livephoto import create_livephoto_pair
from app.models import MediaResult


@dataclass
class SaveResult:
    status: str
    save_dir: Path | None = None
    files: list[Path] = field(default_factory=list)
    note: str = ""
    error: str = ""


REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "*/*",
}


def _download(url: str, dest: Path, timeout: int) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, headers=REQUEST_HEADERS, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        if dest.suffix == ".bin":
            guessed = ext_from_content_type(response.headers.get("Content-Type"), default=dest.suffix)
            if guessed != dest.suffix:
                dest = dest.with_suffix(guessed)
                tmp_path = dest.with_suffix(dest.suffix + ".part")
        dest = unique_path(dest)
        tmp_path = dest.with_suffix(dest.suffix + ".part")
        with tmp_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    fh.write(chunk)
    tmp_path.rename(dest)
    return dest


def _target_dir_for_collection(base_dir: Path, title: str, count: int) -> Path:
    if count >= 3:
        folder = base_dir / safe_filename(title, default="作品")
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _video_url(result: MediaResult) -> str:
    if result.video_url:
        return result.video_url
    if result.video_backups:
        return result.video_backups[0]
    return ""


def _download_video_audio(config: Config, result: MediaResult, title: str, video_path: Path) -> tuple[list[Path], str]:
    """Save a companion audio file for a normal video.

    Priority:
    1. Use the parsed BGM/audio URL when the API provides it.
    2. Otherwise try to extract audio from the downloaded video with ffmpeg.
    """
    files: list[Path] = []

    if result.music.url:
        ext = _audio_ext(result, result.music.url)
        if ext == ".bin":
            ext = ".mp3"
        audio_path = _download(result.music.url, config.video_dir / f"{title}_音频{ext}", config.request_timeout)
        files.append(audio_path)
        return files, "普通视频，已保存视频和音频"

    audio_path = unique_path(config.video_dir / f"{title}_音频.mp3")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-vn", "-c:a", "libmp3lame", "-q:a", "2",
        str(audio_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if proc.returncode == 0 and audio_path.exists() and audio_path.stat().st_size > 0:
        files.append(audio_path)
        return files, "普通视频，已保存视频，并从视频中提取音频"

    if audio_path.exists():
        try:
            audio_path.unlink()
        except Exception:
            pass
    return files, "普通视频已保存；未获取到可保存的音频"


def save_video(config: Config, result: MediaResult) -> SaveResult:
    url = _video_url(result)
    if not url:
        return SaveResult(status="失败", error="未找到视频下载地址")
    title = safe_filename(result.title, default="视频")
    ext = guess_ext_from_url(url, default=".mp4")
    if ext.lower() not in {".mp4", ".mov", ".m4v", ".webm", ".flv", ".mkv", ".avi", ".bin"}:
        ext = ".mp4"
    video_path = _download(url, config.video_dir / f"{title}{ext}", config.request_timeout)
    files = [video_path]
    audio_files, note = _download_video_audio(config, result, title, video_path)
    files.extend(audio_files)
    return SaveResult(status="成功", save_dir=config.video_dir, files=files, note=note)


def save_images(config: Config, result: MediaResult) -> SaveResult:
    if not result.images:
        return SaveResult(status="失败", error="未找到图片列表")
    target_dir = _target_dir_for_collection(config.video_dir, result.title, len(result.images))
    title = safe_filename(result.title, default="图文")
    files: list[Path] = []
    for index, url in enumerate(result.images, start=1):
        ext = guess_ext_from_url(url, default=".jpg")
        if ext.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bin"}:
            ext = ".jpg"
        files.append(_download(url, target_dir / f"{title}_图_{index:02d}{ext}", config.request_timeout))
    note = "图文数量大于等于 3，已新建标题文件夹保存" if len(result.images) >= 3 else "图文数量小于 3，直接保存到视频"
    return SaveResult(status="成功", save_dir=target_dir, files=files, note=note)


def save_livephotos(config: Config, result: MediaResult) -> SaveResult:
    if not result.live_photos:
        return SaveResult(status="失败", error="未找到 live_photo 数据")
    target_dir = _target_dir_for_collection(config.video_dir, result.title, len(result.live_photos))
    title = safe_filename(result.title, default="实况")
    files: list[Path] = []
    raw_files: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="vabot_live_") as temp_root:
        temp_dir = Path(temp_root)
        for index, item in enumerate(result.live_photos, start=1):
            base_name = f"{title}_{index:02d}"
            raw_img = _download(item.image_url, temp_dir / f"{base_name}_raw_img.bin", config.request_timeout)
            raw_vid = _download(item.video_url, temp_dir / f"{base_name}_raw_video.bin", config.request_timeout)
            jpg_path, mp4_path, _asset_id = create_livephoto_pair(raw_img, raw_vid, target_dir, base_name)
            files.extend([jpg_path, mp4_path])

            if config.keep_live_raw:
                raw_img_dest = unique_path(target_dir / f"{base_name}_raw{raw_img.suffix}")
                raw_vid_dest = unique_path(target_dir / f"{base_name}_raw{raw_vid.suffix}")
                raw_img_dest.write_bytes(raw_img.read_bytes())
                raw_vid_dest.write_bytes(raw_vid.read_bytes())
                raw_files.extend([raw_img_dest, raw_vid_dest])

    files.extend(raw_files)
    note = "已保存动态素材（JPG + MP4），不再生成 Motion 或 LivePhoto 压缩包"
    if len(result.live_photos) >= 3:
        note += "；数量大于等于 3，已新建标题文件夹"
    return SaveResult(status="成功", save_dir=target_dir, files=files, note=note)


def _audio_ext(result: MediaResult, url: str) -> str:
    fmt = (result.music.format or result.music.codec or "").strip().lower().lstrip(".")
    if fmt in {"mp3", "m4a", "flac", "wav", "aac", "ogg"}:
        return f".{fmt}"
    ext = guess_ext_from_url(url, default=".mp3")
    if ext.lower() in {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".bin"}:
        return ext
    return ".mp3"


def save_music(config: Config, result: MediaResult) -> SaveResult:
    url = result.music.url
    if not url:
        return SaveResult(status="失败", error="未找到音乐下载地址")
    artist = safe_filename(result.music.author or result.author_name, default="未知歌手", max_len=40)
    title = safe_filename(result.music.title or result.title, default="未命名歌曲", max_len=80)
    ext = _audio_ext(result, url)
    audio_path = _download(url, config.music_dir / f"{artist} - {title}{ext}", config.request_timeout)
    files = [audio_path]

    if result.music.lyric:
        lyric_path = unique_path(config.music_dir / f"{artist} - {title}.lrc")
        lyric_path.write_text(result.music.lyric, encoding="utf-8")
        files.append(lyric_path)

    return SaveResult(status="成功", save_dir=config.music_dir, files=files, note="音乐文件按接口返回格式保存")


def save_audio_only(config: Config, result: MediaResult) -> SaveResult:
    if result.music.url:
        result.media_type = "audio"
        return save_music(config, result)

    url = _video_url(result)
    if not url:
        return SaveResult(status="失败", error="未找到可提取音频的视频地址")

    title = safe_filename(result.title, default="提取音频")
    with tempfile.TemporaryDirectory(prefix="vabot_audio_") as temp_root:
        temp_dir = Path(temp_root)
        video_path = _download(url, temp_dir / f"{title}.mp4", config.request_timeout)
        out_path = unique_path(config.music_dir / f"{title}_音频.mp3")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video_path),
            "-vn", "-c:a", "libmp3lame", "-q:a", "2",
            str(out_path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if proc.returncode != 0:
            return SaveResult(status="失败", error=f"ffmpeg 提取音频失败：{proc.stderr.strip()}")
    return SaveResult(status="成功", save_dir=config.music_dir, files=[out_path], note="已从视频中提取音频")


def save_result(config: Config, result: MediaResult, *, audio_only: bool = False) -> SaveResult:
    if not result.ok:
        return SaveResult(status="失败", error=result.message)
    if audio_only:
        return save_audio_only(config, result)
    if result.media_type == "music":
        return save_music(config, result)
    if result.media_type == "live":
        return save_livephotos(config, result)
    if result.media_type == "image":
        return save_images(config, result)
    if result.media_type == "video":
        return save_video(config, result)
    return SaveResult(status="失败", error=f"未知类型：{result.media_type}")
