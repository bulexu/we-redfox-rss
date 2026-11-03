"""哔哩哔哩关键词订阅同步。"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.print import print_info, print_warning

from .client import PAGE_SIZE, iter_search_works, parse_publish_time

AUTO_DISABLE_ERROR_THRESHOLD = 5
BILI_KW_PREFIX = "BILI_KW_"


def build_feed_id(kind: str, target: str) -> str:
    if kind != "keyword":
        raise ValueError(f"未知 kind: {kind!r}")
    return f"{BILI_KW_PREFIX}{uuid.uuid4().hex[:16]}"


def _as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _normalize_work(work: Dict[str, Any]) -> Dict[str, Any]:
    bvid = str(work.get("bvId") or work.get("bvid") or work.get("id") or "").strip()
    if not bvid:
        return {}
    title = str(work.get("title") or "").strip()
    description = str(work.get("description") or "").strip()
    pic_url = str(work.get("picUrl") or work.get("coverUrl") or "").strip()
    if pic_url.startswith("http://"):
        pic_url = "https://" + pic_url[len("http://"):]
    tags = work.get("tagNames") if isinstance(work.get("tagNames"), list) else []
    url = str(work.get("workUrl") or f"https://www.bilibili.com/video/{bvid}")
    extinfo = {
        "platform": "bili", "bvid": bvid,
        "duration": _as_int(work.get("duration")),
        "coin_count": _as_int(work.get("coinCount")),
        "interaction_quantity": _as_int(work.get("interactionQuantity")),
        "first_type": work.get("firstType") or "",
        "second_type": work.get("secondType") or "",
        "tags": tags,
        "video_review": _as_int(work.get("videoReview")),
    }
    return {
        "id": bvid, "title": title[:1000], "content": description,
        "description": description, "pic_url": pic_url[:500] or None,
        "url": url[:500],
        "publish_time": parse_publish_time(work.get("created") or work.get("publishTime")),
        "author": str(work.get("author") or "")[:255] or None,
        "author_id": str(work.get("authorId") or "")[:255] or None,
        "image_urls": json.dumps([pic_url], ensure_ascii=False) if pic_url else "[]",
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": _as_int(work.get("likeCount")),
        "comments_count": _as_int(work.get("commentCount")),
        "collected_count": _as_int(work.get("favoriteCount")),
        "read_count": _as_int(work.get("playCount")),
        "share_count": _as_int(work.get("shareCount")),
    }


def _fetch_works(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    for raw in iter_search_works(target, max_pages=max_pages, page_size=PAGE_SIZE, order="time"):
        work = _normalize_work(raw)
        if not work:
            continue
        publish_time = work.get("publish_time") or 0
        if last_publish_time and publish_time and publish_time <= last_publish_time:
            continue
        results.append(work)
        if len(results) >= max_count:
            break
    return results


def _upsert_articles(session, feed_id: str, works: List[Dict[str, Any]]) -> int:
    if not works:
        return 0
    ids = [work["id"] for work in works]
    existing = {a.id: a for a in session.query(Article).filter(Article.id.in_(ids)).all()}
    now_ms = int(time.time() * 1000)
    now_dt = datetime.utcfromtimestamp(now_ms / 1000)
    inserted = 0
    for work in works:
        article = existing.get(work["id"])
        if article is None:
            session.add(Article(
                id=work["id"], feed_id=feed_id, title=work["title"],
                content=work["content"], description=work["description"],
                pic_url=work["pic_url"], url=work["url"],
                publish_time=work["publish_time"], author=work["author"],
                author_id=work["author_id"], image_urls=work["image_urls"],
                extinfo=work["extinfo"], liked_count=work["liked_count"],
                comments_count=work["comments_count"], collected_count=work["collected_count"],
                read_count=work["read_count"], share_count=work["share_count"],
                status=1, has_content=1 if work["content"] else 0, show_type=5,
                created_at=now_dt, updated_at=now_ms, updated_at_millis=now_ms,
            ))
            inserted += 1
            continue
        for field in (
            "title", "content", "description", "pic_url", "url", "author", "author_id",
            "image_urls", "extinfo", "publish_time", "liked_count", "comments_count",
            "collected_count", "read_count", "share_count",
        ):
            value = work.get(field)
            if value not in (None, "", "[]"):
                setattr(article, field, value)
        article.has_content = 1 if (article.content or "").strip() else 0
        article.updated_at = now_ms
        article.updated_at_millis = now_ms
    session.flush()
    return inserted


def do_job_bilibili(feed: Feed, is_test: bool = False) -> List[Dict[str, Any]]:
    session = DB.get_session()
    try:
        if not is_test and getattr(feed, "status", 1) != 1:
            return []
        if not feed.id.startswith(BILI_KW_PREFIX):
            raise ValueError(f"无法识别的 B 站 feed.id: {feed.id!r}")
        target = (getattr(feed, "target", None) or "").strip()
        if not target:
            raise ValueError(f"feed {feed.id} target 为空")
        last_publish_time = int(getattr(feed, "last_publish_time", 0) or 0)
        max_count = int(getattr(feed, "max_fetch_count", 20) or 20)
        works = _fetch_works(target, last_publish_time, max_count)
        inserted = _upsert_articles(session, feed.id, works)
        db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
        if db_feed is None:
            session.rollback()
            return []
        if works:
            db_feed.last_publish_time = max(last_publish_time, max((w.get("publish_time") or 0) for w in works))
            db_feed.last_cursor = works[0]["id"]
        db_feed.sync_time = int(time.time())
        db_feed.error_count = 0
        db_feed.last_error = None
        db_feed.last_error_at = None
        session.commit()
        print_info(f"[bili] ok feed={feed.id} inserted={inserted}")
        return works
    except Exception as exc:
        session.rollback()
        if not is_test:
            db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
            if db_feed is not None:
                db_feed.error_count = int(db_feed.error_count or 0) + 1
                db_feed.last_error = str(exc)[:1000]
                db_feed.last_error_at = int(time.time())
                if db_feed.error_count >= AUTO_DISABLE_ERROR_THRESHOLD:
                    db_feed.status = 0
                try:
                    session.commit()
                except Exception:
                    session.rollback()
        else:
            print_warning(f"[bili] test mode 忽略失败记录: {exc}")
        raise
    finally:
        session.close()

