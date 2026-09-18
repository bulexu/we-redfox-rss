"""TikTok 关键词订阅同步。"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from core.models.feed import Feed
from core.redfox.foreign_sync import AUTO_DISABLE_ERROR_THRESHOLD, as_int, run_keyword_job

from .client import PAGE_SIZE, iter_search_videos

TIKTOK_KW_PREFIX = "TIKTOK_KW_"


def build_feed_id(kind: str, target: str) -> str:
    if kind != "keyword":
        raise ValueError(f"未知 kind: {kind!r}")
    return f"{TIKTOK_KW_PREFIX}{uuid.uuid4().hex[:16]}"


def _normalize_video(work: Dict[str, Any]) -> Dict[str, Any]:
    work_id = str(work.get("workId") or work.get("awemeId") or work.get("id") or "").strip()
    if not work_id:
        return {}
    content = str(work.get("content") or work.get("description") or work.get("desc") or "").strip()
    author = work.get("authorData") if isinstance(work.get("authorData"), dict) else {}
    stats = work.get("statsData") if isinstance(work.get("statsData"), dict) else {}
    video = work.get("videoData") if isinstance(work.get("videoData"), dict) else {}
    username = str(author.get("userHandle") or author.get("uniqueId") or author.get("userId") or "").lstrip("@").strip()
    author_name = str(author.get("userName") or author.get("nickname") or username).strip()
    cover = str(video.get("coverImage") or work.get("coverUrl") or "").strip()
    url = str(work.get("shareLink") or work.get("workUrl") or "").strip()
    if not url and username:
        url = f"https://www.tiktok.com/@{username}/video/{work_id}"
    extinfo = {
        "platform": "tiktok", "work_id": work_id,
        "media_type": work.get("mediaType") or "video",
        "video_url": video.get("playAddress") or "",
        "download_url": video.get("downloadNoMarkAddress") or "",
        "duration": as_int(video.get("playDuration")),
        "followers": as_int(author.get("fansCount")),
        "avatar": author.get("avatarImage") or "",
        "repost_count": as_int(stats.get("repostTotal")),
    }
    return {
        "id": f"tiktok_{work_id}", "title": content[:280] or "(无标题)",
        "content": content, "description": content,
        "pic_url": cover[:500] or None, "url": url[:500],
        "publish_time": as_int(work.get("publishTime")),
        "author": author_name[:255] or None, "author_id": username[:255] or None,
        "image_urls": json.dumps([cover], ensure_ascii=False) if cover else "[]",
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": as_int(stats.get("likeCount")),
        "comments_count": as_int(stats.get("commentTotal")),
        "collected_count": as_int(stats.get("favoriteCount")),
        "read_count": as_int(stats.get("viewCount")),
        "share_count": as_int(stats.get("shareTotal")),
    }


def _fetch_videos(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    for raw in iter_search_videos(target, max_pages=max_pages, region="US"):
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


def do_job_tiktok(feed: Feed, is_test: bool = False) -> List[Dict[str, Any]]:
    return run_keyword_job(feed, is_test, TIKTOK_KW_PREFIX, "tiktok", _fetch_videos)
