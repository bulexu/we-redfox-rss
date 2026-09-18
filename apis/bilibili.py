"""B 站关键词订阅与作品 API（Redfox 优质库）。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_

from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.feed import Feed, PLATFORM_BILI
from core.print import print_warning
from core.redfox.bilibili import BILI_KW_PREFIX, build_feed_id, do_job_bilibili

from .base import error_response, success_response

router = APIRouter(prefix="/bilibili", tags=["B站订阅"])


class CreateBilibiliFeedRequest(BaseModel):
    kind: str = Field("keyword", pattern="^keyword$")
    target: str = Field(..., min_length=1, max_length=200)
    name: Optional[str] = Field(None, max_length=255)
    avatar: Optional[str] = Field(None, max_length=500)
    intro: Optional[str] = Field(None, max_length=255)
    max_fetch_count: int = Field(20, ge=1, le=200)
    refresh_interval_hours: int = Field(6, ge=1, le=168)


class UpdateBilibiliFeedRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    avatar: Optional[str] = Field(None, max_length=500)
    intro: Optional[str] = Field(None, max_length=255)
    max_fetch_count: Optional[int] = Field(None, ge=1, le=200)
    refresh_interval_hours: Optional[int] = Field(None, ge=1, le=168)
    status: Optional[int] = Field(None, ge=0, le=1)


def _feed_to_dict(feed: Feed) -> dict:
    return {
        "id": feed.id, "name": feed.name, "cover": feed.cover, "intro": feed.intro,
        "status": feed.status, "kind": "keyword", "target": feed.target or "",
        "max_fetch_count": feed.max_fetch_count,
        "refresh_interval_hours": feed.refresh_interval_hours,
        "last_publish_time": feed.last_publish_time, "last_cursor": feed.last_cursor,
        "sync_time": feed.sync_time, "error_count": feed.error_count,
        "last_error": feed.last_error, "last_error_at": feed.last_error_at,
        "created_at": feed.created_at.isoformat() if feed.created_at else None,
        "updated_at": feed.updated_at.isoformat() if feed.updated_at else None,
    }


@router.get("/feeds")
async def list_feeds(
    status: Optional[int] = Query(None, ge=0, le=1),
    kw: Optional[str] = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        query = session.query(Feed).filter(
            (Feed.platform == PLATFORM_BILI) | Feed.platform.is_(None)
        ).filter(Feed.id.like(f"{BILI_KW_PREFIX}%"))
        if status is not None:
            query = query.filter(Feed.status == status)
        if kw:
            pattern = f"%{kw.strip()}%"
            query = query.filter(or_(Feed.name.ilike(pattern), Feed.target.ilike(pattern)))
        total = query.count()
        rows = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        return success_response({"list": [_feed_to_dict(f) for f in rows], "total": total})
    except Exception as exc:
        return error_response(code=500, message=f"查询B站订阅失败: {exc}")
    finally:
        session.close()


@router.post("/feeds")
async def create_feed(req: CreateBilibiliFeedRequest, current_user: dict = Depends(get_current_user_or_ak)):
    session = DB.get_session()
    try:
        duplicate = session.query(Feed).filter(
            Feed.platform == PLATFORM_BILI, Feed.target == req.target,
            Feed.id.like(f"{BILI_KW_PREFIX}%"),
        ).first()
        if duplicate:
            return error_response(code=400, message=f"订阅已存在: {duplicate.name}")
        feed = Feed(
            id=build_feed_id(req.kind, req.target), name=(req.name or req.target)[:255],
            cover=(req.avatar or "")[:255] or None, intro=(req.intro or "")[:255] or None,
            status=1, max_fetch_count=req.max_fetch_count,
            refresh_interval_hours=req.refresh_interval_hours, sync_time=0,
            update_time=int(time.time()), created_at=datetime.now(), updated_at=datetime.now(),
            last_publish_time=0, last_cursor=None, error_count=0,
            target=req.target[:500], platform=PLATFORM_BILI,
        )
        session.add(feed)
        session.commit()
        session.refresh(feed)
        try:
            from jobs.mps import TaskQueue
            TaskQueue.add_task(do_job_bilibili, feed, False, task_name=f"B站首次采集:{feed.id}")
        except Exception as exc:
            print_warning(f"[bili] 提交首次采集失败: {exc}")
        return success_response(_feed_to_dict(feed), "创建成功, 首次采集已提交")
    except Exception as exc:
        session.rollback()
        return error_response(code=500, message=f"创建B站订阅失败: {exc}")
    finally:
        session.close()


@router.put("/feeds/{feed_id}")
async def update_feed(feed_id: str, req: UpdateBilibiliFeedRequest, current_user: dict = Depends(get_current_user_or_ak)):
    if not feed_id.startswith(BILI_KW_PREFIX):
        return error_response(code=400, message="非B站 feed_id")
    session = DB.get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return error_response(code=404, message="订阅不存在")
        for field in ("name", "max_fetch_count", "refresh_interval_hours", "status"):
            value = getattr(req, field)
            if value is not None:
                setattr(feed, field, value)
        if req.avatar is not None:
            feed.cover = req.avatar
        if req.intro is not None:
            feed.intro = req.intro
        if req.status == 1:
            feed.error_count = 0
        feed.updated_at = datetime.now()
        session.commit()
        session.refresh(feed)
        return success_response(_feed_to_dict(feed), "更新成功")
    except Exception as exc:
        session.rollback()
        return error_response(code=500, message=f"更新失败: {exc}")
    finally:
        session.close()


@router.delete("/feeds/{feed_id}")
async def delete_feed(feed_id: str, current_user: dict = Depends(get_current_user_or_ak)):
    if not feed_id.startswith(BILI_KW_PREFIX):
        return error_response(code=400, message="非B站 feed_id")
    session = DB.get_session()
    try:
        from core.models.article import Article
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return error_response(code=404, message="订阅不存在")
        count = session.query(Article).filter(Article.feed_id == feed_id).delete(synchronize_session=False)
        session.delete(feed)
        session.commit()
        return success_response({"id": feed_id, "deleted_articles": count}, f"已删除订阅及 {count} 条作品")
    except Exception as exc:
        session.rollback()
        return error_response(code=500, message=f"删除失败: {exc}")
    finally:
        session.close()


@router.post("/feeds/{feed_id}/sync")
async def sync_feed(feed_id: str, current_user: dict = Depends(get_current_user_or_ak)):
    if not feed_id.startswith(BILI_KW_PREFIX):
        return error_response(code=400, message="非B站 feed_id")
    session = DB.get_session()
    try:
        feed = session.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return error_response(code=404, message="订阅不存在")
        from jobs.mps import TaskQueue
        TaskQueue.add_task(do_job_bilibili, feed, False, task_name=f"B站手动同步:{feed_id}")
        return success_response({"id": feed_id}, "已提交同步任务")
    except Exception as exc:
        return error_response(code=500, message=f"提交同步失败: {exc}")
    finally:
        session.close()


@router.get("/articles")
async def list_articles(
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, max_length=100),
    current_user: dict = Depends(get_current_user_or_ak),
):
    return _list_articles(None, limit, offset, search)


@router.get("/feeds/{feed_id}/articles")
async def list_feed_articles(
    feed_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, max_length=100),
    current_user: dict = Depends(get_current_user_or_ak),
):
    if not feed_id.startswith(BILI_KW_PREFIX):
        return error_response(code=400, message="非B站 feed_id")
    return _list_articles(feed_id, limit, offset, search)


def _list_articles(feed_id: Optional[str], limit: int, offset: int, search: Optional[str]):
    from core.models.article import Article, DATA_STATUS
    session = DB.get_session()
    try:
        query = session.query(Article).filter(Article.status != DATA_STATUS.DELETED)
        query = query.filter(Article.feed_id == feed_id) if feed_id else query.filter(Article.feed_id.like(f"{BILI_KW_PREFIX}%"))
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(or_(Article.title.ilike(pattern), Article.description.ilike(pattern), Article.content.ilike(pattern)))
        total = query.count()
        rows = query.order_by(Article.publish_time.desc()).limit(limit).offset(offset).all()
        feed_ids = {row.feed_id for row in rows if row.feed_id}
        names = {f.id: f.name for f in session.query(Feed).filter(Feed.id.in_(feed_ids)).all()} if feed_ids else {}
        result = []
        for row in rows:
            item = row.to_dict()
            item["feed_name"] = names.get(row.feed_id, "未知订阅")
            result.append(item)
        return success_response({"list": result, "total": total})
    except Exception as exc:
        return error_response(code=500, message=f"查询B站作品失败: {exc}")
    finally:
        session.close()
