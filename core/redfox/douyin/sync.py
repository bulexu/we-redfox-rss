"""抖音订阅增量同步 worker。"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import or_

from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.print import print_info, print_warning

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


def _pick(data: Any, *paths: str, default=None):
    """从 Redfox 新旧两种字段风格中取第一个非空值。"""
    for path in paths:
        current = data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(current, list):
            current = current[0] if current else None
        if current not in (None, ""):
            return current
    return default


def _as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _normalize_work(work: Dict[str, Any]) -> Dict[str, Any]:
    """把抖音作品转换成共用 Article 字段。"""
    raw_work_id = str(
        _pick(work, "workId", "awemeId", "aweme_id", "videoId", "id", default="")
    ).strip()
    if not raw_work_id:
        return {}

    description = str(
        _pick(
            work, "content", "workDesc", "videoDesc", "desc", "description",
            "workTitle", "videoTitle", "title", default="",
        )
    )
    title = str(
        _pick(
            work, "workTitle", "videoTitle", "title", "content", "desc", "videoDesc",
            "workDesc", default="",
        )
    )
    cover_url = str(
        _pick(
            work,
            "coverUrl",
            "videoCover",
            "workCover",
            "cover",
            "video.cover.url_list",
            "video.dynamic_cover.url_list",
            default="",
        )
    )
    work_url = str(
        _pick(
            work, "opusUrl", "workUrl", "videoShareUrl", "shareUrl", "share_url",
            "videoUrl", "url", default="",
        )
    )
    video_url = str(
        _pick(
            work,
            "videoUrl",
            "playUrl",
            "video.play_addr.url_list",
            "video.download_addr.url_list",
            default="",
        )
    )
    publish_value = _pick(
        work, "workPublishTime", "videoCreateTime", "publishTime", "createTime",
        "create_time", default=0,
    )
    author = str(
        _pick(
            work, "authorName", "accountNickname", "accountName", "userNickname",
            "author.nickname", "nickname", default="",
        )
    )
    author_id = str(
        _pick(
            work,
            "accountUserid",
            "authorUid",
            "authorSecUid",
            "accountId",
            "authorId",
            "userId",
            "secUserId",
            "sec_uid",
            "author.sec_uid",
            "author.uid",
            "uid",
            default="",
        )
    )
    extinfo = {
        "platform": "dy",
        "work_id": raw_work_id,
        "video_url": video_url,
        "duration": _as_int(_pick(work, "duration", "video.duration", default=0)),
    }

    return {
        "id": raw_work_id,
        "title": title[:1000],
        "content": description,
        "description": description,
        "pic_url": cover_url[:500] if cover_url else None,
        "url": work_url[:500],
        "publish_time": parse_work_publish_time(publish_value),
        "author": author[:255] or None,
        "author_id": author_id[:255] or None,
        "image_urls": json.dumps([cover_url], ensure_ascii=False) if cover_url else "[]",
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": _as_int(_pick(work, "workLikedCount", "likedCount", "likeCount", "diggCount", "statistics.digg_count")),
        "comments_count": _as_int(_pick(work, "workCommentsCount", "commentsCount", "commentCount", "statistics.comment_count")),
        "collected_count": _as_int(_pick(work, "workCollectedCount", "collectedCount", "collectCount", "statistics.collect_count")),
        "read_count": _as_int(_pick(work, "workReadedCount", "viewCount", "playCount", "statistics.play_count")),
        "share_count": _as_int(_pick(work, "workSharedCount", "sharedCount", "shareCount", "statistics.share_count")),
    }


def _fetch_works(target: str, last_publish_time: int, max_count: int) -> List[Dict[str, Any]]:
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)
    start_date = (
        datetime.fromtimestamp(last_publish_time).strftime("%Y-%m-%d")
        if last_publish_time else None
    )
    raw_iter = iter_search_articles(
        target,
        max_pages=max_pages,
        page_size=PAGE_SIZE,
        start_date=start_date,
    )

    results: List[Dict[str, Any]] = []
    for work in raw_iter:
        normalized = _normalize_work(work)
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
                    show_type=5,
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
