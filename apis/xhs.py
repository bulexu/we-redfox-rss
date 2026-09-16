"""小红书 (XHS) 订阅管理 API。

路由前缀: ``/api/v1/xhs``,  与公众号 ``/api/v1/wx/mps`` 对称。

核心资源:  ``Feed`` 表中 ``id`` 以 ``XHS_KW_`` 或 ``XHS_U_`` 开头的行。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.feed import Feed
from core.print import print_error, print_info, print_warning
from core.xhs import (
    XHS_KW_PREFIX,
    XHS_U_PREFIX,
    build_feed_id,
    do_job_xhs,
)

from .base import error_response, success_response

router = APIRouter(prefix="/xhs", tags=["小红书订阅"])


# ===== Pydantic 请求模型 =====

class CreateXhsFeedRequest(BaseModel):
    """新增 XHS 订阅。

    ``kind`` 决定 ``target`` 的语义:
      * ``keyword`` — 关键词订阅, ``target`` 为搜索词,  feed.id = ``XHS_KW_<target>``
      * ``account`` — 账号订阅,  ``target`` 为 XHS userId,  feed.id = ``XHS_U_<target>``
    """
    kind: str = Field(..., pattern="^(keyword|account)$")
    target: str = Field(..., min_length=1, max_length=200)
    name: Optional[str] = Field(None, max_length=255)
    avatar: Optional[str] = Field(None, max_length=500)
    intro: Optional[str] = Field(None, max_length=255)
    max_fetch_count: int = Field(20, ge=1, le=200)
    refresh_interval_hours: int = Field(6, ge=1, le=168)


class UpdateXhsFeedRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    avatar: Optional[str] = Field(None, max_length=500)
    intro: Optional[str] = Field(None, max_length=255)
    max_fetch_count: Optional[int] = Field(None, ge=1, le=200)
    refresh_interval_hours: Optional[int] = Field(None, ge=1, le=168)
    status: Optional[int] = Field(None, ge=0, le=1)  # 0=禁用, 1=启用


class SearchUsersRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    offset: int = Field(0, ge=0)


# ===== Helper =====

def _feed_to_dict(f: Feed) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "cover": f.cover,
        "intro": f.intro,
        "status": f.status,
        "kind": "keyword" if f.id.startswith(XHS_KW_PREFIX) else (
            "account" if f.id.startswith(XHS_U_PREFIX) else "unknown"
        ),
        "target": (
            f.id[len(XHS_KW_PREFIX):]
            if f.id.startswith(XHS_KW_PREFIX)
            else f.id[len(XHS_U_PREFIX):]
            if f.id.startswith(XHS_U_PREFIX)
            else ""
        ),
        "max_fetch_count": f.max_fetch_count,
        "refresh_interval_hours": f.refresh_interval_hours,
        "last_publish_time": f.last_publish_time,
        "last_cursor": f.last_cursor,
        "sync_time": f.sync_time,
        "error_count": f.error_count,
        "last_error": f.last_error,
        "last_error_at": f.last_error_at,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


# ===== CRUD =====

@router.get("/feeds", summary="列出 XHS 订阅")
async def list_xhs_feeds(
    kind: Optional[str] = Query(None, pattern="^(keyword|account)$"),
    status: Optional[int] = Query(None, ge=0, le=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        query = session.query(Feed).filter(
            (Feed.id.like(f"{XHS_KW_PREFIX}%")) | (Feed.id.like(f"{XHS_U_PREFIX}%"))
        )
        if kind == "keyword":
            query = query.filter(Feed.id.like(f"{XHS_KW_PREFIX}%"))
        elif kind == "account":
            query = query.filter(Feed.id.like(f"{XHS_U_PREFIX}%"))
        if status is not None:
            query = query.filter(Feed.status == status)

        total = query.count()
        rows = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        return success_response({
            "list": [_feed_to_dict(f) for f in rows],
            "total": total,
            "page": {"limit": limit, "offset": offset},
        })
    except Exception as e:
        return error_response(code=500, message=f"查询 XHS 订阅失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.post("/feeds", summary="新增 XHS 订阅 (首次抓取 fire-and-forget)")
async def create_xhs_feed(
    req: CreateXhsFeedRequest,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """新增 XHS 订阅并立即触发首次抓取。

    首次抓取走 TaskQueue 异步执行,  不阻塞响应 (Q14 fire-and-forget)。
    """
    session = DB.get_session()
    try:
        feed_id = build_feed_id(req.kind, req.target)
        existing = session.query(Feed).filter(Feed.id == feed_id).first()
        if existing:
            return error_response(
                code=400,
                message=f"订阅已存在: {feed_id}",
            )

        # name: 用户显式传入 > 自动从 target 派生
        default_name = (
            req.target if req.kind == "keyword"
            else f"@{req.target[:20]}"
        )
        feed = Feed(
            id=feed_id,
            name=(req.name or default_name)[:255],
            cover=(req.avatar or "")[:255] or None,
            intro=(req.intro or "")[:255] or None,
            status=1,
            max_fetch_count=req.max_fetch_count,
            refresh_interval_hours=req.refresh_interval_hours,
            sync_time=0,
            update_time=int(time.time()),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_publish_time=0,
            last_cursor=None,
            error_count=0,
            last_error=None,
            last_error_at=None,
        )
        session.add(feed)
        session.commit()
        session.refresh(feed)

        # Q14 fire-and-forget: 提交首次同步到 TaskQueue, 立即返回
        try:
            from jobs.mps import TaskQueue
            TaskQueue.add_task(
                do_job_xhs,
                feed,
                False,
                task_name=f"xhs 首次采集:{feed.id}",
            )
        except Exception as exc:  # noqa: BLE001
            # TaskQueue 不可用时只记日志,  不阻断创建
            print_warning(f"[xhs] 提交首次采集到 TaskQueue 失败: {exc}")

        return success_response(_feed_to_dict(feed), "创建成功, 首次采集已提交")
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=f"创建 XHS 订阅失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.get("/feeds/{feed_id}", summary="获取单个 XHS 订阅详情")
async def get_xhs_feed(
    feed_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    if not (feed_id.startswith(XHS_KW_PREFIX) or feed_id.startswith(XHS_U_PREFIX)):
        return error_response(code=400, message="非 XHS feed_id")
    session = DB.get_session()
    try:
        f = session.query(Feed).filter(Feed.id == feed_id).first()
        if not f:
            return error_response(code=404, message="订阅不存在")
        return success_response(_feed_to_dict(f))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.put("/feeds/{feed_id}", summary="更新 XHS 订阅")
async def update_xhs_feed(
    feed_id: str,
    req: UpdateXhsFeedRequest,
    current_user: dict = Depends(get_current_user_or_ak),
):
    if not (feed_id.startswith(XHS_KW_PREFIX) or feed_id.startswith(XHS_U_PREFIX)):
        return error_response(code=400, message="非 XHS feed_id")
    session = DB.get_session()
    try:
        f = session.query(Feed).filter(Feed.id == feed_id).first()
        if not f:
            return error_response(code=404, message="订阅不存在")

        if req.name is not None:
            f.name = req.name
        if req.avatar is not None:
            f.cover = req.avatar
        if req.intro is not None:
            f.intro = req.intro
        if req.max_fetch_count is not None:
            f.max_fetch_count = req.max_fetch_count
        if req.refresh_interval_hours is not None:
            f.refresh_interval_hours = req.refresh_interval_hours
        if req.status is not None:
            # 启用时清零 error_count,  让失败次数从 0 重新累计
            if req.status == 1 and f.status == 0:
                f.error_count = 0
            f.status = req.status

        f.updated_at = datetime.now()
        session.commit()
        session.refresh(f)
        return success_response(_feed_to_dict(f), "更新成功")
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=f"更新失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.delete("/feeds/{feed_id}", summary="删除 XHS 订阅")
async def delete_xhs_feed(
    feed_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """硬删除订阅。  关联 Article 由调用方决定是否清理 (Q16 保留现有删除处理)。"""
    if not (feed_id.startswith(XHS_KW_PREFIX) or feed_id.startswith(XHS_U_PREFIX)):
        return error_response(code=400, message="非 XHS feed_id")
    session = DB.get_session()
    try:
        from core.models.article import Article
        f = session.query(Feed).filter(Feed.id == feed_id).first()
        if not f:
            return error_response(code=404, message="订阅不存在")

        # 删除关联 articles
        deleted_articles = session.query(Article).filter(
            Article.feed_id == feed_id
        ).delete(synchronize_session=False)

        session.delete(f)
        session.commit()

        return success_response({
            "id": feed_id,
            "deleted_articles": deleted_articles,
        }, f"已删除订阅, 同时清理 {deleted_articles} 条关联笔记")
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=f"删除失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.post("/feeds/{feed_id}/sync", summary="手动触发 XHS 同步")
async def sync_xhs_feed(
    feed_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """手动触发一次同步 (不走 cron,  立即跑)。"""
    if not (feed_id.startswith(XHS_KW_PREFIX) or feed_id.startswith(XHS_U_PREFIX)):
        return error_response(code=400, message="非 XHS feed_id")
    session = DB.get_session()
    try:
        f = session.query(Feed).filter(Feed.id == feed_id).first()
        if not f:
            return error_response(code=404, message="订阅不存在")

        # 提交到 TaskQueue,  立即返回
        try:
            from jobs.mps import TaskQueue
            TaskQueue.add_task(
                do_job_xhs,
                f,
                False,
                task_name=f"xhs 手动同步:{feed_id}",
            )
        except Exception as exc:  # noqa: BLE001
            return error_response(code=500, message=f"提交同步失败: {exc}")

        return success_response({"id": feed_id}, "已提交同步任务")
    finally:
        try:
            session.close()
        except Exception:
            pass


# ===== 用户搜索 (账号订阅前置) =====

@router.post("/search-users", summary="按关键词搜索小红书用户")
async def search_xhs_users(
    req: SearchUsersRequest,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """账号订阅前置:  输入关键词查找 userId,  选中后创建 XHS_U_<userId> 订阅。"""
    try:
        from core.xhs import search_users
        data = search_users(keyword=req.keyword, offset=req.offset)
        users = data.get("list") or data.get("users") or []
        return success_response({
            "list": users,
            "total": data.get("total", 0),
            "has_more": data.get("hasMore", False),
        })
    except Exception as e:
        return error_response(code=500, message=f"搜索小红书用户失败: {e}")


# ===== 笔记列表 (单 feed) =====

@router.get("/feeds/{feed_id}/articles", summary="列出 XHS feed 下的笔记")
async def list_xhs_feed_articles(
    feed_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user_or_ak),
):
    if not (feed_id.startswith(XHS_KW_PREFIX) or feed_id.startswith(XHS_U_PREFIX)):
        return error_response(code=400, message="非 XHS feed_id")
    session = DB.get_session()
    try:
        from core.models.article import Article
        total = session.query(Article).filter(Article.feed_id == feed_id).count()
        rows = (
            session.query(Article)
            .filter(Article.feed_id == feed_id)
            .order_by(Article.publish_time.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return success_response({
            "list": [a.to_dict() for a in rows],
            "total": total,
            "page": {"limit": limit, "offset": offset},
        })
    except Exception as e:
        return error_response(code=500, message=f"查询笔记失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass