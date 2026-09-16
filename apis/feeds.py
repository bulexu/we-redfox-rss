"""通用 Feed 列表 (跨平台) — 用于 FeedSelector / 跨平台批量配置。

背景:
  * 之前 selector 组件固定调 ``/mps`` (只查公众号),  导致小红书订阅无法
    作为 tag / message_task / filter_rule / lark_bitable 的关联源。
  * 现在抽出 ``/feeds`` 跨平台端点, 统一返回多平台订阅源,
    ``platform`` 字段区分, ``id`` 是 Feed.id (公众号 / 小红书各自的命名空间)。

路由前缀: ``/feeds``
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.feed import (
    Feed,
    PLATFORM_MP,
    PLATFORM_UNKNOWN,
    PLATFORM_XHS,
    infer_platform_from_id,
)
from core.redfox.xhs.sync import XHS_KW_PREFIX, XHS_U_PREFIX
from .base import error_response, success_response

router = APIRouter(prefix="/feeds", tags=["通用 Feed"])


def _feed_to_selector_item(f: Feed) -> dict:
    """Feed → FeedSelector 用精简字段 (id/name/cover/platform)。

    platform 优先用字段,NULL 时按 id 前缀兜底推断。
    target 只对 XHS 有意义 (keyword 文本 / userId),公众号场景给空字符串,
    前端不需要展示。
    """
    platform = f.platform or infer_platform_from_id(f.id)
    target = ""
    if platform == PLATFORM_XHS and f.target:
        target = f.target
    return {
        "id": f.id,
        "name": f.name or f.id,
        "cover": f.cover or "",
        "platform": platform,
        "status": f.status,
        # FeedSelector 在 option 上展示 platform badge + 可选的 target 提示
        "target": target,
    }


@router.get("", summary="列出 feed (跨平台,用于 FeedSelector)")
async def list_feeds(
    platform: Optional[str] = Query(
        None,
        pattern="^(mp|xhs)$",
        description="平台过滤: mp / xhs; 不传=全部",
    ),
    status: Optional[int] = Query(None, ge=0, le=1, description="状态过滤: 0=禁用 1=启用"),
    kw: Optional[str] = Query(None, max_length=100, description="按名称模糊搜索"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user_or_ak),
):
    """跨平台 Feed 列表,供 FeedSelector 之类的跨平台配置组件调用。

    数据来源: ``feeds`` 表全表扫描;``platform`` 列过滤,有 NULL 历史数据时
    按 id 前缀推断兜底 (``MP_WXS_`` → mp, ``XHS_KW_/XHS_U_`` → xhs)。

    性能: ``platform`` 列已加索引;大量数据场景再加 server-side 分页即可。
    """
    session = DB.get_session()
    try:
        # 不传 platform 时同时返回 mp + xhs;NULL 平台数据按 id 前缀兜底
        if platform == PLATFORM_MP:
            query = session.query(Feed).filter(
                (Feed.platform == PLATFORM_MP) | Feed.platform.is_(None),
            ).filter(Feed.id.like("MP_WXS_%"))
        elif platform == PLATFORM_XHS:
            query = session.query(Feed).filter(
                (Feed.platform == PLATFORM_XHS) | Feed.platform.is_(None),
            ).filter(
                (Feed.id.like(f"{XHS_KW_PREFIX}%")) | (Feed.id.like(f"{XHS_U_PREFIX}%"))
            )
        else:
            # 全部平台: 限定已知 id 前缀,排除 FEATURED_MP_ID 与历史脏数据
            query = session.query(Feed).filter(
                Feed.id.like("MP_WXS_%")
                | Feed.id.like(f"{XHS_KW_PREFIX}%")
                | Feed.id.like(f"{XHS_U_PREFIX}%")
            )

        if status is not None:
            query = query.filter(Feed.status == status)
        if kw:
            query = query.filter(Feed.name.ilike(f"%{kw}%"))

        total = query.count()
        rows = (
            query.order_by(Feed.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return success_response({
            "list": [_feed_to_selector_item(f) for f in rows],
            "total": total,
            "page": {"limit": limit, "offset": offset},
        })
    except Exception as e:
        return error_response(code=500, message=f"查询 Feed 列表失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass