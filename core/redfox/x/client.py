"""X (Twitter) Redfox 搜索接口封装。"""
from __future__ import annotations

import json

from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, Optional

from ..base import RedfoxClient, RedfoxError, _get_client_for
from ..schema import ArticleSchema
from ..validation import checked_item, extract_items

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
    ) -> Iterable[ArticleSchema]:
        cursor: Optional[str] = None
        seen_cursors: set[str] = set()
        for _ in range(max(1, int(max_pages))):
            data = self.search_tweets(keyword, search_type=search_type, cursor=cursor) or {}
            tweets = extract_items("x", data)
            if not tweets:
                return
            for tweet in tweets:
                if isinstance(tweet, dict):
                    article = normalize_item(tweet)
                    if article is not None:
                        yield article
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


def iter_search_tweets(keyword: str, max_pages: int = 5, search_type: str = "Latest") -> Iterable[ArticleSchema]:
    return _get_default_client().iter_search_tweets(keyword, max_pages, search_type)


# Redfox 原始作品 → 统一 Article 字段；不访问数据库。
def _as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0



def normalize_item(tweet: Dict[str, Any]) -> ArticleSchema | None:
    tweet_id = str(tweet.get("tweetId") or tweet.get("id") or "").strip()
    if not tweet_id:
        return None
    text = str(tweet.get("text") or tweet.get("fullText") or "").strip()
    user = tweet.get("user") if isinstance(tweet.get("user"), dict) else {}
    username = str(tweet.get("username") or user.get("username") or user.get("screenName") or "").lstrip("@").strip()
    display_name = str(user.get("displayName") or user.get("name") or username).strip()
    medias = tweet.get("medias") if isinstance(tweet.get("medias"), list) else []
    image_urls = [
        str(media.get("coverUrl") or media.get("url") or "").strip()
        for media in medias if isinstance(media, dict)
    ]
    image_urls = [url for url in image_urls if url]
    url = str(tweet.get("tweetUrl") or tweet.get("url") or "").strip()
    if not url and username:
        url = f"https://x.com/{username}/status/{tweet_id}"
    elif not url:
        url = f"https://x.com/i/status/{tweet_id}"
    extinfo = {
        "platform": "x", "tweet_id": tweet_id, "username": username,
        "language": tweet.get("language") or "",
        "quote_count": _as_int(tweet.get("quoteCount")),
        "followers": _as_int(user.get("followers")),
        "verified": bool(user.get("verified")),
        "location": user.get("location") or "", "avatar": user.get("avatar") or "",
        "medias": medias,
    }
    item = {
        "id": f"x_{tweet_id}", "title": (text[:280] or "(无正文)"),
        "content": text, "description": text,
        "pic_url": image_urls[0][:500] if image_urls else None,
        "url": url[:500],
        "publish_time": parse_publish_time(tweet.get("createdAt") or tweet.get("created_at")),
        "author": display_name[:255] or None, "author_id": username[:255] or None,
        "image_urls": json.dumps(image_urls, ensure_ascii=False),
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": _as_int(tweet.get("likeCount")),
        "comments_count": _as_int(tweet.get("replyCount")),
        "collected_count": _as_int(tweet.get("bookmarkCount")),
        "read_count": _as_int(tweet.get("viewCount")),
        "share_count": _as_int(tweet.get("retweetCount")),
    }
    return ArticleSchema.from_record(checked_item("x", tweet, item))
