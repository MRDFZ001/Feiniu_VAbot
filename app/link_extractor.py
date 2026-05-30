from __future__ import annotations

import re

URL_RE = re.compile(r"https?://[^\s\]\[\)\(<>\"'，。；;、]+", re.IGNORECASE)


def extract_links(text: str) -> list[str]:
    links: list[str] = []
    for match in URL_RE.findall(text or ""):
        link = match.rstrip(".,!?。！？）)]}")
        if link not in links:
            links.append(link)
    return links


def detect_platform(url: str) -> str:
    lower = (url or "").lower()
    if "douyin" in lower or "iesdouyin" in lower:
        return "抖音"
    if "xiaohongshu" in lower or "xhslink" in lower:
        return "小红书"
    if "qishui" in lower:
        return "汽水音乐"
    if "kuaishou" in lower or "gifshow" in lower:
        return "快手"
    if "bilibili" in lower or "b23.tv" in lower:
        return "哔哩哔哩"
    if "tiktok" in lower:
        return "TikTok"
    if "youtube" in lower or "youtu.be" in lower:
        return "YouTube"
    if "instagram" in lower:
        return "Instagram"
    if "twitter" in lower or "x.com" in lower:
        return "X/Twitter"
    return "未知平台"
