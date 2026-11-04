"""抖音订阅增量同步 worker。"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import or_

from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.print import print_info, print_warning

from .client import normalize_item
from .client import PAGE_SIZE, iter_search_articles, parse_work_publish_time


AUTO_DISABLE_ERROR_THRESHOLD = 5
DY_KW_PREFIX = "DY_KW_"


def _split_feed_id(feed_id: str) -> tuple[str, str]:
    if feed_id.startswith(DY_KW_PREFIX):
        return "keyword", feed_id[len(DY_KW_PREFIX):]
    raise ValueError(f"无法识别的抖音 feed.id: {feed_id!r}")


def build_feed_id(kind: str, target: str) -> str:
    if kind == "keyword":
        return f"{DY_KW_PREFIX}{uuid.uuid4().hex[:16]}"
    raise ValueError(f"未知 kind: {kind!r}")


def _fetch_works(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    start_date = (
        datetime.fromtimestamp(last_publish_time).strftime("%Y-%m-%d")
        if last_publish_time else None
    )
    articles = iter_search_articles(
        target,
        max_pages=max_pages,
        page_size=PAGE_SIZE,
        start_date=start_date,
    )

    results: List[Dict[str, Any]] = []
    for article in articles:
        normalized = article.to_record()
        if not normalized:
            continue
        publish_time = normalized.get("publish_time") or 0
        # 广域库不承诺严格按时间倒序，因此不能遇到旧作品就 break。
        if last_publish_time and publish_time and publish_time <= last_publish_time:
            continue
        results.append(normalized)
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
    for work in works:
        article = existing.get(work["id"])
        if article is None:
            session.add(
                Article(
                    id=work["id"],
                    feed_id=feed_id,
                    title=work.get("title"),
                    content=work.get("content"),
                    description=work.get("description"),
                    pic_url=work.get("pic_url"),
                    url=work.get("url"),
                    publish_time=work.get("publish_time"),
                    author=work.get("author"),
                    author_id=work.get("author_id"),
                    image_urls=work.get("image_urls"),
                    extinfo=work.get("extinfo"),
                    liked_count=work.get("liked_count", 0),
                    comments_count=work.get("comments_count", 0),
                    collected_count=work.get("collected_count", 0),
                    read_count=work.get("read_count", 0),
                    share_count=work.get("share_count", 0),
                    status=1,
                    has_content=1,
                    show_type=work.get("show_type", 5),
                    created_at=now_dt,
                    updated_at=now_ms,
                    updated_at_millis=now_ms,
                )
            )
            continue
        # 已有作品只刷新互动指标，保留原始文案和链接。
        article.liked_count = work.get("liked_count", 0)
        article.comments_count = work.get("comments_count", 0)
        article.collected_count = work.get("collected_count", 0)
        article.read_count = work.get("read_count", 0)
        article.share_count = work.get("share_count", 0)
        # 老版本没有适配广域库的 content / opusUrl 字段，已经入库的作品
        # 会出现标题、正文和链接为空。同步再次拿到作品时仅补齐空字段，
        # 避免覆盖用户或其它任务已经修正过的内容。
        for field in (
            "title",
            "content",
            "description",
            "pic_url",
            "url",
            "author",
            "author_id",
            "image_urls",
            "extinfo",
        ):
            incoming = work.get(field)
            if incoming not in (None, "", "[]") and getattr(article, field, None) in (None, "", "[]"):
                setattr(article, field, incoming)
        if not article.publish_time and work.get("publish_time"):
            article.publish_time = work["publish_time"]
        article.has_content = 1 if (article.content or "").strip() else 0
        article.updated_at = now_ms
        article.updated_at_millis = now_ms
    session.flush()
    return len(works)


def do_job_douyin(feed: Feed, is_test: bool = False) -> List[Dict[str, Any]]:
    session = DB.get_session()
    try:
        if not is_test and getattr(feed, "status", 1) != 1:
            print_info(f"[dy] skip: feed {feed.id} status={feed.status}")
            return []
        _kind, suffix = _split_feed_id(feed.id)
        target = (getattr(feed, "target", None) or suffix).strip()
        if not target:
            raise ValueError(f"feed {feed.id} target 为空, 无法同步")
        last_publish_time = int(getattr(feed, "last_publish_time", 0) or 0)
        max_count = int(getattr(feed, "max_fetch_count", 20) or 20)
        # 字段映射修复前写入的数据缺少标题/正文。发现这种记录时从第一页
        # 回查一次，确保用户点击“立即同步”即可补齐，无需删除并重建订阅。
        needs_content_backfill = session.query(Article.id).filter(
            Article.feed_id == feed.id,
            or_(
                Article.title.is_(None),
                Article.title == "",
                Article.content.is_(None),
                Article.content == "",
                Article.url.is_(None),
                Article.url == "",
            ),
        ).first() is not None
        fetch_after = 0 if needs_content_backfill else last_publish_time
        works = _fetch_works(target, fetch_after, max_count)
        written = _upsert_articles(session, feed.id, works)

        db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
        if db_feed is None:
            session.rollback()
            return []
        if works:
            db_feed.last_publish_time = max(
                last_publish_time, max((w.get("publish_time") or 0) for w in works)
            )
            db_feed.last_cursor = works[0]["id"]
        db_feed.sync_time = int(time.time())
        db_feed.error_count = 0
        db_feed.last_error = None
        db_feed.last_error_at = None
        session.commit()
        from core.redfox.transcript import enqueue_transcripts
        enqueue_transcripts(works)
        print_info(f"[dy] ok feed={feed.id} written={written}")
        return works
    except Exception as exc:  # RedfoxError 也统一走失败记录
        session.rollback()
        _record_failure(session, feed, exc, is_test)
        raise
    finally:
        session.close()


def _record_failure(session, feed: Feed, exc: Exception, is_test: bool = False):
    if is_test:
        print_warning(f"[dy] test mode 忽略失败记录: {exc}")
        return
    db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
    if db_feed is None:
        return
    db_feed.error_count = int(db_feed.error_count or 0) + 1
    db_feed.last_error = str(exc)[:1000]
    db_feed.last_error_at = int(time.time())
    if db_feed.error_count >= AUTO_DISABLE_ERROR_THRESHOLD:
        db_feed.status = 0
    try:
        session.commit()
    except Exception:
        session.rollback()


def _normalize_work(raw: Dict[str, Any]) -> Dict[str, Any]:
    """兼容旧调用；同步主流程直接消费客户端 ArticleSchema。"""
    article = normalize_item(raw)
    return article.to_record() if article is not None else {}
