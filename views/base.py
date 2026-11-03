from math import e
from fastapi import APIRouter, Request, Depends, Query, HTTPException
from core.lax.template_parser import TemplateParser
from fastapi.responses import HTMLResponse
from core.db import DB
from core.models.feed import (
    Feed,
    PLATFORM_MP,
    PLATFORM_XHS,
    PLATFORM_DY,
    PLATFORM_BILI,
    PLATFORM_X,
    PLATFORM_TIKTOK,
    PLATFORM_YOUTUBE,
    PLATFORM_INSTAGRAM,
    infer_platform_from_id,
)
from core.models.article import Article
from driver.wxarticle import Web
from datetime import datetime
from core.models.tags import Tags
from sqlalchemy import or_
import json

# ===== 平台元数据 (legacy views 站内共用) =====
# feed.id 前缀,  与 core/models/feed.py 的 infer_platform_from_id 保持一致。
# 新平台接入时在这里补一行即可让 /views/home 与平台列表页同步展示。
PLATFORM_PREFIXES = {
    PLATFORM_MP: ("MP_WXS_",),
    PLATFORM_XHS: ("XHS_KW_", "XHS_U_"),
    PLATFORM_DY: ("DY_KW_",),
    PLATFORM_BILI: ("BILI_KW_",),
    PLATFORM_X: ("X_KW_",),
    PLATFORM_TIKTOK: ("TIKTOK_KW_",),
    PLATFORM_YOUTUBE: ("YOUTUBE_KW_",),
    PLATFORM_INSTAGRAM: ("INSTAGRAM_KW_",),
}

PLATFORM_LABELS = {
    PLATFORM_MP: "公众号",
    PLATFORM_XHS: "小红书",
    PLATFORM_DY: "抖音",
    PLATFORM_BILI: "B站",
    PLATFORM_X: "X",
    PLATFORM_TIKTOK: "TikTok",
    PLATFORM_YOUTUBE: "YouTube",
    PLATFORM_INSTAGRAM: "Instagram",
}

# 展示顺序: 公众号 / 小红书优先, 其余按接入先后排列。
PLATFORM_ORDER = [
    PLATFORM_MP,
    PLATFORM_XHS,
    PLATFORM_DY,
    PLATFORM_BILI,
    PLATFORM_X,
    PLATFORM_TIKTOK,
    PLATFORM_YOUTUBE,
    PLATFORM_INSTAGRAM,
]

# 已有独立列表页的平台沿用旧地址,  其余走通用 /views/platform/{key}。
_PLATFORM_VIEW_URLS = {
    PLATFORM_MP: "/views/mps",
    PLATFORM_XHS: "/views/xhs",
}


def get_platform_view_url(platform: str) -> str:
    """平台列表页地址。"""
    return _PLATFORM_VIEW_URLS.get(platform, f"/views/platform/{platform}")


def get_platform_summary() -> list:
    """各平台订阅数,  供首页平台 tab 展示。"""
    session = DB.get_session()
    summary = []
    try:
        for platform in PLATFORM_ORDER:
            prefixes = PLATFORM_PREFIXES[platform]
            id_filter = or_(*[Feed.id.like(f"{prefix}%") for prefix in prefixes])
            feed_count = session.query(Feed).filter(
                Feed.status == 1, id_filter
            ).count()
            summary.append({
                "key": platform,
                "label": PLATFORM_LABELS[platform],
                "count": feed_count,
                "url": get_platform_view_url(platform),
            })
    except Exception as e:
        print(f"获取平台统计错误: {str(e)}")
    finally:
        session.close()
    return summary


def get_feeds_view(platform: str, page: int, limit: int):
    """通用订阅列表。platform 传 None 时返回全部平台的最新订阅。

    过滤规则与 apis/feeds.py 一致:  platform 列命中或为 NULL 老数据,
    再用 feed.id 前缀兜底,  避免历史脏数据混入。
    """
    session = DB.get_session()
    data = {}
    try:
        if platform:
            prefixes = PLATFORM_PREFIXES.get(platform)
            if not prefixes:
                return {}
            id_filter = or_(*[Feed.id.like(f"{prefix}%") for prefix in prefixes])
            query = session.query(Feed).filter(
                Feed.status == 1,
                (Feed.platform == platform) | Feed.platform.is_(None),
                id_filter,
            )
        else:
            id_filter = or_(*[
                Feed.id.like(f"{prefix}%")
                for prefixes in PLATFORM_PREFIXES.values()
                for prefix in prefixes
            ])
            query = session.query(Feed).filter(Feed.status == 1, id_filter)

        total = query.count()
        offset = (page - 1) * limit
        feeds = (
            query.order_by(Feed.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        feed_list = []
        for feed in feeds:
            article_count = session.query(Article).filter(
                Article.feed_id == feed.id,
                Article.status == 1,
            ).count()
            feed_platform = feed.platform or infer_platform_from_id(feed.id)
            feed_list.append({
                "id": feed.id,
                "name": feed.name,
                "cover": Web.get_image_url(feed.cover) if feed.cover else "",
                "intro": feed.intro or "",
                "kind": "keyword" if "_KW_" in feed.id else "account",
                "platform": feed_platform,
                "platform_label": PLATFORM_LABELS.get(feed_platform, feed_platform),
                "article_count": article_count,
                "sync_time": datetime.fromtimestamp(feed.sync_time).strftime('%Y-%m-%d %H:%M') if feed.sync_time else "未同步",
            })

        total_pages = (total + limit - 1) // limit
        data = {
            "feeds": feed_list,
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total,
            "limit": limit,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }
    except Exception as e:
        print(f"获取订阅列表错误: {str(e)}")
    finally:
        session.close()
    return data
#获取公众号视图数据
def get_mps_view(
    page: int ,
    limit: int
):
    session = DB.get_session()
    data={}
    try:
        # 仅显示公众号订阅源，剔除小红书等其他平台
        mp_filter = (Feed.platform == PLATFORM_MP) | Feed.platform.is_(None)
        # 查询标签总数
        total = session.query(Feed).filter(Feed.status == 1, mp_filter).count()

        # 计算偏移量
        offset = (page - 1) * limit

        # 查询公众号列表
        feeds = (
            session.query(Feed)
            .filter(Feed.status == 1, mp_filter)
            .order_by(Feed.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        
        # 处理公众号数据
        feed_list = []
        for feed in feeds:
            # 对于 Feed 表，id 就是公众号的 ID
            mp_id = feed.id
            
            # 统计该公众号的文章数量
            article_count = session.query(Article).filter(
                Article.feed_id == mp_id,
                Article.status == 1
            ).count()
            
            feed_data = {
                "id": feed.id,
                "name": feed.name,
                "cover": Web.get_image_url(feed.cover) if feed.cover else "",
                "intro": feed.intro,
                "mp_count": 1,  # Feed 本身就是一个公众号
                "article_count": article_count,
                "sync_time": datetime.fromtimestamp(feed.sync_time).strftime('%Y-%m-%d %H:%M') if feed.sync_time else "未同步",
                "created_at": feed.created_at.strftime('%Y-%m-%d') if feed.created_at else ""
            }
            feed_list.append(feed_data)
        
        # 计算分页信息
        total_pages = (total + limit - 1) // limit
        has_prev = page > 1
        has_next = page < total_pages
        
        # 构建面包屑
        breadcrumb = [
            {"name": "公众号", "url": "/views/mps"}
        ]
        # 使用模板引擎渲染
        data={
            "feeds": feed_list,
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total,
            "limit": limit,
            "has_prev": has_prev,
            "has_next": has_next,
            "breadcrumb": breadcrumb
        }
    except Exception as e:
        print(e)
    finally:
        session.close()
    return data



#显示所有标签，支持分页
def get_tags_view(
    page: int ,
    limit: int 
):
    """
    显示所有标签，支持分页
    """
    session = DB.get_session()
    data={}
    try:
        # 查询标签总数
        total = session.query(Tags).filter(Tags.status == 1).count()
        
        # 计算偏移量
        offset = (page - 1) * limit
        
        # 查询标签列表
        tags = session.query(Tags).filter(Tags.status == 1).order_by(Tags.created_at.desc()).offset(offset).limit(limit).all()
        
        # 处理标签数据
        tag_list = []
        for tag in tags:
            # 改名自 mps_id (commit 65aaffd1): Tags 模型字段是 feed_ids
            mps_ids = []
            if tag.feed_ids:
                try:
                    mps_data = json.loads(tag.feed_ids)
                    mps_ids = [str(mp['id']) for mp in mps_data] if isinstance(mps_data, list) else []
                except (json.JSONDecodeError, TypeError):
                    mps_ids = []
            
            # 统计文章数量
            article_count = 0
            if mps_ids:
                article_count = session.query(Article).filter(
                    Article.feed_id.in_(mps_ids),
                    Article.status == 1
                ).count()
            
            # 获取关联的公众号数量
            mp_count = len(mps_ids) if mps_ids else 0
            
            tag_data = {
                "id": tag.id,
                "name": tag.name,
                "cover": Web.get_image_url(tag.cover) if tag.cover else "",
                "intro": tag.intro,
                "mp_count": mp_count,
                "article_count": article_count,
                "sync_time": datetime.fromtimestamp(tag.sync_time).strftime('%Y-%m-%d %H:%M') if tag.sync_time else "未同步",
                "created_at": tag.created_at.strftime('%Y-%m-%d') if tag.created_at else ""
            }
            tag_list.append(tag_data)
        
        # 计算分页信息
        total_pages = (total + limit - 1) // limit
        has_prev = page > 1
        has_next = page < total_pages
        
        # 构建面包屑
        breadcrumb = [
            {"name": "首页", "url": "/views/home"}
        ]
        
        data={
            "tags": tag_list,
            "current_page": page,
            "total_pages": total_pages,
            "total_items": total,
            "limit": limit,
            "has_prev": has_prev,
            "has_next": has_next,
        }
        
        
    except Exception as e:
        print(f"获取首页数据错误: {str(e)}")
    finally:
        session.close()
    return data

def _render_template_with_error(template_path: str, error_msg: str, breadcrumb: list) -> HTMLResponse:
    """渲染错误页面的辅助函数"""
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render({
            "site": base.site,
            "error": error_msg,
            "breadcrumb": breadcrumb
        })
        return HTMLResponse(content=html_content)
    except Exception:
        return HTMLResponse(content=f"<h1>系统错误</h1><p>{error_msg}</p>")

def process_content_images(content: str) -> str:
    """处理文章内容中的图片链接，添加前缀"""
    if not content:
        return content
    return Web.proxy_images(content,isProxy=False)