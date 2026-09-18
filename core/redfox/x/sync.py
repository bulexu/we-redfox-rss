"""X (Twitter) 关键词订阅同步。"""
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

from .client import PAGE_SIZE, iter_search_tweets, parse_publish_time

AUTO_DISABLE_ERROR_THRESHOLD = 5
X_KW_PREFIX = "X_KW_"


def build_feed_id(kind: str, target: str) -> str:
    if kind != "keyword":
        raise ValueError(f"未知 kind: {kind!r}")
    return f"{X_KW_PREFIX}{uuid.uuid4().hex[:16]}"


def _as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _normalize_tweet(tweet: Dict[str, Any]) -> Dict[str, Any]:
    tweet_id = str(tweet.get("tweetId") or tweet.get("id") or "").strip()
    if not tweet_id:
        return {}
    text = str(tweet.get("text") or tweet.get("fullText") or "").strip()
    user = tweet.get("user") if isinstance(tweet.get("user"), dict) else {}
    username = str(tweet.get("username") or user.get("username") or user.get("screenName") or "").lstrip("@").strip()
    display_name = str(user.get("displayName") or user.get("name") or username).strip()
    medias = tweet.get("medias") if isinstance(tweet.get("medias"), list) else []
    image_urls = [
        str(media.get("coverUrl") or media.get("url") or "").strip()
        for media in medias if isinstance(media, dict)
    ]
    image_urls = [url for url in image_urls if url]
    url = str(tweet.get("tweetUrl") or tweet.get("url") or "").strip()
    if not url and username:
        url = f"https://x.com/{username}/status/{tweet_id}"
    elif not url:
        url = f"https://x.com/i/status/{tweet_id}"
    extinfo = {
        "platform": "x", "tweet_id": tweet_id, "username": username,
        "language": tweet.get("language") or "",
        "quote_count": _as_int(tweet.get("quoteCount")),
        "followers": _as_int(user.get("followers")),
        "verified": bool(user.get("verified")),
        "location": user.get("location") or "", "avatar": user.get("avatar") or "",
        "medias": medias,
    }
    return {
        "id": f"x_{tweet_id}", "title": (text[:280] or "(无正文)"),
        "content": text, "description": text,
        "pic_url": image_urls[0][:500] if image_urls else None,
        "url": url[:500],
        "publish_time": parse_publish_time(tweet.get("createdAt") or tweet.get("created_at")),
        "author": display_name[:255] or None, "author_id": username[:255] or None,
        "image_urls": json.dumps(image_urls, ensure_ascii=False),
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": _as_int(tweet.get("likeCount")),
        "comments_count": _as_int(tweet.get("replyCount")),
        "collected_count": _as_int(tweet.get("bookmarkCount")),
        "read_count": _as_int(tweet.get("viewCount")),
        "share_count": _as_int(tweet.get("retweetCount")),
    }


def _fetch_tweets(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    for raw in iter_search_tweets(target, max_pages=max_pages, search_type="Latest"):
        tweet = _normalize_tweet(raw)
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
                setattr(article, field, value)
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
