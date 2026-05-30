from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

DEFAULT_ACCOUNT_ID = os.getenv("VABOT_WEIXIN_ACCOUNT_ID", "")
DEFAULT_STATE_ROOT = Path(os.getenv("VABOT_WEIXIN_STATE_ROOT", "/openclaw-weixin"))
DEFAULT_CONFIG_FILE = Path(os.getenv("VABOT_OPENCLAW_CONFIG", "/openclaw-config/openclaw.json"))
DEFAULT_CDN_BASE_URL = os.getenv("VABOT_WEIXIN_CDN_BASE_URL", "https://novac2c.cdn.weixin.qq.com/c2c")
DEFAULT_CHANNEL_VERSION = os.getenv("VABOT_WEIXIN_CHANNEL_VERSION", "1.0.3")
REQUEST_TIMEOUT = int(os.getenv("VABOT_WEIXIN_TIMEOUT", "60"))
UPLOAD_TIMEOUT = int(os.getenv("VABOT_WEIXIN_UPLOAD_TIMEOUT", "180"))
MAX_SEND_FILES = int(os.getenv("VABOT_WEIXIN_MAX_SEND_FILES", "30"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg"}


class WeixinSendError(RuntimeError):
    pass


@dataclass
class WeixinAccount:
    account_id: str
    base_url: str
    cdn_base_url: str
    token: str
    to_user_id: str
    context_token: str | None = None
    route_tag: str | None = None
    channel_version: str = DEFAULT_CHANNEL_VERSION


@dataclass
class UploadedFileInfo:
    filekey: str
    download_encrypted_query_param: str
    aeskey_hex: str
    file_size: int
    file_size_ciphertext: int


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _state_paths(account_id: str) -> tuple[Path, Path]:
    account_file = DEFAULT_STATE_ROOT / "accounts" / f"{account_id}.json"
    context_file = DEFAULT_STATE_ROOT / "accounts" / f"{account_id}.context-tokens.json"
    return account_file, context_file


def _load_route_tag(account_id: str) -> str | None:
    try:
        if not DEFAULT_CONFIG_FILE.exists():
            return None
        cfg = _load_json(DEFAULT_CONFIG_FILE)
        section = ((cfg.get("channels") or {}).get("openclaw-weixin") or {})
        accounts = section.get("accounts") or {}
        value = None
        if isinstance(accounts, dict):
            value = (accounts.get(account_id) or {}).get("routeTag")
        if value is None:
            value = section.get("routeTag")
        if value is None:
            return None
        value = str(value).strip()
        return value or None
    except Exception:
        return None


def load_weixin_account(account_id: str = DEFAULT_ACCOUNT_ID) -> WeixinAccount:
    if not account_id:
        raise WeixinSendError("未配置 VABOT_WEIXIN_ACCOUNT_ID，请在 .env 中填写 OpenClaw 微信账号 ID。")
    account_file, context_file = _state_paths(account_id)
    if not account_file.exists():
        raise WeixinSendError(f"未找到微信账号文件：{account_file}")
    account = _load_json(account_file)
    token = str(account.get("token") or "").strip()
    if not token:
        raise WeixinSendError("微信账号 token 为空，请重新登录 OpenClaw 微信渠道")

    base_url = str(account.get("baseUrl") or "https://ilinkai.weixin.qq.com").rstrip("/")
    cdn_base_url = str(account.get("cdnBaseUrl") or DEFAULT_CDN_BASE_URL).rstrip("/")

    configured_to = os.getenv("VABOT_WEIXIN_TO_USER_ID", "").strip()
    context_token = None
    to_user_id = configured_to
    if context_file.exists():
        try:
            tokens = _load_json(context_file)
            if isinstance(tokens, dict) and tokens:
                if configured_to and configured_to in tokens:
                    context_token = str(tokens.get(configured_to) or "") or None
                else:
                    to_user_id = list(tokens.keys())[-1]
                    context_token = str(tokens.get(to_user_id) or "") or None
        except Exception:
            pass
    if not to_user_id:
        to_user_id = str(account.get("userId") or "").strip()
    if not to_user_id:
        raise WeixinSendError("未找到微信接收用户 ID，请先从微信给机器人发一条消息")

    return WeixinAccount(
        account_id=account_id,
        base_url=base_url,
        cdn_base_url=cdn_base_url,
        token=token,
        to_user_id=to_user_id,
        context_token=context_token,
        route_tag=_load_route_tag(account_id),
        channel_version=DEFAULT_CHANNEL_VERSION,
    )


def _wechat_uin() -> str:
    return base64.b64encode(str(secrets.randbelow(2**32 - 1) + 1).encode("utf-8")).decode("ascii")


def _headers(account: WeixinAccount, body: bytes | str) -> dict[str, str]:
    if isinstance(body, str):
        body_len = len(body.encode("utf-8"))
    else:
        body_len = len(body)
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(body_len),
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {account.token}",
        "X-WECHAT-UIN": _wechat_uin(),
    }
    if account.route_tag:
        headers["SKRouteTag"] = account.route_tag
    return headers


def _api_post(account: WeixinAccount, endpoint: str, payload: dict[str, Any], timeout: int = REQUEST_TIMEOUT) -> dict[str, Any]:
    payload = dict(payload)
    payload.setdefault("base_info", {"channel_version": account.channel_version})
    body_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    url = f"{account.base_url}/ilink/bot/{endpoint}"
    response = requests.post(url, data=body_text.encode("utf-8"), headers=_headers(account, body_text), timeout=timeout)
    response.raise_for_status()
    try:
        data = response.json() if response.text.strip() else {}
    except Exception:
        raise WeixinSendError(f"微信接口返回非 JSON：{response.text[:300]}")
    ret = data.get("ret")
    if ret not in (None, 0):
        raise WeixinSendError(f"微信接口 {endpoint} 返回 ret={ret}：{data}")
    return data


def _send_message(account: WeixinAccount, item: dict[str, Any]) -> None:
    payload = {
        "msg": {
            "from_user_id": "",
            "to_user_id": account.to_user_id,
            "client_id": "vabot-" + secrets.token_hex(8),
            "message_type": 2,
            "message_state": 2,
            "item_list": [item],
            "context_token": account.context_token,
        }
    }
    _api_post(account, "sendmessage", payload)


def send_text(text: str) -> None:
    account = load_weixin_account()
    _send_message(account, {"type": 1, "text_item": {"text": text}})


def _aes_padded_size(size: int) -> int:
    return ((size + 1 + 15) // 16) * 16


def _aes_encrypt_ecb(plaintext: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(pad(plaintext, AES.block_size))


def _cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    return f"{cdn_base_url}/upload?encrypted_query_param={quote(upload_param, safe='')}&filekey={quote(filekey, safe='')}"


def upload_file(account: WeixinAccount, file_path: Path, media_type: int) -> UploadedFileInfo:
    plaintext = file_path.read_bytes()
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    filesize = _aes_padded_size(rawsize)
    filekey = secrets.token_hex(16)
    aeskey = secrets.token_bytes(16)
    upload_req = {
        "filekey": filekey,
        "media_type": media_type,
        "to_user_id": account.to_user_id,
        "rawsize": rawsize,
        "rawfilemd5": rawfilemd5,
        "filesize": filesize,
        "no_need_thumb": True,
        "aeskey": aeskey.hex(),
    }
    upload_resp = _api_post(account, "getuploadurl", upload_req)
    upload_param = upload_resp.get("upload_param")
    upload_full_url = upload_resp.get("upload_full_url")
    if upload_full_url:
        cdn_url = str(upload_full_url)
    elif upload_param:
        cdn_url = _cdn_upload_url(account.cdn_base_url, str(upload_param), filekey)
    else:
        raise WeixinSendError(f"getuploadurl 未返回 upload_param：{upload_resp}")

    ciphertext = _aes_encrypt_ecb(plaintext, aeskey)
    last_error = None
    download_param = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                cdn_url,
                data=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
                timeout=UPLOAD_TIMEOUT,
            )
            if resp.status_code >= 400 and resp.status_code < 500:
                raise WeixinSendError(f"CDN 上传客户端错误 {resp.status_code}：{resp.text[:300]}")
            if resp.status_code != 200:
                raise WeixinSendError(f"CDN 上传服务端错误 {resp.status_code}：{resp.text[:300]}")
            download_param = resp.headers.get("x-encrypted-param") or resp.headers.get("X-Encrypted-Param")
            if not download_param:
                raise WeixinSendError("CDN 上传返回缺少 x-encrypted-param")
            break
        except Exception as exc:
            last_error = exc
            if attempt >= 3:
                raise
            time.sleep(1)
    if not download_param:
        raise WeixinSendError(f"CDN 上传失败：{last_error}")
    return UploadedFileInfo(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aeskey_hex=aeskey.hex(),
        file_size=rawsize,
        file_size_ciphertext=len(ciphertext),
    )


def _cdn_media(uploaded: UploadedFileInfo) -> dict[str, Any]:
    return {
        "encrypt_query_param": uploaded.download_encrypted_query_param,
        "aes_key": base64.b64encode(bytes.fromhex(uploaded.aeskey_hex)).decode("ascii"),
        "encrypt_type": 1,
    }


def _file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return "file"


def send_file(path: str | Path, caption: str = "") -> tuple[bool, str]:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return False, f"文件不存在：{file_path}"
    account = load_weixin_account()
    kind = _file_kind(file_path)
    media_type = 1 if kind == "image" else 2 if kind == "video" else 3
    uploaded = upload_file(account, file_path, media_type)

    if caption:
        _send_message(account, {"type": 1, "text_item": {"text": caption}})

    if kind == "image":
        item = {
            "type": 2,
            "image_item": {
                "media": _cdn_media(uploaded),
                "mid_size": uploaded.file_size_ciphertext,
            },
        }
    elif kind == "video":
        item = {
            "type": 5,
            "video_item": {
                "media": _cdn_media(uploaded),
                "video_size": uploaded.file_size_ciphertext,
            },
        }
    else:
        item = {
            "type": 4,
            "file_item": {
                "media": _cdn_media(uploaded),
                "file_name": file_path.name,
                "len": str(uploaded.file_size),
            },
        }
    _send_message(account, item)
    return True, file_path.name


def send_files(paths: list[str]) -> dict[str, Any]:
    sent: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    cleaned = []
    for p in paths:
        s = str(p).strip()
        if s and s not in cleaned:
            cleaned.append(s)
    if len(cleaned) > MAX_SEND_FILES:
        skipped = cleaned[MAX_SEND_FILES:]
        cleaned = cleaned[:MAX_SEND_FILES]
    for idx, file in enumerate(cleaned, start=1):
        try:
            ok, msg = send_file(file, caption="" if idx > 1 else f"VABot 开始发送本次保存的 {len(cleaned)} 个文件。")
            if ok:
                sent.append(msg)
            else:
                failed.append(msg)
        except Exception as exc:
            failed.append(f"{Path(file).name}：{exc}")
    return {"sent": sent, "failed": failed, "skipped": skipped}


def send_files_reply(paths: list[str]) -> str:
    if not paths:
        return "没有可发送的文件。本次对话已结束。"
    try:
        result = send_files(paths)
    except Exception as exc:
        return f"发送文件失败：{exc}\n文件已保存在飞牛对应目录。"
    lines = ["📤 文件发送完成。", f"成功：{len(result['sent'])} 个", f"失败：{len(result['failed'])} 个"]
    if result["failed"]:
        lines.append("")
        lines.append("失败详情：")
        for item in result["failed"][:10]:
            lines.append(f"- {item}")
    if result["skipped"]:
        lines.append("")
        lines.append(f"还有 {len(result['skipped'])} 个文件超过发送上限，已保留在飞牛目录。")
    return "\n".join(lines).strip()
