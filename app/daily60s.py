from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from zoneinfo import ZoneInfo

from app.weixin_sender import send_text

DEFAULT_API = "https://60s.viki.moe/v2/60s?encoding=text"
STATE_FILE = Path(os.getenv("VABOT_60S_STATE_FILE", "/app/data/60s_push_state.json"))


def _enabled() -> bool:
    return os.getenv("VABOT_60S_ENABLED", "true").strip().lower() in {"1", "true", "yes", "y", "on"}


def _timezone() -> ZoneInfo:
    name = os.getenv("TZ", "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _times() -> list[tuple[int, int]]:
    raw = os.getenv("VABOT_60S_TIMES", "08:00,20:00")
    values: list[tuple[int, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h, m = part.split(":", 1)
            hour, minute = int(h), int(m)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                values.append((hour, minute))
        except Exception:
            continue
    return values or [(8, 0), (20, 0)]


def _api_url() -> str:
    return os.getenv("VABOT_60S_API", DEFAULT_API).strip() or DEFAULT_API


def _read_state() -> dict[str, Any]:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _write_state(data: dict[str, Any]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"60s state write failed: {exc}")


def _fetch_60s_text() -> str:
    url = _api_url()
    req = Request(url, headers={"User-Agent": "VABot/1.4"})
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
    if not body:
        raise RuntimeError("60s API 返回为空")

    # encoding=text 会直接返回文本；如果用户换成 JSON API，这里也尽量兼容。
    if body.startswith("{"):
        try:
            data = json.loads(body)
            items = data.get("data") or data.get("items") or data.get("news") or []
            if isinstance(items, dict):
                items = items.get("news") or items.get("list") or []
            lines: list[str] = []
            if isinstance(items, list):
                for idx, item in enumerate(items, start=1):
                    if isinstance(item, str):
                        lines.append(f"{idx}. {item}")
                    elif isinstance(item, dict):
                        title = item.get("title") or item.get("content") or item.get("text") or ""
                        if title:
                            lines.append(f"{idx}. {title}")
            tip = data.get("tip") or data.get("quote") or data.get("sentence") or ""
            if tip:
                lines.append("")
                lines.append(str(tip))
            if lines:
                body = "\n".join(lines)
        except Exception:
            pass

    header = "🌏 每天 60 秒读懂世界"
    today = datetime.now(_timezone()).strftime("%Y-%m-%d %H:%M")
    return f"{header}\n🕗 {today}\n\n{body}".strip()


def _split_text(text: str, limit: int = 1800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines():
        add = len(line) + 1
        if buf and size + add > limit:
            chunks.append("\n".join(buf).strip())
            buf, size = [], 0
        buf.append(line)
        size += add
    if buf:
        chunks.append("\n".join(buf).strip())
    return chunks


def send_60s_now(reason: str = "manual") -> tuple[bool, str]:
    try:
        text = _fetch_60s_text()
        parts = _split_text(text)
        for i, part in enumerate(parts, start=1):
            suffix = f"\n\n({i}/{len(parts)})" if len(parts) > 1 else ""
            send_text(part + suffix)
        print(f"60s push sent: reason={reason} parts={len(parts)}")
        return True, "🌏 60s 每日资讯已推送。"
    except Exception as exc:
        print(f"60s push failed: {exc}")
        return False, str(exc)


def _next_run(now: datetime) -> datetime:
    candidates: list[datetime] = []
    for day_offset in (0, 1):
        base = now.date() + timedelta(days=day_offset)
        for hour, minute in _times():
            candidates.append(datetime(base.year, base.month, base.day, hour, minute, tzinfo=now.tzinfo))
    future = [c for c in candidates if c > now]
    return min(future) if future else now + timedelta(hours=12)


def _scheduler_loop() -> None:
    tz = _timezone()
    print(f"60s scheduler enabled: times={os.getenv('VABOT_60S_TIMES', '08:00,20:00')} tz={tz.key if hasattr(tz, 'key') else tz}")
    while True:
        try:
            now = datetime.now(tz)
            target = _next_run(now)
            sleep_seconds = max(1, int((target - now).total_seconds()))
            # 最长 60 秒醒一次，便于修改环境后重启前不至于长睡；正式触发仍按 target 判断。
            time.sleep(min(sleep_seconds, 60))
            now = datetime.now(tz)
            for hour, minute in _times():
                if now.hour == hour and now.minute == minute:
                    slot = now.strftime(f"%Y-%m-%d {hour:02d}:{minute:02d}")
                    state = _read_state()
                    if state.get("last_slot") == slot:
                        continue
                    ok, msg = send_60s_now(reason=f"schedule:{slot}")
                    if ok:
                        state["last_slot"] = slot
                        state["last_message"] = msg
                        state["last_sent_at"] = datetime.now(tz).isoformat()
                        _write_state(state)
                    else:
                        state["last_error"] = msg
                        state["last_error_at"] = datetime.now(tz).isoformat()
                        _write_state(state)
        except Exception as exc:
            print(f"60s scheduler loop error: {exc}")
            time.sleep(30)


def start_60s_scheduler() -> None:
    if not _enabled():
        print("60s scheduler disabled")
        return
    thread = threading.Thread(target=_scheduler_loop, name="vabot-60s-scheduler", daemon=True)
    thread.start()
