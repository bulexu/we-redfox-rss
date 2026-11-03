"""YouTube Redfox 关键词视频搜索。"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from ..base import RedfoxClient, RedfoxError, _get_client_for

SEARCH_VIDEOS_PATH = "/story/api/youtube/searchVideo"
PAGE_SIZE = 20


class YouTubeClient(RedfoxClient):
    def search_videos(self, keyword: str, continuation_token: Optional[str] = None) -> Dict[str, Any]:
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_videos: keyword 不能为空")
        payload: Dict[str, Any] = {"searchQuery": kw}
        if continuation_token:
            payload["continuationToken"] = continuation_token
        return self._sdk_call(
            endpoint=SEARCH_VIDEOS_PATH,
            request_payload=payload,
            sdk_op=lambda: self._sdk.youtube.search_videos(
                search_query=kw, continuation_token=continuation_token,
            ),
        )

    def iter_search_videos(self, keyword: str, max_pages: int = 5) -> Iterable[Dict[str, Any]]:
        token: Optional[str] = None
        seen: set[str] = set()
        for _ in range(max(1, int(max_pages))):
            data = self.search_videos(keyword, token) or {}
            items = data.get("videos") or data.get("items") or data.get("list") or []
            if not isinstance(items, list) or not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            next_token = str(data.get("continuationToken") or data.get("nextContinuationToken") or data.get("nextToken") or "").strip()
            if len(items) < PAGE_SIZE or not next_token or next_token in seen:
                return
            seen.add(next_token)
            token = next_token


def _get_default_client() -> YouTubeClient:
    return _get_client_for("youtube", YouTubeClient)


def search_videos(keyword: str, continuation_token: Optional[str] = None):
    return _get_default_client().search_videos(keyword, continuation_token)


def iter_search_videos(keyword: str, max_pages: int = 5):
    return _get_default_client().iter_search_videos(keyword, max_pages)
