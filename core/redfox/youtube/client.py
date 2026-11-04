"""YouTube Redfox 关键词视频搜索。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from ..base import RedfoxClient, RedfoxError, _get_client_for, as_int
from ..schema import ArticleSchema
from ..validation import checked_item, extract_items

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

    def get_transcript(self, video_url: str) -> Dict[str, Any]:
        return self._sdk_call(
            endpoint="/story/api/youtube/transcript",
            request_payload={"videoUrl": video_url},
            sdk_op=lambda: self._sdk.youtube.get_transcript(video_url=video_url),
        )

    def iter_search_videos(self, keyword: str, max_pages: int = 5) -> Iterable[ArticleSchema]:
        token: Optional[str] = None
        seen: set[str] = set()
        for _ in range(max(1, int(max_pages))):
            data = self.search_videos(keyword, token) or {}
            items = extract_items("youtube", data)
            if not items:
                return
            for item in items:
                if isinstance(item, dict):
                    article = normalize_item(item)
                    if article is not None:
                        yield article
            next_token = str(data.get("continuationToken") or data.get("nextContinuationToken") or data.get("nextToken") or "").strip()
            if len(items) < PAGE_SIZE or not next_token or next_token in seen:
                return
            seen.add(next_token)
            token = next_token


def _get_default_client() -> YouTubeClient:
    return _get_client_for("youtube", YouTubeClient)


def search_videos(keyword: str, continuation_token: Optional[str] = None):
    return _get_default_client().search_videos(keyword, continuation_token)


def iter_search_videos(keyword: str, max_pages: int = 5) -> Iterable[ArticleSchema]:
    return _get_default_client().iter_search_videos(keyword, max_pages)


def get_transcript(video_url: str):
    return _get_default_client().get_transcript(video_url)


# Redfox 原始作品 → 统一 Article 字段；不访问数据库。
def parse_publish_time(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)) or str(value).isdigit():
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    text = str(value).strip()
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        pass
    match = re.search(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", text, re.I)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        days = {"day": 1, "week": 7, "month": 30, "year": 365}.get(unit, 0) * amount
        delta = timedelta(days=days, hours=amount if unit == "hour" else 0,
                          minutes=amount if unit == "minute" else 0,
                          seconds=amount if unit == "second" else 0)
        return int((datetime.now(timezone.utc) - delta).timestamp())
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d %b %Y"):
        try:
            return int(datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return 0



def normalize_item(video: Dict[str, Any]) -> ArticleSchema | None:
    video_id = str(video.get("videoId") or video.get("id") or "").strip()
    if not video_id:
        return None
    title = str(video.get("title") or "").strip()
    description = str(video.get("description") or "").strip()
    thumbnails = video.get("thumbnails") if isinstance(video.get("thumbnails"), list) else []
    thumbnail_urls = [str(t.get("url") or "").strip() for t in thumbnails if isinstance(t, dict)]
    thumbnail_urls = [url for url in thumbnail_urls if url]
    cover = thumbnail_urls[-1] if thumbnail_urls else str(video.get("thumbnailUrl") or "").strip()
    author = str(video.get("author") or video.get("channelName") or "").strip()
    channel_id = str(video.get("channelId") or "").strip()
    extinfo = {
        "platform": "youtube", "video_id": video_id,
        "duration": video.get("duration") or "",
        "thumbnails": thumbnails,
    }
    item = {
        "id": f"youtube_{video_id}", "title": title[:1000] or description[:280] or "(无标题)",
        "content": description, "description": description,
        "pic_url": cover[:500] or None,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "publish_time": parse_publish_time(video.get("publishedTime") or video.get("publishedAt")),
        "author": author[:255] or None, "author_id": channel_id[:255] or None,
        "image_urls": json.dumps(thumbnail_urls or ([cover] if cover else []), ensure_ascii=False),
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": as_int(video.get("likeCount")),
        "comments_count": as_int(video.get("commentCount")),
        "collected_count": 0,
        "read_count": as_int(video.get("viewCount")),
        "share_count": 0,
    }
    return ArticleSchema.from_record(checked_item("youtube", video, item))
