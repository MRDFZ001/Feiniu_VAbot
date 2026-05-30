"""OpenClaw 微信发送测试脚本。

使用前请先通过环境变量配置以下值，不要把真实路径和账号 ID 写进代码：

- VABOT_WEIXIN_ACCOUNT_ID
- OPENCLAW_BASE_DIR，例如 /path/to/.openclaw
"""

from __future__ import annotations

import base64
import json
import os
import random
import time
import urllib.request
from pathlib import Path

ACCOUNT_ID = os.getenv("VABOT_WEIXIN_ACCOUNT_ID", "").strip()
BASE = Path(os.getenv("OPENCLAW_BASE_DIR", "")).expanduser()

if not ACCOUNT_ID:
    raise SystemExit("请先设置环境变量 VABOT_WEIXIN_ACCOUNT_ID")
if not str(BASE) or str(BASE) == ".":
    raise SystemExit("请先设置环境变量 OPENCLAW_BASE_DIR")

ACCOUNT_FILE = BASE / "openclaw-weixin" / "accounts" / f"{ACCOUNT_ID}.json"
CONTEXT_FILE = BASE / "openclaw-weixin" / "accounts" / f"{ACCOUNT_ID}.context-tokens.json"
PLUGIN_PACKAGE = BASE / "extensions" / "openclaw-weixin" / "package.json"
CONFIG_FILE = BASE / "openclaw.json"

account = json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
base_url = account.get("baseUrl", "https://ilinkai.weixin.qq.com").rstrip("/")
token = account.get("token", "")

if not token:
    raise SystemExit("没有读取到 token")

tokens = {}
if CONTEXT_FILE.exists():
    tokens = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))

if not tokens:
    raise SystemExit("没有读取到 context token，请先从微信给机器人发一条消息。")

to_user_id = list(tokens.keys())[-1]
context_token = tokens[to_user_id]

try:
    channel_version = json.loads(PLUGIN_PACKAGE.read_text(encoding="utf-8")).get("version", "1.0.3")
except Exception:
    channel_version = "1.0.3"

route_tag = ""
try:
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    route_tag = cfg.get("channels", {}).get("openclaw-weixin", {}).get("routeTag", "")
except Exception:
    route_tag = ""

client_id = "vabot-test-" + str(int(time.time()))
body = {
    "msg": {
        "from_user_id": "",
        "to_user_id": to_user_id,
        "client_id": client_id,
        "message_type": 2,
        "message_state": 2,
        "item_list": [{"type": 1, "text_item": {"text": "VABot 微信插件直连测试成功。"}}],
        "context_token": context_token,
    },
    "base_info": {"channel_version": channel_version},
}
if route_tag:
    body["base_info"]["route_tag"] = route_tag

raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
uin = base64.b64encode(str(random.randint(100000000, 4294967295)).encode()).decode()
headers = {
    "Content-Type": "application/json",
    "Content-Length": str(len(raw)),
    "AuthorizationType": "ilink_bot_token",
    "Authorization": "Bearer " + token,
    "X-WECHAT-UIN": uin,
}

req = urllib.request.Request(base_url + "/cgi-bin/mmwebwx-bin/webwxsendmsg", data=raw, headers=headers, method="POST")
with urllib.request.urlopen(req, timeout=60) as resp:
    print(resp.status)
    print(resp.read().decode("utf-8", errors="ignore"))
