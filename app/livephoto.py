from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from app.filename import unique_path


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)


def convert_image_to_jpg(src: Path, dest: Path) -> Path:
    """Convert the static cover to a normal JPG file."""
    dest = unique_path(dest)
    with Image.open(src) as image:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("RGB")
        image.save(dest, "JPEG", quality=95)
    return dest


def convert_video_to_mp4(src: Path, dest: Path) -> Path:
    """Convert or remux the dynamic part to a normal MP4 file.

    VABot no longer tries to generate Apple Live Photo or Google Motion Photo.
    Dynamic/live content is saved as a simple pair:
    - base_name.jpg
    - base_name.mp4
    """
    dest = unique_path(dest)

    command_copy = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-c", "copy",
        "-movflags", "+faststart",
        str(dest),
    ]
    result = _run(command_copy)
    if result.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
        return dest

    command_encode = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(dest),
    ]
    result = _run(command_encode)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 转 MP4 失败：{result.stderr.strip()}")
    return dest


def create_livephoto_pair(raw_image: Path, raw_video: Path, target_dir: Path, base_name: str) -> tuple[Path, Path, str]:
    """Create the saved dynamic media pair.

    The function name is kept for compatibility with older VABot code.
    Output files:
    - base_name.jpg: static cover
    - base_name.mp4: dynamic video
    """
    jpg_path = convert_image_to_jpg(raw_image, target_dir / f"{base_name}.jpg")
    mp4_path = convert_video_to_mp4(raw_video, target_dir / f"{base_name}.mp4")
    return jpg_path, mp4_path, ""
