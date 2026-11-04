"""X (Twitter) 关键词订阅同步。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from core.db import DB
from core.models.article import Article
from core.redfox.transcript import preserve_transcript
from core.models.feed import Feed
from core.print import print_info, print_warning

from .client import normalize_item
from .client import PAGE_SIZE, iter_search_tweets, parse_publish_time

AUTO_DISABLE_ERROR_THRESHOLD = 5
X_KW_PREFIX = "X_KW_"


def build_feed_id(kind: str, target: str) -> str:
    if kind != "keyword":
        raise ValueError(f"未知 kind: {kind!r}")
    return f"{X_KW_PREFIX}{uuid.uuid4().hex[:16]}"


def _fetch_tweets(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    for article in iter_search_tweets(target, max_pages=max_pages, search_type="Latest"):
        tweet = article.to_record()
        if not tweet:
            continue
        publish_time = tweet.get("publish_time") or 0
        if last_publish_time and publish_time and publish_time <= last_publish_time:
            continue
        results.append(tweet)
        if len(results) >= max_count:
            break
    return results


def _upsert_articles(session, feed_id: str, tweets: List[Dict[str, Any]]) -> int:
    if not tweets:
        return 0
    ids = [tweet["id"] for tweet in tweets]
    existing = {a.id: a for a in session.query(Article).filter(Article.id.in_(ids)).all()}
    now_ms = int(time.time() * 1000)
    now_dt = datetime.utcfromtimestamp(now_ms / 1000)
    inserted = 0
    for tweet in tweets:
        article = existing.get(tweet["id"])
        if article is None:
            session.add(Article(
                id=tweet["id"], feed_id=feed_id, title=tweet["title"],
                content=tweet["content"], description=tweet["description"],
                pic_url=tweet["pic_url"], url=tweet["url"],
                publish_time=tweet["publish_time"], author=tweet["author"],
                author_id=tweet["author_id"], image_urls=tweet["image_urls"],
                extinfo=tweet["extinfo"], liked_count=tweet["liked_count"],
                comments_count=tweet["comments_count"], collected_count=tweet["collected_count"],
                read_count=tweet["read_count"], share_count=tweet["share_count"],
                status=1, has_content=1 if tweet["content"] else 0, show_type=5,
                created_at=now_dt, updated_at=now_ms, updated_at_millis=now_ms,
            ))
            inserted += 1
            continue
        for field in (
            "title", "content", "description", "pic_url", "url", "author", "author_id",
            "image_urls", "extinfo", "publish_time", "liked_count", "comments_count",
            "collected_count", "read_count", "share_count",
        ):
            value = tweet.get(field)
            if value not in (None, "", "[]"):
                setattr(article, field, preserve_transcript(article, field, value))
        article.has_content = 1 if (article.content or "").strip() else 0
        article.updated_at = now_ms
        article.updated_at_millis = now_ms
    session.flush()
    return inserted


def do_job_x(feed: Feed, is_test: bool = False) -> List[Dict[str, Any]]:
    session = DB.get_session()
    try:
        if not is_test and getattr(feed, "status", 1) != 1:
            return []
        if not feed.id.startswith(X_KW_PREFIX):
            raise ValueError(f"无法识别的 X feed.id: {feed.id!r}")
        target = (getattr(feed, "target", None) or "").strip()
        if not target:
            raise ValueError(f"feed {feed.id} target 为空")
        last_publish_time = int(getattr(feed, "last_publish_time", 0) or 0)
        max_count = int(getattr(feed, "max_fetch_count", 20) or 20)
        tweets = _fetch_tweets(target, last_publish_time, max_count)
        inserted = _upsert_articles(session, feed.id, tweets)
        db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
        if db_feed is None:
            session.rollback()
            return []
        if tweets:
            db_feed.last_publish_time = max(last_publish_time, max((t.get("publish_time") or 0) for t in tweets))
            db_feed.last_cursor = tweets[0]["id"]
        db_feed.sync_time = int(time.time())
        db_feed.error_count = 0
        db_feed.last_error = None
        db_feed.last_error_at = None
        session.commit()
        from core.redfox.transcript import enqueue_transcripts
        enqueue_transcripts(tweets)
        print_info(f"[x] ok feed={feed.id} inserted={inserted}")
        return tweets
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
            print_warning(f"[x] test mode 忽略失败记录: {exc}")
        raise
    finally:
        session.close()


def _normalize_tweet(raw: Dict[str, Any]) -> Dict[str, Any]:
    """兼容旧调用；同步主流程直接消费客户端 ArticleSchema。"""
    article = normalize_item(raw)
    return article.to_record() if article is not None else {}
