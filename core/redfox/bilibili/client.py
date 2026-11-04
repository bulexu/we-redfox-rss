"""哔哩哔哩 Redfox 接口封装。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable

from ..base import RedfoxClient, RedfoxError, _get_client_for
from ..validation import extract_items

SEARCH_WORKS_PATH = "/story/api/bili/data/workSearch"  # 关键词搜索作品 (通用接口)
PAGE_SIZE = 20  # 通用接口单页固定 20 条

# 排序方式: 不填为综合, pubdate 最新发布。
ORDER_DEFAULT = ""
ORDER_LATEST = "pubdate"
VALID_ORDERS = {"", "click", "pubdate", "dm", "stow"}
# 旧接口的排序值与新接口不同 (旧接口用 time 表示最新发布)
LEGACY_ORDER_MAP = {"": "time", "pubdate": "time", "click": "click", "dm": "dm", "stow": "stow"}


class BilibiliClient(RedfoxClient):
    def search_works(self, keyword: str, page: int = 1, order: str = ORDER_LATEST) -> Dict[str, Any]:
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_works: keyword 不能为空")
        page = max(1, int(page or 1))
        order = (order or "").strip()
        if order not in VALID_ORDERS:
            raise RedfoxError(f"search_works: 不支持的排序方式 {order!r}")

        payload = {
            "keyword": kw,
            "exactMatch": False,
            "page": str(page),
            "pageSize": PAGE_SIZE,
            "order": LEGACY_ORDER_MAP.get(order, "time"),
        }
        return self._sdk_call(
            endpoint=SEARCH_WORKS_PATH,
            request_payload=payload,
            sdk_op=lambda: self._sdk.post(SEARCH_WORKS_PATH, data=payload),
        )

    def iter_search_works(self, keyword: str, max_pages: int = 5, order: str = ORDER_LATEST) -> Iterable[Dict[str, Any]]:
        for page in range(1, max(1, int(max_pages)) + 1):
            data = self.search_works(keyword, page, order) or {}
            items = extract_items("bilibili", data)
            if not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            pages = int(data.get("pages") or 0)
            total = int(data.get("total") or 0)
            if (
                len(items) < PAGE_SIZE
                or (pages and page >= pages)
                or (total and page * PAGE_SIZE >= total)
            ):
                return


def parse_publish_time(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        return number // 1000 if number > 10_000_000_000 else number
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return 0


def _get_default_client() -> BilibiliClient:
    return _get_client_for("bilibili", BilibiliClient)


def search_works(keyword: str, page: int = 1, order: str = ORDER_LATEST):
    return _get_default_client().search_works(keyword, page, order)


def iter_search_works(keyword: str, max_pages: int = 5, order: str = ORDER_LATEST):
    return _get_default_client().iter_search_works(keyword, max_pages, order)
