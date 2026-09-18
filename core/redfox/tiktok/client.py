"""TikTok Redfox 关键词视频搜索。"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from ..base import RedfoxClient, RedfoxError, _get_client_for

SEARCH_VIDEOS_PATH = "/story/api/tiktok/ability/searchVideo"
PAGE_SIZE = 20


class TikTokClient(RedfoxClient):
    def search_videos(self, keyword: str, offset: int = 0, count: int = PAGE_SIZE, region: str = "US") -> Any:
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_videos: keyword 不能为空")
        count = max(1, min(PAGE_SIZE, int(count or PAGE_SIZE)))
        payload = {
            "keyword": kw, "offset": str(max(0, int(offset or 0))),
            "count": str(count), "sortType": "0", "publishTime": "0",
            "region": (region or "US").upper(),
        }
        return self._sdk_call(
            endpoint=SEARCH_VIDEOS_PATH,
            request_payload=payload,
            sdk_op=lambda: self._sdk.tiktok.search_videos(
                keyword=kw, offset=payload["offset"], count=payload["count"],
                sort_type="0", publish_time="0", region=payload["region"],
            ),
        )

    def iter_search_videos(self, keyword: str, max_pages: int = 5, region: str = "US") -> Iterable[Dict[str, Any]]:
        for page in range(max(1, int(max_pages))):
            data = self.search_videos(keyword, offset=page * PAGE_SIZE, count=PAGE_SIZE, region=region)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("list") or data.get("items") or data.get("videos") or []
            else:
                items = []
            if not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            if len(items) < PAGE_SIZE:
                return


def _get_default_client() -> TikTokClient:
    return _get_client_for("tiktok", TikTokClient)


def search_videos(keyword: str, offset: int = 0, count: int = PAGE_SIZE, region: str = "US"):
    return _get_default_client().search_videos(keyword, offset, count, region)


def iter_search_videos(keyword: str, max_pages: int = 5, region: str = "US"):
    return _get_default_client().iter_search_videos(keyword, max_pages, region)
