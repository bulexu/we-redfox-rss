from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional
from apis.tags import get_tags
from core.lax.template_parser import TemplateParser
from views.config import base
from core.cache import cache_view, clear_cache_pattern
from views.base import (
    PLATFORM_LABELS,
    get_tags_view,
    get_feeds_view,
    get_platform_summary,
)

# 创建路由器
router = APIRouter(tags=["首页"])

@router.get("/home", response_class=HTMLResponse, summary="首页 - 显示所有标签")
async def home_view(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(12, ge=1, le=50, description="每页数量"),
    platform: Optional[str] = Query(None, description="平台筛选: mp/xhs/dy/bili/x/tiktok/youtube/instagram")
):
    """
    首页显示所有标签，支持分页，并可按平台 tab 筛选订阅
    """
    try:
        # 平台筛选: 未知平台按"全部"处理
        if platform not in PLATFORM_LABELS:
            platform = None

        # 标签固定显示前12个
        tags_data = get_tags_view(1, 12)
        # 按平台筛选订阅 (None 表示全部平台)
        feeds_data = get_feeds_view(platform, page, limit)
        # 平台 tab 数据 (各平台订阅数)
        platforms_data = get_platform_summary()
        total_subscriptions = sum(item["count"] for item in platforms_data)

        # 读取模板文件
        template_path = base.home_template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # 生成分页URL (保留平台筛选)
        def build_page_url(page_num: int) -> str:
            params = []
            if platform:
                params.append(f"platform={platform}")
            params.append(f"page={page_num}")
            params.append(f"limit={limit}")
            return "/views/home?" + "&".join(params)

        has_prev = feeds_data.get('has_prev', False)
        has_next = feeds_data.get('has_next', False)
        prev_url = build_page_url(page - 1) if has_prev else None
        next_url = build_page_url(page + 1) if has_next else None

        data = {
            "site": base.site,
            "tags": tags_data,
            "platforms": platforms_data,
            "current_platform": platform or "",
            "total_subscriptions": total_subscriptions,
            "feeds": feeds_data.get('feeds', []),
            "current_page": page,
            "total_pages": feeds_data.get('total_pages', 1),
            "total_items": feeds_data.get('total_items', 0),
            "has_prev": has_prev,
            "has_next": has_next,
            "prev_url": prev_url,
            "next_url": next_url,
            "item_name": "个订阅"
        }
        
        # 使用模板引擎渲染
        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render(data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        print(f"获取首页数据错误: {str(e)}")
        # 读取模板文件
        template_path = base.home_template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render({
            "site": base.site,
            "error": f"加载数据时出现错误: {str(e)}",
            "breadcrumb": [{"name": "首页", "url": "/views/home"}]
        })
        
        return HTMLResponse(content=html_content)

