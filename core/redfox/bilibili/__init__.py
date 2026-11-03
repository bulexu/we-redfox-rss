"""哔哩哔哩 Redfox 接口与同步入口。"""
from .client import (
    ORDER_DEFAULT,
    ORDER_LATEST,
    PAGE_SIZE,
    SEARCH_WORKS_PATH,
    SEARCH_WORKS_PATH_LEGACY,
    VALID_ORDERS,
    BilibiliClient,
    RedfoxError,
    iter_search_works,
    parse_publish_time,
    search_works,
)
from .sync import AUTO_DISABLE_ERROR_THRESHOLD, BILI_KW_PREFIX, build_feed_id, do_job_bilibili

__all__ = [
    "BilibiliClient", "RedfoxError", "PAGE_SIZE", "SEARCH_WORKS_PATH", "SEARCH_WORKS_PATH_LEGACY",
    "ORDER_DEFAULT", "ORDER_LATEST", "VALID_ORDERS",
    "search_works", "iter_search_works", "parse_publish_time",
    "BILI_KW_PREFIX", "AUTO_DISABLE_ERROR_THRESHOLD", "build_feed_id", "do_job_bilibili",
]
