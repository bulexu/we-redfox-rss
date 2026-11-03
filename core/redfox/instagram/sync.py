"""Instagram 关键词订阅同步。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List

from core.models.feed import Feed
from core.redfox.foreign_sync import AUTO_DISABLE_ERROR_THRESHOLD, as_int, run_keyword_job

from .client import PAGE_SIZE, iter_search_posts

INSTAGRAM_KW_PREFIX = "INSTAGRAM_KW_"


def build_feed_id(kind: str, target: str) -> str:
    if kind != "keyword":
        raise ValueError(f"未知 kind: {kind!r}")
    return f"{INSTAGRAM_KW_PREFIX}{uuid.uuid4().hex[:16]}"


def parse_publish_time(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)) or str(value).isdigit():
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _normalize_post(post: Dict[str, Any]) -> Dict[str, Any]:
    media_id = str(post.get("mediaId") or post.get("id") or post.get("code") or "").strip()
    code = str(post.get("code") or post.get("shortcode") or "").strip()
    if not media_id:
        return {}
    caption = str(post.get("captionText") or post.get("caption") or post.get("description") or "").strip()
    user = post.get("user") if isinstance(post.get("user"), dict) else {}
    username = str(user.get("username") or post.get("username") or "").lstrip("@").strip()
    full_name = str(user.get("fullName") or user.get("name") or username).strip()
    cover = str(post.get("imageUrl") or post.get("thumbnailUrl") or "").strip()
    url = str(post.get("postUrl") or "").strip() or (f"https://www.instagram.com/p/{code}/" if code else "")
    hashtags = post.get("captionHashtags") if isinstance(post.get("captionHashtags"), list) else []
    extinfo = {
        "platform": "instagram", "media_id": media_id, "code": code,
        "media_format": post.get("mediaFormat") or "",
        "media_type": post.get("mediaType"), "video_url": post.get("videoUrl") or "",
        "duration": post.get("videoDuration") or 0, "hashtags": hashtags,
        "followers": as_int(user.get("followerCount")),
        "avatar": user.get("profilePicUrl") or "", "verified": bool(user.get("isVerified")),
    }
    return {
        "id": f"instagram_{media_id}", "title": caption[:280] or "(无标题)",
        "content": caption, "description": caption,
        # Instagram CDN URL 带有较长的动态签名参数，不能按 500 字符截断。
        "pic_url": cover or None, "url": url[:500],
        "publish_time": parse_publish_time(post.get("takenAt") or post.get("takenAtDate")),
        "author": full_name[:255] or None, "author_id": username[:255] or None,
        "image_urls": json.dumps([cover], ensure_ascii=False) if cover else "[]",
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": as_int(post.get("likeCount")),
        "comments_count": as_int(post.get("commentCount")),
        "collected_count": 0,
        "read_count": as_int(post.get("playCount")),
        "share_count": as_int(post.get("shareCount")),
    }


def _fetch_posts(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    for raw in iter_search_posts(target, max_pages=max_pages):
        item = _normalize_post(raw)
        if not item:
            continue
        publish_time = item.get("publish_time") or 0
        if last_publish_time and publish_time and publish_time <= last_publish_time:
            continue
        results.append(item)
        if len(results) >= max_count:
            break
    return results


def do_job_instagram(feed: Feed, is_test: bool = False) -> List[Dict[str, Any]]:
    return run_keyword_job(feed, is_test, INSTAGRAM_KW_PREFIX, "instagram", _fetch_posts)
