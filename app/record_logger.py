from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.config import Config
from app.downloader import SaveResult
from app.models import MediaResult


def _value(value: object, default: str = "未获取") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _relative_or_abs(path: Path | None) -> str:
    if path is None:
        return "未保存"
    return str(path)


def append_record(config: Config, result: MediaResult, save: SaveResult) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = save.status or ("成功" if result.ok else "失败")
    files_text = "无"
    if save.files:
        files_text = "\n" + "\n".join(f"- {p.name}" for p in save.files)

    remark = save.note if status == "成功" else save.error or result.message
    if not remark:
        remark = "无"

    block = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
解析时间：{now}
状态：{status}
类型：{_value(result.display_type, "未知")}
平台：{_value(result.platform)}
标题：{_value(result.title)}
作者名称：{_value(result.author_name)}
作者粉丝：{_value(result.author_fans)}
作品链接：{_value(result.source_url)}
作品点赞数量：{_value(result.like_count)}
作品发布时间：{_value(result.publish_time)}
保存位置：{_relative_or_abs(save.save_dir)}
保存文件：{files_text}
接口：{_value(result.api_used, "未记录")}
备注：{remark}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
    config.log_dir.mkdir(parents=True, exist_ok=True)
    with config.record_file.open("a", encoding="utf-8") as fh:
        fh.write(block)
