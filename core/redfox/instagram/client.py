"""Instagram Redfox 关键词综合搜索。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from ..base import RedfoxClient, RedfoxError, _get_client_for, as_int
from ..schema import ArticleSchema
from ..validation import checked_item, extract_items

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

    def iter_search_posts(self, keyword: str, max_pages: int = 5) -> Iterable[ArticleSchema]:
        token: Optional[str] = None
        seen: set[str] = set()
        for _ in range(max(1, int(max_pages))):
            data = self.search_posts(keyword, token) or {}
            items = extract_items("instagram", data)
            if not items:
                return
            for item in items:
                if isinstance(item, dict):
                    article = normalize_item(item)
                    if article is not None:
                        yield article
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


def iter_search_posts(keyword: str, max_pages: int = 5) -> Iterable[ArticleSchema]:
    return _get_default_client().iter_search_posts(keyword, max_pages)


# Redfox 原始作品 → 统一 Article 字段；不访问数据库。
def parse_publish_time(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)) or str(value).isdigit():
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0



def normalize_item(post: Dict[str, Any]) -> ArticleSchema | None:
    media_id = str(post.get("mediaId") or post.get("id") or post.get("code") or "").strip()
    code = str(post.get("code") or post.get("shortcode") or "").strip()
    if not media_id:
        return None
    caption = str(post.get("captionText") or post.get("caption") or post.get("description") or "").strip()
    user = post.get("user") if isinstance(post.get("user"), dict) else {}
    username = str(user.get("username") or post.get("username") or "").lstrip("@").strip()
    full_name = str(user.get("fullName") or user.get("name") or username).strip()
    cover = str(post.get("imageUrl") or post.get("thumbnailUrl") or "").strip()
    url = str(post.get("postUrl") or "").strip() or (f"https://www.instagram.com/p/{code}/" if code else "")
    hashtags = post.get("captionHashtags") if isinstance(post.get("captionHashtags"), list) else []
    extinfo = {
        "platform": "instagram", "media_id": media_id, "code": code,
        "media_format": post.get("mediaFormat") or "",
        "media_type": post.get("mediaType"), "video_url": post.get("videoUrl") or "",
        "duration": post.get("videoDuration") or 0, "hashtags": hashtags,
        "followers": as_int(user.get("followerCount")),
        "avatar": user.get("profilePicUrl") or "", "verified": bool(user.get("isVerified")),
    }
    item = {
        "id": f"instagram_{media_id}", "title": caption[:280] or "(无标题)",
        "content": caption, "description": caption,
        # Instagram CDN URL 带有较长的动态签名参数，不能按 500 字符截断。
        "pic_url": cover or None, "url": url[:500],
        "publish_time": parse_publish_time(post.get("takenAt") or post.get("takenAtDate")),
        "author": full_name[:255] or None, "author_id": username[:255] or None,
        "image_urls": json.dumps([cover], ensure_ascii=False) if cover else "[]",
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": as_int(post.get("likeCount")),
        "comments_count": as_int(post.get("commentCount")),
        "collected_count": 0,
        "read_count": as_int(post.get("playCount")),
        "share_count": as_int(post.get("shareCount")),
    }
    return ArticleSchema.from_record(checked_item("instagram", post, item))
