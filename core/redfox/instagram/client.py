"""Instagram Redfox 关键词综合搜索。"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..base import RedfoxClient, RedfoxError, _get_client_for

SEARCH_POSTS_PATH = "/story/api/ins/search"
PAGE_SIZE = 20


class InstagramClient(RedfoxClient):
    def search_posts(self, keyword: str, pagination_token: Optional[str] = None) -> Dict[str, Any]:
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_posts: keyword 不能为空")
        payload: Dict[str, Any] = {"keyword": kw}
        if pagination_token:
            payload["paginationToken"] = pagination_token
        return self._sdk_call(
            endpoint=SEARCH_POSTS_PATH,
            request_payload=payload,
            sdk_op=lambda: self._sdk.instagram.search(
                keyword=kw, pagination_token=pagination_token,
            ),
        )

    def iter_search_posts(self, keyword: str, max_pages: int = 5) -> Iterable[Dict[str, Any]]:
        token: Optional[str] = None
        seen: set[str] = set()
        for _ in range(max(1, int(max_pages))):
            data = self.search_posts(keyword, token) or {}
            items = data.get("items") or data.get("posts") or data.get("list") or []
            if not isinstance(items, list) or not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            next_token = str(
                data.get("paginationToken") or data.get("nextPaginationToken")
                or data.get("nextToken") or data.get("continuationToken") or ""
            ).strip()
            if len(items) < PAGE_SIZE or not next_token or next_token in seen:
                return
            seen.add(next_token)
            token = next_token


def _get_default_client() -> InstagramClient:
    return _get_client_for("instagram", InstagramClient)


def search_posts(keyword: str, pagination_token: Optional[str] = None):
    return _get_default_client().search_posts(keyword, pagination_token)


def iter_search_posts(keyword: str, max_pages: int = 5):
    return _get_default_client().iter_search_posts(keyword, max_pages)
