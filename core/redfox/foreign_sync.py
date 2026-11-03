"""海外平台关键词订阅共享的入库与错误处理。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, Dict, List

from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.print import print_info, print_warning

AUTO_DISABLE_ERROR_THRESHOLD = 5


def as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def upsert_articles(session, feed_id: str, items: List[Dict[str, Any]]) -> int:
    if not items:
        return 0
    ids = [item["id"] for item in items]
    existing = {a.id: a for a in session.query(Article).filter(Article.id.in_(ids)).all()}
    now_ms = int(time.time() * 1000)
    now_dt = datetime.utcfromtimestamp(now_ms / 1000)
    inserted = 0
    for item in items:
        article = existing.get(item["id"])
        if article is None:
            session.add(Article(
                id=item["id"], feed_id=feed_id, title=item["title"],
                content=item["content"], description=item["description"],
                pic_url=item["pic_url"], url=item["url"],
                publish_time=item["publish_time"], author=item["author"],
                author_id=item["author_id"], image_urls=item["image_urls"],
                extinfo=item["extinfo"], liked_count=item["liked_count"],
                comments_count=item["comments_count"], collected_count=item["collected_count"],
                read_count=item["read_count"], share_count=item["share_count"],
                status=1, has_content=1 if item["content"] else 0, show_type=5,
                created_at=now_dt, updated_at=now_ms, updated_at_millis=now_ms,
            ))
            inserted += 1
            continue
        for field in (
            "title", "content", "description", "pic_url", "url", "author", "author_id",
            "image_urls", "extinfo", "publish_time", "liked_count", "comments_count",
            "collected_count", "read_count", "share_count",
        ):
            value = item.get(field)
            if value not in (None, "", "[]"):
                setattr(article, field, value)
        article.has_content = 1 if (article.content or "").strip() else 0
        article.updated_at = now_ms
        article.updated_at_millis = now_ms
    session.flush()
    return inserted


def run_keyword_job(
    feed: Feed,
    is_test: bool,
    prefix: str,
    tag: str,
    fetcher: Callable[[str, int, int], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    session = DB.get_session()
    try:
        if not is_test and getattr(feed, "status", 1) != 1:
            return []
        if not feed.id.startswith(prefix):
            raise ValueError(f"无法识别的 {tag} feed.id: {feed.id!r}")
        target = (getattr(feed, "target", None) or "").strip()
        if not target:
            raise ValueError(f"feed {feed.id} target 为空")
        last_publish_time = int(getattr(feed, "last_publish_time", 0) or 0)
        max_count = int(getattr(feed, "max_fetch_count", 20) or 20)
        items = fetcher(target, last_publish_time, max_count)
        inserted = upsert_articles(session, feed.id, items)
        db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
        if db_feed is None:
            session.rollback()
            return []
        if items:
            db_feed.last_publish_time = max(last_publish_time, max((item.get("publish_time") or 0) for item in items))
            db_feed.last_cursor = items[0]["id"]
        db_feed.sync_time = int(time.time())
        db_feed.error_count = 0
        db_feed.last_error = None
        db_feed.last_error_at = None
        session.commit()
        print_info(f"[{tag}] ok feed={feed.id} inserted={inserted}")
        return items
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
            print_warning(f"[{tag}] test mode 忽略失败记录: {exc}")
        raise
    finally:
        session.close()
