from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required user configuration is missing."""


@dataclass(frozen=True)
class Config:
    creative_root: Path
    video_dir: Path
    music_dir: Path
    log_dir: Path
    record_file: Path
    request_timeout: int
    bugpk_key: str
    apicx_token: str
    apicx_auth: str
    keep_live_raw: bool
    short_videos_api: str
    svparse_api: str
    douyin_api: str
    xhsimg_api: str
    qsmusic_api: str
    apicx_douyin_live_api: str
    apicx_xhs_api: str


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _str_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _path_env(name: str, default: str) -> Path:
    raw = _str_env(name, default)
    return Path(raw).expanduser()


def _required_path_env(name: str) -> Path:
    raw = _str_env(name)
    if not raw:
        raise ConfigError(
            f"未配置保存目录 {name}。请先复制 .env.example 为 .env，"
            "然后填写你自己的飞牛/NAS/服务器保存目录。"
        )
    return Path(raw).expanduser()


def get_config() -> Config:
    # CREATIVE_ROOT 必须由用户在 .env 或 docker-compose 环境中显式提供。
    # Docker 部署时一般保持 /creative，再把用户自己的飞牛目录挂载到 /creative。
    creative_root = _required_path_env("CREATIVE_ROOT")
    video_dir = _path_env("VIDEO_DIR", str(creative_root / "video"))
    music_dir = _path_env("MUSIC_DIR", str(creative_root / "music"))
    log_dir = _path_env("LOG_DIR", str(creative_root / "logs"))
    record_file = _path_env("RECORD_FILE", str(log_dir / "解析记录.txt"))

    timeout_raw = _str_env("REQUEST_TIMEOUT", "30")
    try:
        request_timeout = int(timeout_raw)
    except ValueError:
        request_timeout = 30

    return Config(
        creative_root=creative_root,
        video_dir=video_dir,
        music_dir=music_dir,
        log_dir=log_dir,
        record_file=record_file,
        request_timeout=request_timeout,
        bugpk_key=_str_env("BUGPK_KEY"),
        apicx_token=_str_env("APICX_TOKEN"),
        apicx_auth=_str_env("APICX_AUTH"),
        keep_live_raw=_bool_env("KEEP_LIVE_RAW", False),
        short_videos_api=_str_env("SHORT_VIDEOS_API"),
        svparse_api=_str_env("SVPARSE_API"),
        douyin_api=_str_env("DOUYIN_API"),
        xhsimg_api=_str_env("XHSIMG_API"),
        qsmusic_api=_str_env("QSMUSIC_API"),
        apicx_douyin_live_api=_str_env("APICX_DOUYIN_LIVE_API"),
        apicx_xhs_api=_str_env("APICX_XHS_API"),
    )


def ensure_dirs(config: Config) -> None:
    config.video_dir.mkdir(parents=True, exist_ok=True)
    config.music_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.record_file.parent.mkdir(parents=True, exist_ok=True)
    if not config.record_file.exists():
        config.record_file.touch()
