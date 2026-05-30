from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import ConfigError, ensure_dirs, get_config
from app.downloader import SaveResult, save_result
from app.link_extractor import extract_links
from app.parser_api import parse_link
from app.record_logger import append_record
from app.models import MediaResult
from app.filename import safe_filename


@dataclass
class ItemSummary:
    index: int
    total: int
    link: str
    status: str
    media_type: str
    platform: str
    title: str
    author_name: str
    save_dir: str
    files: list[str] = field(default_factory=list)
    note: str = ""
    error: str = ""
    api_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "total": self.total,
            "link": self.link,
            "status": self.status,
            "media_type": self.media_type,
            "platform": self.platform,
            "title": self.title,
            "author_name": self.author_name,
            "save_dir": self.save_dir,
            "files": self.files,
            "note": self.note,
            "error": self.error,
            "api_used": self.api_used,
        }


@dataclass
class BatchSummary:
    ok: bool
    success: int = 0
    failed: int = 0
    message: str = ""
    reply: str = ""
    results: list[ItemSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "success": self.success,
            "failed": self.failed,
            "message": self.message,
            "reply": self.reply,
            "results": [item.to_dict() for item in self.results],
        }


def _path_text(path: Path | None) -> str:
    return str(path) if path else "未保存"


def _display_save_dir(path: Path | None) -> str:
    """Show user-facing folder names instead of container paths."""
    if path is None:
        return "未保存"
    config = get_config()
    try:
        p = Path(path)
        for base, label in ((config.video_dir, "视频"), (config.music_dir, "音乐")):
            try:
                rel = p.relative_to(base)
                if str(rel) == ".":
                    return label
                return f"{label}/{rel}"
            except ValueError:
                continue
    except Exception:
        pass
    return Path(path).name or str(path)


def _item_summary(index: int, total: int, link: str, result: MediaResult, saved: SaveResult) -> ItemSummary:
    return ItemSummary(
        index=index,
        total=total,
        link=link,
        status=saved.status,
        media_type=result.display_type,
        platform=result.platform,
        title=result.title,
        author_name=result.author_name,
        save_dir=_display_save_dir(saved.save_dir),
        files=[str(p) for p in saved.files],
        note=saved.note,
        error=saved.error,
        api_used=result.api_used,
    )


def _build_reply(summary: BatchSummary) -> str:
    if not summary.results:
        return summary.message or "没有处理结果。"

    lines: list[str] = []
    lines.append("✅ VABot 处理完成" if summary.failed == 0 else "⚠️ VABot 处理完成，部分失败")
    lines.append(f"📊 成功：{summary.success} 个，失败：{summary.failed} 个")
    lines.append("")

    for item in summary.results:
        icon = "✅" if item.status == "成功" else "❌"
        lines.append(f"{icon} [{item.index}/{item.total}] {item.media_type}｜{item.platform}")
        lines.append(f"🎬 标题：{item.title or '未获取'}")
        if item.status == "成功":
            lines.append(f"📁 保存到：{item.save_dir}")
            if item.files:
                shown = item.files[:6]
                lines.append("📄 保存文件：")
                for file in shown:
                    lines.append(f"• {Path(file).name}")
                if len(item.files) > len(shown):
                    lines.append(f"• 还有 {len(item.files) - len(shown)} 个文件")
            if item.note:
                lines.append(f"📝 备注：{item.note}")
        else:
            lines.append(f"失败原因：{item.error or '未知错误'}")
        lines.append("")

    return "\n".join(lines).strip()


def _batch_folder_name(total: int, first_title: str = "") -> str:
    if total == 1 and first_title:
        return safe_filename(first_title, default="作品")
    return "VABot批量_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _config_for_save_mode(config, result: MediaResult, total: int, save_mode: str, batch_folder: str | None):
    if save_mode != "new_folder":
        return config, batch_folder, ""

    if not batch_folder:
        batch_folder = _batch_folder_name(total, result.title)

    # 普通视频/图文/实况放到视频下的新文件夹；音乐/仅音频放到音乐下的新文件夹。
    if result.media_type in {"music", "audio"}:
        target = config.music_dir / batch_folder
        target.mkdir(parents=True, exist_ok=True)
        return replace(config, music_dir=target), batch_folder, f"已新建文件夹保存：音乐/{batch_folder}"

    target = config.video_dir / batch_folder
    target.mkdir(parents=True, exist_ok=True)
    return replace(config, video_dir=target), batch_folder, f"已新建文件夹保存：视频/{batch_folder}"


def process_text(text: str, *, force_music: bool = False, audio_only: bool = False, save_mode: str = "default") -> BatchSummary:
    raw_text = (text or "").strip()
    if not raw_text:
        return BatchSummary(ok=False, message="消息为空。", reply="没有收到可处理内容。")

    try:
        config = get_config()
        ensure_dirs(config)
    except ConfigError as exc:
        return BatchSummary(ok=False, message=str(exc), reply=str(exc))

    links = extract_links(raw_text)
    if not links:
        return BatchSummary(ok=False, message="没有检测到链接。", reply="没有检测到链接，请发送抖音/小红书/汽水音乐等分享链接。")

    summary = BatchSummary(ok=True, message=f"检测到 {len(links)} 个链接。")
    batch_folder: str | None = None

    for index, link in enumerate(links, start=1):
        result = parse_link(config, link, force_music=force_music)
        item_config, batch_folder, save_mode_note = _config_for_save_mode(config, result, len(links), save_mode, batch_folder)
        saved = save_result(item_config, result, audio_only=audio_only)
        if save_mode_note and saved.status == "成功":
            saved.note = (saved.note + "；" + save_mode_note) if saved.note else save_mode_note
        append_record(item_config, result, saved)
        item = _item_summary(index, len(links), link, result, saved)
        summary.results.append(item)
        if saved.status == "成功":
            summary.success += 1
        else:
            summary.failed += 1

    summary.ok = summary.failed == 0
    summary.reply = _build_reply(summary)
    return summary
