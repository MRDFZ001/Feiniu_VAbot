from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

INVALID_CHARS = r'<>:"/\\|?*\0'
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def safe_filename(name: str | None, default: str = "未命名", max_len: int = 80) -> str:
    if not name:
        name = default
    name = unicodedata.normalize("NFKC", str(name))
    for ch in INVALID_CHARS:
        name = name.replace(ch, "_")
    name = re.sub(r"[\r\n\t]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = re.sub(r"_+", "_", name)
    if not name:
        name = default
    if name.upper() in RESERVED_NAMES:
        name = f"_{name}"
    return name[:max_len].strip(" .") or default


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 10000):
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法生成不重复文件名：{path}")


def guess_ext_from_url(url: str, default: str = ".bin") -> str:
    try:
        path = urlparse(url).path
    except Exception:
        return default
    suffix = Path(path).suffix.lower()
    if suffix and len(suffix) <= 8:
        return suffix
    return default


def ext_from_content_type(content_type: str | None, default: str = ".bin") -> str:
    if not content_type:
        return default
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/flac": ".flac",
        "audio/wav": ".wav",
    }
    return mapping.get(ct, default)
