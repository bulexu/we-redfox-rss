"""小红书同步 worker。

``do_job_xhs(feed)`` 是单个 feed 的增量同步入口,  与 ``jobs.mps`` 派发的
``do_job`` (公众号) 对称。  流程:

  1. 根据 ``feed.id`` 前缀识别 kind:
     * ``XHS_KW_<keyword>``  → 走 ``iter_search_articles(keyword, sort_type='2')``
     * ``XHS_U_<userId>``    → 走 ``iter_user_works(user_id, sort_type='2')``
  2. 翻页直到 (a) ``publish_time <= feed.last_publish_time`` 早停,
     (b) 已抓 ``feed.max_fetch_count`` 条,  (c) ``hasMore=false``。
  3. 对每条 note 做 Q7 metrics_only UPSERT:
     * 新 note:  INSERT 全字段
     * 已有 note:  只 UPDATE 5 个 metrics 列 + ``updated_at`` + ``updated_at_millis``
     保留 title/content/pic_url/author 等不动 (XHS 笔记发布后不改)。
  4. 更新 ``feed.last_publish_time`` / ``feed.last_cursor`` / ``feed.sync_time``;
     成功一次清零 ``feed.error_count``,  失败一次 +1 并写 ``last_error``。
  5. 连续失败 ``5 次`` → ``feed.status=0`` 暂停同步。

异常处理:
  * 单页网络/5xx 错误:  整页跳过,  已抓的页保留 (调用方再触发即可续传)
  * 整次失败:  异常向上抛,  走 ``jobs.mps._run_batch`` 的 TaskQueue
    自带 retry (指数退避 1m/5m/30m/1h/6h)
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.config import cfg
from core.db import DB
from core.models.article import Article
from core.models.feed import Feed
from core.print import print_error, print_info, print_warning

from .client import (
    PAGE_SIZE,
    RedfoxError,
    iter_search_articles,
    iter_user_works,
    parse_work_publish_time,
)


# 连续失败次数阈值,  触发自动暂停同步
AUTO_DISABLE_ERROR_THRESHOLD = 5

# XHS feed id 前缀 (与 ``core/models/feed.py`` 注释保持一致)
XHS_KW_PREFIX = "XHS_KW_"
XHS_U_PREFIX = "XHS_U_"

# 关键词/账号订阅默认 sortType ("2" = 最新,  适合时间增量)
DEFAULT_SORT_TYPE = "2"


# ---------- feed id 解析 ----------

def _split_feed_id(feed_id: str) -> tuple[str, str]:
    """从 ``XHS_KW_<uuid-or-keyword>`` / ``XHS_U_<user_id>`` 拆出 (kind, target_id_suffix)。

    仅按 prefix 拆分,  不再用 suffix 作为检索值:  新数据 suffix 是 uuid,
    真正的检索值 (keyword / userId) 存在 ``feed.target`` 里。

    老数据 (suffix 是中文 keyword 或纯数字 userId) 仍能拆出 suffix 作为 fallback。
    """
    if not feed_id:
        raise ValueError("feed.id 为空")
    if feed_id.startswith(XHS_KW_PREFIX):
        return "keyword", feed_id[len(XHS_KW_PREFIX):]
    if feed_id.startswith(XHS_U_PREFIX):
        return "account", feed_id[len(XHS_U_PREFIX):]
    raise ValueError(f"无法识别的 XHS feed.id: {feed_id!r}")


def build_feed_id(kind: str, target: str) -> str:
    """构造 XHS feed.id。

    * ``kind="keyword"`` → ``XHS_KW_<uuid>`` (避免中文/特殊字符进主键, 也方便 URL 编码)。
      原始 keyword 字符串由调用方写入 ``feed.target``。
    * ``kind="account"`` → ``XHS_U_<userId>`` (userId 本身就是平台唯一键, 直接拼接 OK)。
      ``feed.target`` 也存一份 userId 便于统一读取。
    """
    if kind == "keyword":
        return f"{XHS_KW_PREFIX}{uuid.uuid4().hex[:16]}"
    if kind == "account":
        return f"{XHS_U_PREFIX}{target}"
    raise ValueError(f"未知 kind: {kind!r}")


# ---------- redfox note → Article 字段映射 ----------

def _normalize_note(note: Dict[str, Any]) -> Dict[str, Any]:
    """把 redfox note dict 拆成 ``Article.__init__`` 可吃的 kwargs。

    只做字段映射 + 类型规范化,  不入库。  字段语义详见 ``do_job_xhs`` 顶部。
    """
    work_id = (note.get("workId") or "").strip()
    if not work_id:
        return {}

    cover_url = note.get("coverUrl") or ""
    image_urls_json = json.dumps([cover_url], ensure_ascii=False) if cover_url else "[]"

    return {
        "id": work_id,
        "title": (note.get("workTitle") or "")[:1000],
        "content": note.get("workDesc") or "",
        "pic_url": cover_url[:500] if cover_url else None,
        "url": note.get("workUrl") or "",
        "publish_time": parse_work_publish_time(note.get("workPublishTime") or ""),
        "author": (note.get("accountNickname") or "")[:255] or None,
        "author_id": (note.get("accountUserid") or "")[:255] or None,
        "image_urls": image_urls_json,
        "liked_count": int(note.get("workLikedCount") or 0),
        "comments_count": int(note.get("workCommentsCount") or 0),
        "collected_count": int(note.get("workCollectedCount") or 0),
        "read_count": int(note.get("workReadedCount") or 0),
        "share_count": int(note.get("workSharedCount") or 0),
    }


# ---------- 增量抓取主循环 ----------

def _fetch_notes(
    feed: Feed,
    kind: str,
    target: str,
    last_publish_time: int,
    max_count: int,
) -> List[Dict[str, Any]]:
    """按 feed 类型拉 notes,  按 ``publish_time`` 增量早停,  最多 ``max_count`` 条。

    返回的是 ``_normalize_note`` 之后的字段 dict 列表 (已经筛过增量边界)。
    """
    results: List[Dict[str, Any]] = []

    # 每页 20 条,  max_count=20 时 1 页;  50 时 3 页;  100 时 5 页。
    # 给点 buffer:  max_count 不超过上限时按 (max_count+PAGE_SIZE-1)//PAGE_SIZE
    # 计算最大页数,  避免刚抓到 N 条但下一页还有更早的就被截断。
    max_pages = max(1, (max_count + PAGE_SIZE - 1) // PAGE_SIZE)

    if kind == "keyword":
        raw_iter = iter_search_articles(
            keyword=target,
            max_pages=max_pages,
            sort_type=DEFAULT_SORT_TYPE,
            page_size=PAGE_SIZE,
        )
    elif kind == "account":
        raw_iter = iter_user_works(
            user_id=target,
            max_pages=max_pages,
            sort_type=DEFAULT_SORT_TYPE,
            page_size=PAGE_SIZE,
        )
    else:
        raise ValueError(f"未知 kind: {kind!r}")

    for note in raw_iter:
        normalized = _normalize_note(note)
        if not normalized:
            continue
        pt = normalized.get("publish_time") or 0
        # 增量早停:  本次抓到的笔记 publish_time <= last_publish_time
        # 表示已经走到上次同步的位置,  后面的(更早的)不必再处理
        # (XHS sort_type='2' 按时间倒序,  遇到比水印早就 break)
        if last_publish_time and pt and pt <= last_publish_time:
            break
        results.append(normalized)
        if len(results) >= max_count:
            break

    return results


# ---------- UPSERT ----------

def _upsert_articles(session, feed_id: str, normalized_notes: List[Dict[str, Any]]) -> int:
    """批量 UPSERT notes 到 articles 表,  返回实际写入/更新条数。

    策略 (Q7 metrics_only 部分 UPSERT):
      * 新 workId  → INSERT 全字段
      * 已有 workId → 只 UPDATE 5 个 metrics 列 + updated_at + updated_at_millis,
                       保留 title/content/pic_url/author/... 原值不动。
    """
    if not normalized_notes:
        return 0

    work_ids = [n["id"] for n in normalized_notes]
    existing = {
        a.id: a
        for a in session.query(Article).filter(Article.id.in_(work_ids)).all()
    }

    now_ms = int(time.time() * 1000)
    now_dt = datetime.utcfromtimestamp(now_ms / 1000)
    written = 0
    for n in normalized_notes:
        work_id = n["id"]
        art = existing.get(work_id)
        if art is None:
            # 新增
            art = Article(
                id=work_id,
                feed_id=feed_id,
                title=n.get("title"),
                content=n.get("content"),
                pic_url=n.get("pic_url"),
                url=n.get("url"),
                publish_time=n.get("publish_time"),
                author=n.get("author"),
                author_id=n.get("author_id"),
                image_urls=n.get("image_urls"),
                liked_count=n.get("liked_count") or 0,
                comments_count=n.get("comments_count") or 0,
                collected_count=n.get("collected_count") or 0,
                read_count=n.get("read_count") or 0,
                share_count=n.get("share_count") or 0,
                status=1,
                has_content=1,  # XHS 一次抓回 workDesc 全文,  标记为有正文
                created_at=now_dt,
                updated_at=now_ms,
                updated_at_millis=now_ms,
            )
            session.add(art)
            written += 1
        else:
            # Q7 metrics_only 部分 UPSERT:  只更新 5 个 metrics + 时间戳
            art.liked_count = n.get("liked_count") or 0
            art.comments_count = n.get("comments_count") or 0
            art.collected_count = n.get("collected_count") or 0
            art.read_count = n.get("read_count") or 0
            art.share_count = n.get("share_count") or 0
            art.updated_at = now_ms
            art.updated_at_millis = now_ms
            written += 1

    session.flush()
    return written


# ---------- 主入口 ----------

def do_job_xhs(feed: Feed, is_test: bool = False) -> List[Dict[str, Any]]:
    """单个 XHS feed 的增量同步入口。

    Args:
        feed:  XHS_KW_* 或 XHS_U_* 前缀的 Feed 对象 (数据库已有记录)
        is_test:  测试模式,  跳过 error_count / status 自动暂停逻辑

    Returns:
        本次新写入/更新的笔记 (normalize 后的 dict 列表)。
        返回空列表表示 skip (status=0) 或已同步到水印。
        异常路径 raise, 由调用方 (TaskQueue) 重试。
    """
    session = DB.get_session()
    try:
        # 检查 enabled (status=1) — 连续失败 5 次会自动置 0
        if not is_test and getattr(feed, "status", 1) != 1:
            print_info(
                f"[xhs] skip: feed {feed.id} status={feed.status} (已暂停)"
            )
            return []

        kind, _id_suffix = _split_feed_id(feed.id)
        # 优先用 feed.target (新数据); 老数据没填 target 时 fallback 到 id suffix (向后兼容)。
        target = (getattr(feed, "target", None) or _id_suffix).strip()
        if not target:
            raise ValueError(f"feed {feed.id} target 为空, 无法同步")
        last_publish_time = int(getattr(feed, "last_publish_time", 0) or 0)
        last_cursor = getattr(feed, "last_cursor", None)
        max_count = int(getattr(feed, "max_fetch_count", 20) or 20)

        print_info(
            f"[xhs] start feed={feed.id} kind={kind} target={target!r} "
            f"last_pt={last_publish_time} max_count={max_count}"
        )

        notes = _fetch_notes(feed, kind, target, last_publish_time, max_count)
        written = _upsert_articles(session, feed.id, notes)

        # 更新 feed 水位线 / 错误计数
        if notes:
            new_last_pt = max(
                last_publish_time,
                max((n.get("publish_time") or 0) for n in notes),
            )
            new_last_cursor = notes[0].get("id")  # 最新一条的 workId
        else:
            new_last_pt = last_publish_time
            new_last_cursor = last_cursor

        # 同一 session 内 feed 对象可能 stale,  显式 refresh
        db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
        if db_feed is None:
            print_warning(f"[xhs] feed {feed.id} 不存在, 跳过")
            session.rollback()
            return []
        db_feed.last_publish_time = new_last_pt
        db_feed.last_cursor = new_last_cursor
        db_feed.sync_time = int(time.time())
        db_feed.error_count = 0  # 成功清零
        db_feed.last_error = None
        db_feed.last_error_at = None

        session.commit()

        print_info(
            f"[xhs] ok feed={feed.id} written={written} "
            f"new_last_pt={new_last_pt} cursor={new_last_cursor}"
        )

        return notes

    except RedfoxError as exc:
        # 整次失败:  不 commit,  异常向上抛,  走 TaskQueue retry。
        session.rollback()
        _record_failure(session, feed, exc, is_test=is_test)
        raise
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _record_failure(session, feed, exc, is_test=is_test)
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass


def _record_failure(
    session,
    feed: Feed,
    exc: Exception,
    is_test: bool = False,
) -> None:
    """失败处理:  +1 error_count,  写 last_error,  达到阈值则 status=0。

    用 ``session.begin()`` 单独起事务,  与 ``do_job_xhs`` 主流程的
    rollback 互不干扰。  ``is_test=True`` 时跳过状态变更。
    """
    if is_test:
        print_warning(f"[xhs] test mode 忽略失败记录: feed={feed.id} exc={exc}")
        return

    db_feed = session.query(Feed).filter(Feed.id == feed.id).first()
    if db_feed is None:
        return
    db_feed.error_count = int(db_feed.error_count or 0) + 1
    db_feed.last_error = (str(exc) or "")[:1000]
    db_feed.last_error_at = int(time.time())
    if db_feed.error_count >= AUTO_DISABLE_ERROR_THRESHOLD:
        if db_feed.status != 0:
            print_warning(
                f"[xhs] feed {feed.id} 连续失败 {db_feed.error_count} 次, "
                f"自动暂停 (status=0)"
            )
        db_feed.status = 0
    try:
        session.commit()
    except Exception as commit_exc:  # noqa: BLE001
        session.rollback()
        print_warning(f"[xhs] 写失败状态失败 feed={feed.id}: {commit_exc}")