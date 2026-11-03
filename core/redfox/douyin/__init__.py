"""抖音 Redfox 接口与同步入口。"""
from .client import (
    PAGE_SIZE,
    SEARCH_ARTICLES_PATH,
    DouyinClient,
    RedfoxError,
    iter_search_articles,
    parse_work_publish_time,
    search_articles,
)
from .sync import (
    AUTO_DISABLE_ERROR_THRESHOLD,
    DY_KW_PREFIX,
    build_feed_id,
    do_job_douyin,
)

__all__ = [
    "DouyinClient",
    "RedfoxError",
    "do_job_douyin",
    "build_feed_id",
    "search_articles",
    "iter_search_articles",
    "parse_work_publish_time",
    "DY_KW_PREFIX",
    "AUTO_DISABLE_ERROR_THRESHOLD",
    "SEARCH_ARTICLES_PATH",
    "PAGE_SIZE",
]
