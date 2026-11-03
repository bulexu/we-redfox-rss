"""X (Twitter) Redfox 搜索接口封装。"""
from __future__ import annotations

from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, Optional

from ..base import RedfoxClient, RedfoxError, _get_client_for

SEARCH_TWEETS_PATH = "/story/api/x/search"
PAGE_SIZE = 20


class XClient(RedfoxClient):
    def search_tweets(
        self,
        keyword: str,
        search_type: str = "Latest",
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_tweets: keyword 不能为空")
        search_type = search_type if search_type in {"Top", "Latest", "Media"} else "Latest"
        payload: Dict[str, Any] = {"keyword": kw, "searchType": search_type}
        if cursor:
            payload["cursor"] = cursor
        return self._sdk_call(
            endpoint=SEARCH_TWEETS_PATH,
            request_payload=payload,
            sdk_op=lambda: self._sdk.twitter.search_tweets(
                keyword=kw,
                search_type=search_type,
                cursor=cursor,
            ),
        )

    def iter_search_tweets(
        self,
        keyword: str,
        max_pages: int = 5,
        search_type: str = "Latest",
    ) -> Iterable[Dict[str, Any]]:
        cursor: Optional[str] = None
        seen_cursors: set[str] = set()
        for _ in range(max(1, int(max_pages))):
            data = self.search_tweets(keyword, search_type=search_type, cursor=cursor) or {}
            tweets = data.get("tweets") or data.get("list") or data.get("items") or []
            if not isinstance(tweets, list) or not tweets:
                return
            for tweet in tweets:
                if isinstance(tweet, dict):
                    yield tweet
            next_cursor = str(data.get("nextCursor") or data.get("next_cursor") or "").strip()
            if len(tweets) < PAGE_SIZE or not next_cursor or next_cursor in seen_cursors:
                return
            seen_cursors.add(next_cursor)
            cursor = next_cursor


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
    try:
        return int(parsedate_to_datetime(text).timestamp())
    except (TypeError, ValueError, OverflowError):
        return 0


def _get_default_client() -> XClient:
    return _get_client_for("x", XClient)


def search_tweets(keyword: str, search_type: str = "Latest", cursor: Optional[str] = None):
    return _get_default_client().search_tweets(keyword, search_type, cursor)


def iter_search_tweets(keyword: str, max_pages: int = 5, search_type: str = "Latest"):
    return _get_default_client().iter_search_tweets(keyword, max_pages, search_type)
