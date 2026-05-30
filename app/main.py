from __future__ import annotations

import argparse
from pathlib import Path

from app.processor import process_text


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VABot 本地解析下载核心")
    parser.add_argument("text", nargs="*", help="分享文本或链接，可以一次传多个")
    parser.add_argument("--music", action="store_true", help="强制按汽水音乐接口解析")
    parser.add_argument("--audio-only", action="store_true", help="仅保存音频：优先保存解析出的 BGM，失败时从视频提取 MP3")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    raw_text = " ".join(args.text).strip()
    if not raw_text:
        parser.print_help()
        return 2

    summary = process_text(raw_text, force_music=args.music, audio_only=args.audio_only)
    print(summary.reply or summary.message)
    print()
    print(f"处理完成：成功 {summary.success}，失败 {summary.failed}")
    return 0 if summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
