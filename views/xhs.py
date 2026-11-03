"""小红书订阅列表页 (公众号 ``/views/mps`` 的小红书对应)。

列出所有 platform=xhs 的 Feed,  支持分页。  渲染摘要与 mps.html 同源,
但 item_name / breadcrumb 用"小红书订阅"。
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from core.db import DB
from core.lax.template_parser import TemplateParser
from core.models.article import Article
from core.models.feed import Feed, PLATFORM_XHS
from views.config import base
from views.base import _render_template_with_error
from driver.wxarticle import Web
from datetime import datetime

router = APIRouter(tags=["小红书"])


def _get_xhs_feeds_view(page: int, limit: int) -> dict:
    """拉取所有 platform=xhs 的 feed,  附文章计数。"""
    session = DB.get_session()
    try:
        # 兼容老数据 platform=NULL:  按 id 前缀再筛一次
        query = session.query(Feed).filter(
            (Feed.platform == PLATFORM_XHS) | Feed.platform.is_(None),
        ).filter(
            (Feed.id.like("XHS_KW_%")) | (Feed.id.like("XHS_U_%"))
        ).order_by(Feed.created_at.desc())

        total = query.count()
        offset = (page - 1) * limit
        feeds = query.offset(offset).limit(limit).all()

        feed_list = []
        for feed in feeds:
            article_count = session.query(Article).filter(
                Article.feed_id == feed.id,
                Article.status == 1,
            ).count()
            feed_list.append({
                "id": feed.id,
                "name": feed.name,
                "cover": Web.get_image_url(feed.cover) if feed.cover else "",
                "intro": feed.intro or "",
                "kind": "keyword" if feed.id.startswith("XHS_KW_") else "account",
                "article_count": article_count,
                "sync_time": datetime.fromtimestamp(feed.sync_time).strftime('%Y-%m-%d %H:%M') if feed.sync_time else "未同步",
            })

        total_pages = (total + limit - 1) // limit
        return {
            "feeds": feed_list,
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total,
            "limit": limit,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "breadcrumb": [{"name": "小红书订阅", "url": "/views/xhs"}],
        }
    finally:
        session.close()


@router.get("/xhs", response_class=HTMLResponse, summary="小红书订阅 - 显示所有小红书订阅")
async def xhs_view(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(12, ge=1, le=20, description="每页数量"),
):
    """小红书订阅列表页 (与 /views/mps 对称)。"""
    try:
        data = _get_xhs_feeds_view(page, limit)
        data["site"] = base.site
        data["item_name"] = "个订阅"
        data["prev_url"] = (
            f"/views/xhs?page={page - 1}&limit={limit}" if data["has_prev"] else None
        )
        data["next_url"] = (
            f"/views/xhs?page={page + 1}&limit={limit}" if data["has_next"] else None
        )

        template_path = base.xhs_template
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render(data)
        return HTMLResponse(content=html_content)
    except Exception as e:
        print(f"获取小红书订阅列表错误: {str(e)}")
        return _render_template_with_error(
            base.xhs_template,
            f"加载小红书订阅时出现错误: {str(e)}",
            [{"name": "首页", "url": "/views/home"}],
        )