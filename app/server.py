from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from app.processor import BatchSummary, process_text
from app.daily60s import start_60s_scheduler, send_60s_now
from app.link_extractor import extract_links

HOST = os.getenv("VABOT_HOST", "0.0.0.0")
PORT = int(os.getenv("VABOT_PORT", "18088"))
TOKEN = os.getenv("VABOT_TOKEN", "").strip()

PENDING_PATH = Path(os.getenv("VABOT_PENDING_FILE", "/app/data/pending.json"))
MODE_TIMEOUT_SECONDS = int(os.getenv("VABOT_MODE_TIMEOUT_SECONDS", "120"))
SEND_TIMEOUT_SECONDS = int(os.getenv("VABOT_SEND_TIMEOUT_SECONDS", "20"))

def _mode_menu_text(count: int) -> str:
    # 单链接绝不显示“批量模式”；多链接只统一询问一次。
    if count <= 1:
        prefix = "🔎 检测到 1 个链接。"
    else:
        prefix = f"📦 检测到 {count} 个链接，将按同一套规则批量处理。"
    return f"""{prefix}

请选择处理方式：
1️⃣ 视频 / 图文 / 实况提取（普通视频会同时保存视频 + 音频）
2️⃣ 仅保存音乐 / 提取音频
0️⃣ 取消

⏳ 请在 2 分钟内回复序号，超时自动取消。"""

SAVE_MENU_TEXT = """📁 请选择保存方式（只需选择一次，批量链接会统一应用）：
1️⃣ 保存到默认文件夹
   视频 / 图文 / 实况 → 视频
   音乐 / 音频 → 音乐
2️⃣ 新建文件夹保存
0️⃣ 取消

⏳ 请在 2 分钟内回复序号，超时自动取消。"""

SEND_MENU_TEXT = """\n\n📮 要把这次保存的文件发到微信吗？
1️⃣ 发送文件
0️⃣ 不发送

⏳ 20 秒内不回复，默认结束本次对话。"""


def _now() -> int:
    return int(time.time())


def _load_pending() -> dict[str, Any]:
    try:
        if PENDING_PATH.exists():
            value = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        pass
    return {}


def _save_pending(payload: dict[str, Any]) -> None:
    try:
        PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload["updated_at"] = _now()
        PENDING_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"VABot pending save failed: {exc}")


def _save_mode_pending(text: str, links: list[str]) -> None:
    _save_pending({
        "state": "choose_mode",
        "text": text,
        "links": links,
    })


def _save_storage_pending(text: str, links: list[str], mode: str) -> None:
    _save_pending({
        "state": "choose_save",
        "text": text,
        "links": links,
        "mode": mode,
    })


def _clear_pending() -> None:
    try:
        if PENDING_PATH.exists():
            PENDING_PATH.unlink()
    except Exception:
        pass


def _pending_age(pending: dict[str, Any]) -> int:
    try:
        return max(0, _now() - int(pending.get("updated_at") or 0))
    except Exception:
        return 999999


def _pending_expired(pending: dict[str, Any]) -> bool:
    if not pending:
        return False
    state = pending.get("state")
    age = _pending_age(pending)
    if state in {"choose_mode", "choose_save"}:
        return age > MODE_TIMEOUT_SECONDS
    if state == "send_prompt":
        return age > SEND_TIMEOUT_SECONDS
    return age > MODE_TIMEOUT_SECONDS


def _mode_choice(text: str) -> str:
    normalized = (text or "").strip().lower()
    mapping = {
        "1": "video", "一": "video", "视频": "video", "保存视频": "video", "图文": "video", "实况": "video",
        "2": "audio", "二": "audio", "音频": "audio", "音乐": "audio", "提取音频": "audio", "仅音频": "audio",
        "0": "cancel", "取消": "cancel", "退出": "cancel", "不要": "cancel", "不处理": "cancel",
    }
    return mapping.get(normalized, "")


def _save_choice(text: str) -> str:
    normalized = (text or "").strip().lower()
    mapping = {
        "1": "default", "一": "default", "默认": "default", "默认位置": "default", "保存": "default",
        "2": "new_folder", "二": "new_folder", "新建": "new_folder", "新建文件夹": "new_folder", "文件夹": "new_folder",
        "0": "cancel", "取消": "cancel", "退出": "cancel", "不要": "cancel", "不处理": "cancel",
    }
    return mapping.get(normalized, "")


def _send_choice(text: str) -> str:
    normalized = (text or "").strip().lower()
    mapping = {
        "1": "send", "发送": "send", "发": "send", "要": "send", "是": "send", "yes": "send", "y": "send",
        "0": "end", "不发送": "end", "不要": "end", "否": "end", "取消": "end", "结束": "end", "no": "end", "n": "end",
    }
    return mapping.get(normalized, "")


def _all_saved_files(summary: BatchSummary) -> list[str]:
    files: list[str] = []
    for item in summary.results:
        if item.status == "成功":
            for file in item.files:
                if file not in files:
                    files.append(file)
    return files


def _save_send_pending(files: list[str], reply: str) -> None:
    if not files:
        return
    _save_pending({
        "state": "send_prompt",
        "files": files,
        "reply": reply,
    })


def _file_list_reply(files: list[str]) -> str:
    if not files:
        return "没有可发送的文件。本次对话已结束。"
    lines = [
        "📦 已保存文件清单：",
        "",
    ]
    shown = files[:20]
    for index, file in enumerate(shown, start=1):
        lines.append(f"{index}. {Path(file).name}")
        lines.append(f"   {file}")
    if len(files) > len(shown):
        lines.append(f"还有 {len(files) - len(shown)} 个文件未列出。")
    lines.append("")
    lines.append("当前微信直连本地模型通道暂时不能直接回传文件本体，先发送文件清单；文件已保存在飞牛对应目录。")
    return "\n".join(lines).strip()


def _strip_openclaw_metadata(text: str) -> str:
    """Remove OpenClaw channel metadata wrapper and keep the real user message.

    Weixin messages arrive as:
    Conversation info ... ```json ... ```

    real user text

    If we do not strip this, replies like "1" become a long metadata block plus "1",
    so menu choices fail and VABot asks the same question again.
    """
    value = (text or "").strip()
    if not value:
        return ""
    if value.startswith("Conversation info"):
        parts = value.split("```")
        if len(parts) >= 3:
            value = "```".join(parts[2:]).strip()
    return value.strip()


def _choice_text(text: str) -> str:
    value = _strip_openclaw_metadata(text)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return lines[-1] if lines else value.strip()


def _openclaw_message_millis(raw_text: str) -> int:
    """Extract OpenClaw/Weixin message timestamp from the metadata wrapper.

    OpenClaw may send the whole conversation history to the local model. If we
    scan all historical user messages for links, an old batch link can be
    treated as the current message. The Weixin metadata contains a monotonic
    message id like `openclaw-weixin:1779576901167-...`; use it to find the
    real latest inbound message.
    """
    m = re.search(r"openclaw-weixin:(\d+)-", raw_text or "")
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def _extract_user_entries_from_chat(data: dict[str, Any]) -> list[dict[str, Any]]:
    messages = data.get("messages") or []
    entries: list[dict[str, Any]] = []
    if isinstance(messages, list):
        for idx, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                raw = _extract_text_from_content(msg.get("content"))
                text = _strip_openclaw_metadata(raw).strip()
                if text:
                    entries.append({"index": idx, "text": text, "millis": _openclaw_message_millis(raw)})
    return entries


def _extract_user_texts_from_chat(data: dict[str, Any]) -> list[str]:
    """Return all stripped user texts in stable chronological order."""
    entries = _extract_user_entries_from_chat(data)
    return [str(e["text"]) for e in entries]


def _current_user_text_from_chat(data: dict[str, Any]) -> str:
    """Return only the current/latest user message, not old history.

    This is important for commands like `60s` and `取消`: old links remain in
    the OpenClaw conversation history, but they must not start a new batch task.
    """
    entries = _extract_user_entries_from_chat(data)
    if not entries:
        return _strip_openclaw_metadata(_extract_user_text_from_chat(data)).strip()
    with_millis = [e for e in entries if int(e.get("millis") or 0) > 0]
    if with_millis:
        return str(max(with_millis, key=lambda e: int(e.get("millis") or 0))["text"]).strip()
    return str(entries[-1]["text"]).strip()


def _pick_menu_reply(data: dict[str, Any], state: str) -> str:
    """Pick the actual Weixin menu reply.

    Prefer the latest inbound message by Weixin metadata. This prevents an old
    `1` or old link in the conversation history from being reused.
    """

    def valid(token: str) -> bool:
        if state == "choose_mode":
            return bool(_mode_choice(token))
        if state == "choose_save":
            return bool(_save_choice(token))
        if state == "send_prompt":
            return bool(_send_choice(token))
        return False

    current = _current_user_text_from_chat(data)
    if valid(_choice_text(current)):
        return current

    # Fallback for gateways that strip metadata: scan backwards for a valid standalone choice.
    texts = _extract_user_texts_from_chat(data)
    for text in reversed(texts):
        token = _choice_text(text)
        if valid(token):
            return text
    return current or (texts[-1] if texts else "")


def _pick_latest_link_text(data: dict[str, Any]) -> str:
    # Only inspect the current/latest user message. Do not reuse old links from history.
    return _current_user_text_from_chat(data)


def _last_user_link_text(messages: list[Any], skip_latest: bool = True) -> str:
    if not isinstance(messages, list):
        return ""
    iterable = list(reversed(messages[:-1] if skip_latest else messages))
    for msg in iterable:
        if isinstance(msg, dict) and msg.get("role") == "user":
            text = _strip_openclaw_metadata(_extract_text_from_content(msg.get("content")))
            if extract_links(text):
                return text.strip()
    return ""


def _process_summary_with_send_prompt(pending_text: str, *, audio_only: bool, save_mode: str = "default") -> str:
    summary = process_text(pending_text, audio_only=audio_only, save_mode=save_mode)
    base_reply = summary.reply or summary.message or "VABot 没有返回内容。"
    # 微信媒体直传在当前插件链路中容易出现大文件、灰色占位或无法播放，
    # v1.4 起默认不再询问/发送文件，只保留飞牛本地保存和路径回复。
    _clear_pending()
    return base_reply + "\n\n📌 文件已保存在飞牛对应文件夹，不再自动回传到微信。"


def _process_chat_dialog(data: dict[str, Any]) -> str:
    messages = data.get("messages") or []
    pending = _load_pending()

    current_text = _current_user_text_from_chat(data)
    current_choice = _choice_text(current_text)

    # Global commands should use the current message only. They should not be
    # swallowed by an old pending batch or by historical links.
    manual_key = current_choice.strip().lower()
    if manual_key in {"60s", "每日新闻", "60秒", "60秒看世界", "新闻"}:
        _clear_pending()
        ok, message = send_60s_now(reason="manual")
        return message if ok else f"60s 推送失败：{message}"
    if manual_key in {"取消", "退出", "0"} and pending.get("state") not in {"choose_mode", "choose_save"}:
        _clear_pending()
        return "✅ 已取消当前会话。请发送新的链接继续处理。"

    if pending.get("state") in {"choose_mode", "choose_save", "send_prompt"}:
        latest_text = _pick_menu_reply(data, str(pending.get("state")))
    else:
        latest_text = current_text
    latest_text = _strip_openclaw_metadata(latest_text)
    latest_choice = _choice_text(latest_text)

    print(f"VABot dialog state={pending.get('state') or 'none'} current={current_choice!r} choice={latest_choice!r} links={len(extract_links(latest_text))}")

    pending = _load_pending()
    if pending and _pending_expired(pending):
        old_state = str(pending.get("state") or "")

        # 如果用户已经回了有效序号，即使经过 OpenClaw 转发有几秒延迟，仍然继续处理。
        valid_late_choice = False
        if old_state == "send_prompt" and _send_choice(latest_choice):
            valid_late_choice = True
        elif old_state == "choose_mode" and _mode_choice(latest_choice):
            valid_late_choice = True
        elif old_state == "choose_save" and _save_choice(latest_choice):
            valid_late_choice = True

        if not valid_late_choice:
            _clear_pending()
            # If the current message contains a new link, continue normally below.
            if not extract_links(latest_text):
                if old_state in {"choose_mode", "choose_save"}:
                    return "⏳ 上次任务已超过 2 分钟未选择，已自动取消。请重新发送链接。"
                if old_state == "send_prompt":
                    return "⏳ 上次发送询问已超过 20 秒未回复，已默认结束本次对话。请发送新的链接。"

    pending = _load_pending()
    if pending.get("state") in {"choose_mode", "choose_save", "send_prompt"}:
        latest_text = _pick_menu_reply(data, str(pending.get("state")))
        latest_text = _strip_openclaw_metadata(latest_text)
        latest_choice = _choice_text(latest_text)

    if pending.get("state") == "send_prompt":
        # v1.4 已关闭微信文件直传，兼容旧版本遗留的 send_prompt 状态。
        _clear_pending()
        if not extract_links(latest_text):
            return "📌 微信文件回传已关闭。文件已保存在飞牛对应目录，请发送新的链接继续处理。"

    pending = _load_pending()
    if pending.get("state") == "choose_save":
        choice = _save_choice(latest_choice)
        if choice == "cancel":
            _clear_pending()
            return "✅ 已取消本次处理。"
        if choice in {"default", "new_folder"}:
            pending_text = str(pending.get("text") or "").strip()
            mode = str(pending.get("mode") or "video")
            if not extract_links(pending_text):
                pending_text = _last_user_link_text(messages, skip_latest=True)
            if not extract_links(pending_text):
                _clear_pending()
                return "没有找到上一条待处理链接，请重新发送视频、图文、实况或音乐链接。"
            _clear_pending()
            return _process_summary_with_send_prompt(
                pending_text,
                audio_only=(mode == "audio"),
                save_mode=choice,
            )
        if not extract_links(latest_text):
            return SAVE_MENU_TEXT

    pending = _load_pending()
    if pending.get("state") == "choose_mode":
        choice = _mode_choice(latest_choice)
        if choice == "cancel":
            _clear_pending()
            return "✅ 已取消本次处理。"
        if choice in {"video", "audio"}:
            pending_text = str(pending.get("text") or "").strip()
            links = [str(x) for x in pending.get("links") or [] if str(x).strip()]
            if not extract_links(pending_text):
                pending_text = _last_user_link_text(messages, skip_latest=True)
                links = extract_links(pending_text)
            if not links:
                _clear_pending()
                return "没有找到上一条待处理链接，请重新发送视频、图文、实况或音乐链接。"
            _save_storage_pending(pending_text, links, choice)
            return SAVE_MENU_TEXT
        if not extract_links(latest_text):
            return _mode_menu_text(len(pending.get("links") or []) or 1)

    link_text = _pick_latest_link_text(data)
    links = extract_links(link_text)
    if links:
        _save_mode_pending(link_text, links)
        return _mode_menu_text(len(links))

    return "还没有检测到链接，请发送抖音 / 小红书 / 汽水音乐等分享链接。"


def _extract_text_from_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def _extract_user_text_from_chat(data: dict[str, Any]) -> str:
    messages = data.get("messages") or []
    if isinstance(messages, list):
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                text = _extract_text_from_content(msg.get("content"))
                text = _strip_openclaw_metadata(text)
                text = _strip_openclaw_metadata(text)
                if text.strip():
                    return text.strip()
        for msg in reversed(messages):
            if isinstance(msg, dict):
                text = _extract_text_from_content(msg.get("content"))
                text = _strip_openclaw_metadata(text)
                text = _strip_openclaw_metadata(text)
                if text.strip():
                    return text.strip()
    return str(data.get("prompt") or data.get("input") or "").strip()


def _extract_user_text_from_responses(data: dict[str, Any]) -> str:
    value = data.get("input")
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("role") == "user" or item.get("type") in {"message", "input_text"}:
                    text = _extract_text_from_content(item.get("content") or item.get("text"))
                    if text:
                        parts.append(text)
        if parts:
            return "\n".join(parts).strip()
    return _extract_user_text_from_chat(data)


def _openai_models_payload() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": "vabot",
                "object": "model",
                "created": 1770000000,
                "owned_by": "local",
            }
        ],
    }


def _chat_completion_payload(model: str, reply: str) -> dict[str, Any]:
    now = int(time.time())
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": now,
        "model": model or "vabot",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _responses_payload(model: str, reply: str) -> dict[str, Any]:
    rid = f"resp_{uuid.uuid4().hex}"
    mid = f"msg_{uuid.uuid4().hex}"
    return {
        "id": rid,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model or "vabot",
        "output_text": reply,
        "output": [
            {
                "id": mid,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": reply, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _split_stream_text(text: str, size: int = 256) -> list[str]:
    if not text:
        return [""]
    return [text[i:i + size] for i in range(0, len(text), size)]


class VABotHandler(BaseHTTPRequestHandler):
    server_version = "VABotHTTP/1.1"
    protocol_version = "HTTP/1.1"

    def _write_chunked_bytes(self, payload: bytes) -> None:
        self.wfile.write(f"{len(payload):X}\r\n".encode("ascii"))
        self.wfile.write(payload)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def _finish_chunked(self) -> None:
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse_header(self) -> tuple[str, int]:
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        return f"chatcmpl-{uuid.uuid4().hex}", int(time.time())

    def _write_sse_chat_chunk(self, cid: str, created: int, model: str, delta: dict[str, Any], finish_reason: str | None = None) -> None:
        chunk = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model or "vabot",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
        line = f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")
        self._write_chunked_bytes(line)

    def _write_sse_done(self) -> None:
        self._write_chunked_bytes(b"data: [DONE]\n\n")
        self._finish_chunked()

    def _send_sse_chat(self, model: str, data: dict[str, Any]) -> None:
        cid, now = self._send_sse_header()
        try:
            reply = _process_chat_dialog(data)
        except Exception as exc:
            reply = f"VABot 处理失败：{exc}"
        self._write_sse_chat_chunk(cid, now, model, {"role": "assistant"})
        for part in _split_stream_text(reply):
            self._write_sse_chat_chunk(cid, now, model, {"content": part})
        self._write_sse_chat_chunk(cid, now, model, {}, finish_reason="stop")
        self._write_sse_done()
        print(f"VABot stream completed: chars={len(reply)}")

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length > 0 else b""

    def _authorized(self) -> bool:
        if not TOKEN:
            return True
        header_token = self.headers.get("X-VABOT-Token", "").strip()
        auth = self.headers.get("Authorization", "").strip()
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return header_token == TOKEN or bearer == TOKEN

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/v1/models", "/models"}:
            self._send_json(200, _openai_models_payload())
            return
        if path in {"/", "/health"}:
            self._send_json(200, {
                "ok": True,
                "service": "VABot",
                "version": "1.5",
                "state_file": str(PENDING_PATH),
                "timeouts": {"mode_seconds": MODE_TIMEOUT_SECONDS, "send_seconds": SEND_TIMEOUT_SECONDS},
                "endpoints": ["POST /parse", "POST /wechat", "GET /v1/models", "POST /v1/chat/completions", "POST /v1/responses"],
                "daily_60s": {"enabled": os.getenv("VABOT_60S_ENABLED", "true"), "times": os.getenv("VABOT_60S_TIMES", "08:00,20:00")},
            })
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {"/parse", "/wechat", "/v1/chat/completions", "/chat/completions", "/v1/responses", "/responses"}:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        raw = self._read_body()
        content_type = self.headers.get("Content-Type", "")
        try:
            if "application/json" in content_type:
                data = json.loads(raw.decode("utf-8") or "{}")
            else:
                data = {"text": raw.decode("utf-8", errors="ignore")}
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": f"bad request: {exc}"})
            return

        if path in {"/v1/chat/completions", "/chat/completions"}:
            text = _extract_user_text_from_chat(data)
            model = str(data.get("model") or "vabot")
            print(f"VABot chat request: stream={bool(data.get('stream'))} text_len={len(text)}")
            if bool(data.get("stream")):
                self._send_sse_chat(model, data)
            else:
                reply = _process_chat_dialog(data)
                self._send_json(200, _chat_completion_payload(model, reply))
            return

        if path in {"/v1/responses", "/responses"}:
            text = _extract_user_text_from_responses(data)
            summary = process_text(text)
            reply = summary.reply or summary.message or "VABot 没有返回内容。"
            model = str(data.get("model") or "vabot")
            self._send_json(200, _responses_payload(model, reply))
            return

        try:
            text = str(data.get("text") or data.get("message") or data.get("content") or "")
            mode = str(data.get("mode") or "auto").lower()
            force_music = bool(data.get("music") or mode == "music")
            audio_only = bool(data.get("audio_only") or mode in {"audio", "audio_only"})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": f"bad request: {exc}"})
            return

        summary = process_text(text, force_music=force_music, audio_only=audio_only)
        self._send_json(200 if summary.ok else 207, summary.to_dict())


def main() -> int:
    start_60s_scheduler()
    httpd = ThreadingHTTPServer((HOST, PORT), VABotHandler)
    print(f"VABot HTTP server started: http://{HOST}:{PORT}")
    print("Endpoints: POST /parse, POST /wechat, GET /health, GET /v1/models, POST /v1/chat/completions, POST /v1/responses")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
