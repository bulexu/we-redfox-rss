"""TikTok 关键词订阅同步。"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from core.models.feed import Feed
from core.redfox.foreign_sync import AUTO_DISABLE_ERROR_THRESHOLD, run_keyword_job

from .client import normalize_item
from .client import PAGE_SIZE, iter_search_videos

TIKTOK_KW_PREFIX = "TIKTOK_KW_"


def build_feed_id(kind: str, target: str) -> str:
    if kind != "keyword":
        raise ValueError(f"未知 kind: {kind!r}")
    return f"{TIKTOK_KW_PREFIX}{uuid.uuid4().hex[:16]}"


def _fetch_videos(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    for article in iter_search_videos(target, max_pages=max_pages, region="US"):
        item = article.to_record()
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


def _normalize_video(raw: Dict[str, Any]) -> Dict[str, Any]:
    """兼容旧调用；同步主流程直接消费客户端 ArticleSchema。"""
    article = normalize_item(raw)
    return article.to_record() if article is not None else {}
