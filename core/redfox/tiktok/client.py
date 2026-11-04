"""TikTok Redfox 关键词视频搜索。"""
from __future__ import annotations

import json

from typing import Any, Dict, Iterable

from ..base import RedfoxClient, RedfoxError, _get_client_for, as_int
from ..schema import ArticleSchema
from ..validation import checked_item, extract_items

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

    def iter_search_videos(self, keyword: str, max_pages: int = 5, region: str = "US") -> Iterable[ArticleSchema]:
        for page in range(max(1, int(max_pages))):
            data = self.search_videos(keyword, offset=page * PAGE_SIZE, count=PAGE_SIZE, region=region)
            items = extract_items("tiktok", data)
            if not items:
                return
            for item in items:
                if isinstance(item, dict):
                    article = normalize_item(item)
                    if article is not None:
                        yield article
            if len(items) < PAGE_SIZE:
                return


def _get_default_client() -> TikTokClient:
    return _get_client_for("tiktok", TikTokClient)


def search_videos(keyword: str, offset: int = 0, count: int = PAGE_SIZE, region: str = "US"):
    return _get_default_client().search_videos(keyword, offset, count, region)


def iter_search_videos(keyword: str, max_pages: int = 5, region: str = "US") -> Iterable[ArticleSchema]:
    return _get_default_client().iter_search_videos(keyword, max_pages, region)


# Redfox 原始作品 → 统一 Article 字段；不访问数据库。
def normalize_item(work: Dict[str, Any]) -> ArticleSchema | None:
    work_id = str(work.get("workId") or work.get("awemeId") or work.get("id") or "").strip()
    if not work_id:
        return None
    content = str(work.get("content") or work.get("description") or work.get("desc") or "").strip()
    author = work.get("authorData") if isinstance(work.get("authorData"), dict) else {}
    stats = work.get("statsData") if isinstance(work.get("statsData"), dict) else {}
    video = work.get("videoData") if isinstance(work.get("videoData"), dict) else {}
    username = str(author.get("userHandle") or author.get("uniqueId") or author.get("userId") or "").lstrip("@").strip()
    author_name = str(author.get("userName") or author.get("nickname") or username).strip()
    cover = str(video.get("coverImage") or work.get("coverUrl") or "").strip()
    url = str(work.get("shareLink") or work.get("workUrl") or "").strip()
    if not url and username:
        url = f"https://www.tiktok.com/@{username}/video/{work_id}"
    extinfo = {
        "platform": "tiktok", "work_id": work_id,
        "media_type": work.get("mediaType") or "video",
        "video_url": video.get("playAddress") or "",
        "download_url": video.get("downloadNoMarkAddress") or "",
        "duration": as_int(video.get("playDuration")),
        "followers": as_int(author.get("fansCount")),
        "avatar": author.get("avatarImage") or "",
        "repost_count": as_int(stats.get("repostTotal")),
    }
    item = {
        "id": f"tiktok_{work_id}", "title": content[:280] or "(无标题)",
        "content": content, "description": content,
        "pic_url": cover[:500] or None, "url": url[:500],
        "publish_time": as_int(work.get("publishTime")),
        "author": author_name[:255] or None, "author_id": username[:255] or None,
        "image_urls": json.dumps([cover], ensure_ascii=False) if cover else "[]",
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": as_int(stats.get("likeCount")),
        "comments_count": as_int(stats.get("commentTotal")),
        "collected_count": as_int(stats.get("favoriteCount")),
        "read_count": as_int(stats.get("viewCount")),
        "share_count": as_int(stats.get("shareTotal")),
    }
    return ArticleSchema.from_record(checked_item("tiktok", work, item))
