"""哔哩哔哩 Redfox 优质库接口封装。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable

from ..base import RedfoxClient, RedfoxError, _get_client_for

SEARCH_WORKS_PATH = "/story/api/bili/data/workSearch"
PAGE_SIZE = 20


class BilibiliClient(RedfoxClient):
    def search_works(self, keyword: str, page: int = 1, page_size: int = PAGE_SIZE, order: str = "time") -> Dict[str, Any]:
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_works: keyword 不能为空")
        page = max(1, int(page or 1))
        page_size = max(1, min(50, int(page_size or PAGE_SIZE)))
        payload = {
            "keyword": kw,
            "exactMatch": False,
            "page": str(page),
            "pageSize": page_size,
            "order": order or "time",
        }
        return self._sdk_call(
            endpoint=SEARCH_WORKS_PATH,
            request_payload=payload,
            # SDK 当前版本的便捷方法未暴露 exactMatch，直接通过 SDK 底层
            # post 发送；鉴权、重试和响应解包仍由官方 SDK 负责。
            sdk_op=lambda: self._sdk.post(SEARCH_WORKS_PATH, data=payload),
        )

    def iter_search_works(self, keyword: str, max_pages: int = 5, page_size: int = PAGE_SIZE, order: str = "time") -> Iterable[Dict[str, Any]]:
        size = max(1, min(50, int(page_size or PAGE_SIZE)))
        for page in range(1, max(1, int(max_pages)) + 1):
            data = self.search_works(keyword, page, size, order) or {}
            items = data.get("workList") or data.get("list") or data.get("works") or []
            if not items:
                return
            yield from items
            total = int(data.get("total") or 0)
            if len(items) < size or (total and page * size >= total):
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


def search_works(keyword: str, page: int = 1, page_size: int = PAGE_SIZE, order: str = "time"):
    return _get_default_client().search_works(keyword, page, page_size, order)


def iter_search_works(keyword: str, max_pages: int = 5, page_size: int = PAGE_SIZE, order: str = "time"):
    return _get_default_client().iter_search_works(keyword, max_pages, page_size, order)
