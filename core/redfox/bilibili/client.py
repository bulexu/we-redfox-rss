"""哔哩哔哩 Redfox 接口封装。"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List

from ..base import RedfoxClient, RedfoxError, _get_client_for, enterprise_enabled
from ..schema import ArticleSchema
from ..validation import checked_item, extract_items

REALTIME_SEARCH_PATH = "/story/api/bili/search"  # 企业关键词实时搜索
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

        if enterprise_enabled():
            payload = {"keyword": kw, "page": str(page)}
            if order:
                payload["order"] = order
            return self._sdk_call(
                endpoint=REALTIME_SEARCH_PATH,
                request_payload=payload,
                sdk_op=lambda: self._sdk.post(REALTIME_SEARCH_PATH, data=payload),
            )

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

    def iter_search_works(self, keyword: str, max_pages: int = 5, order: str = ORDER_LATEST) -> Iterable[ArticleSchema]:
        realtime = enterprise_enabled()
        seen: set[str] = set()
        for page in range(1, max(1, int(max_pages)) + 1):
            data = self.search_works(keyword, page, order) or {}
            items = extract_items("bilibili", data)
            if not items:
                return
            new_items = 0
            for item in items:
                article = normalize_item(item)
                if article is None or (realtime and article.id in seen):
                    continue
                seen.add(article.id)
                new_items += 1
                yield article
            pages = int(data.get("pages") or 0)
            total = int(data.get("total") or 0)
            if (
                (pages and page >= pages)
                or (not realtime and total and page * PAGE_SIZE >= total)
                or (not realtime and not pages and len(items) < PAGE_SIZE)
                or (realtime and not new_items)
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


def iter_search_works(keyword: str, max_pages: int = 5, order: str = ORDER_LATEST) -> Iterable[ArticleSchema]:
    return _get_default_client().iter_search_works(keyword, max_pages, order)


# Redfox 原始作品 → 统一 Article 字段；不访问数据库。
def _as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0



def _clean_text(value: Any) -> str:
    """去掉搜索结果标题里的高亮标签 (如 ``<em class="keyword">``) 并反转义。"""
    text = html.unescape(str(value or ""))
    return re.sub(r"<[^>]+>", "", text).strip()



def _normalize_tags(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []



def _normalize_cover(value: Any) -> str:
    pic_url = str(value or "").strip()
    if pic_url.startswith("//"):
        return "https:" + pic_url
    if pic_url.startswith("http://"):
        return "https://" + pic_url[len("http://"):]
    return pic_url



def normalize_item(work: Dict[str, Any]) -> ArticleSchema | None:
    bvid = str(work.get("bvId") or work.get("bvid") or work.get("id") or "").strip()
    if not bvid:
        return None
    title = _clean_text(work.get("title"))
    description = _clean_text(work.get("description"))
    pic_url = _normalize_cover(work.get("cover") or work.get("picUrl") or work.get("coverUrl"))
    tags = _normalize_tags(work.get("tags") if work.get("tags") is not None else work.get("tagNames"))
    url = str(work.get("url") or work.get("workUrl") or f"https://www.bilibili.com/video/{bvid}")
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    extinfo = {
        "platform": "bili", "bvid": bvid,
        "av_id": work.get("avId") or 0,
        "duration": _as_int(work.get("duration")),
        "category_id": str(work.get("categoryId") or ""),
        "category_name": str(work.get("categoryName") or ""),
        "type": str(work.get("type") or ""),
        "danmaku_count": _as_int(work.get("danmakuCount")),
        "total_danmaku_count": _as_int(work.get("totalDanmakuCount")),
        "tags": tags,
        "author_avatar": _normalize_cover(work.get("avatar")),
    }
    item = {
        "id": bvid, "title": title[:1000], "content": description,
        "description": description, "pic_url": pic_url[:500] or None,
        "url": url[:500],
        "publish_time": parse_publish_time(work.get("publishTime") or work.get("created")),
        "author": str(work.get("nickname") or work.get("author") or "")[:255] or None,
        "author_id": str(work.get("authorId") or "")[:255] or None,
        "image_urls": json.dumps([pic_url], ensure_ascii=False) if pic_url else "[]",
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": _as_int(work.get("likeNum") if work.get("likeNum") is not None else work.get("likeCount")),
        "comments_count": _as_int(work.get("commentNum") if work.get("commentNum") is not None else work.get("commentCount")),
        "collected_count": _as_int(work.get("collectNum") if work.get("collectNum") is not None else work.get("favoriteCount")),
        "read_count": _as_int(work.get("viewNum") if work.get("viewNum") is not None else work.get("playCount")),
        "share_count": _as_int(work.get("shareCount")),
    }
    return ArticleSchema.from_record(checked_item("bilibili", work, item))
