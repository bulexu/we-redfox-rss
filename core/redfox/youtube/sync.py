"""YouTube 关键词订阅同步。"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from core.models.feed import Feed
from core.redfox.foreign_sync import AUTO_DISABLE_ERROR_THRESHOLD, as_int, run_keyword_job

from .client import PAGE_SIZE, iter_search_videos

YOUTUBE_KW_PREFIX = "YOUTUBE_KW_"


def build_feed_id(kind: str, target: str) -> str:
    if kind != "keyword":
        raise ValueError(f"未知 kind: {kind!r}")
    return f"{YOUTUBE_KW_PREFIX}{uuid.uuid4().hex[:16]}"


def parse_publish_time(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)) or str(value).isdigit():
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    text = str(value).strip()
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        pass
    match = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", text, re.I)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        days = {"day": 1, "week": 7, "month": 30, "year": 365}.get(unit, 0) * amount
        delta = timedelta(days=days, hours=amount if unit == "hour" else 0,
                          minutes=amount if unit == "minute" else 0,
                          seconds=amount if unit == "second" else 0)
        return int((datetime.now(timezone.utc) - delta).timestamp())
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d %b %Y"):
        try:
            return int(datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return 0


def _normalize_video(video: Dict[str, Any]) -> Dict[str, Any]:
    video_id = str(video.get("videoId") or video.get("id") or "").strip()
    if not video_id:
        return {}
    title = str(video.get("title") or "").strip()
    description = str(video.get("description") or "").strip()
    thumbnails = video.get("thumbnails") if isinstance(video.get("thumbnails"), list) else []
    thumbnail_urls = [str(t.get("url") or "").strip() for t in thumbnails if isinstance(t, dict)]
    thumbnail_urls = [url for url in thumbnail_urls if url]
    cover = thumbnail_urls[-1] if thumbnail_urls else str(video.get("thumbnailUrl") or "").strip()
    author = str(video.get("author") or video.get("channelName") or "").strip()
    channel_id = str(video.get("channelId") or "").strip()
    extinfo = {
        "platform": "youtube", "video_id": video_id,
        "duration": video.get("duration") or "",
        "thumbnails": thumbnails,
    }
    return {
        "id": f"youtube_{video_id}", "title": title[:1000] or description[:280] or "(无标题)",
        "content": description, "description": description,
        "pic_url": cover[:500] or None,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "publish_time": parse_publish_time(video.get("publishedTime") or video.get("publishedAt")),
        "author": author[:255] or None, "author_id": channel_id[:255] or None,
        "image_urls": json.dumps(thumbnail_urls or ([cover] if cover else []), ensure_ascii=False),
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": as_int(video.get("likeCount")),
        "comments_count": as_int(video.get("commentCount")),
        "collected_count": 0,
        "read_count": as_int(video.get("viewCount")),
        "share_count": 0,
    }


def _fetch_videos(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    for raw in iter_search_videos(target, max_pages=max_pages):
        item = _normalize_video(raw)
        if not item:
            continue
        publish_time = item.get("publish_time") or 0
        if last_publish_time and publish_time and publish_time <= last_publish_time:
            continue
        results.append(item)
        if len(results) >= max_count:
            break
    return results


def do_job_youtube(feed: Feed, is_test: bool = False) -> List[Dict[str, Any]]:
    return run_keyword_job(feed, is_test, YOUTUBE_KW_PREFIX, "youtube", _fetch_videos)
