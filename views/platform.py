"""通用平台订阅列表页 (抖音 / B站 / X / TikTok / YouTube / Instagram)。

公众号、小红书已有独立页面 (/views/mps、/views/xhs),  其余平台统一走
``/views/platform/{platform}``,  渲染复用 includes/feeds.html。
"""
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from core.lax.template_parser import TemplateParser
from views.config import base
from views.base import (
    PLATFORM_LABELS,
    _render_template_with_error,
    get_feeds_view,
    get_platform_view_url,
)

router = APIRouter(tags=["平台订阅"])


@router.get("/platform/{platform}", response_class=HTMLResponse, summary="平台订阅 - 显示指定平台的订阅源")
async def platform_view(
    platform: str,
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(12, ge=1, le=50, description="每页数量"),
):
    """按平台列出订阅源 (与 /views/xhs 对称)。"""
    label = PLATFORM_LABELS.get(platform)
    if not label:
        return _render_template_with_error(
            base.platform_template,
            f"暂不支持的平台: {platform}",
            [{"name": "首页", "url": "/views/home"}],
        )

    try:
        data = get_feeds_view(platform, page, limit)
        data["site"] = base.site
        data["platform"] = platform
        data["platform_label"] = label
        data["item_name"] = "个订阅"
        data["breadcrumb"] = [{"name": f"{label}订阅", "url": get_platform_view_url(platform)}]
        data["prev_url"] = (
            f"/views/platform/{platform}?page={page - 1}&limit={limit}"
            if data.get("has_prev") else None
        )
        data["next_url"] = (
            f"/views/platform/{platform}?page={page + 1}&limit={limit}"
            if data.get("has_next") else None
        )

        template_path = base.platform_template
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        parser = TemplateParser(template_content, template_dir=base.public_dir)
        html_content = parser.render(data)
        return HTMLResponse(content=html_content)
    except Exception as e:
        print(f"获取{label}订阅列表错误: {str(e)}")
        return _render_template_with_error(
            base.platform_template,
            f"加载{label}订阅时出现错误: {str(e)}",
            [{"name": "首页", "url": "/views/home"}],
        )
