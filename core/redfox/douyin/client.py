"""抖音 (Douyin) Redfox 接口薄封装。"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable

from ..base import RedfoxClient, RedfoxError, _get_client_for, enterprise_enabled
from ..schema import ArticleSchema
from ..validation import checked_item, extract_items


# 普通搜索响应默认每页 10 条；同步上限按此估算分页预算。
PAGE_SIZE = 10

REALTIME_SEARCH_PATH = "/story/api/dy/work/search"


SEARCH_ARTICLES_PATH = "/story/api/dy/data/searchWork"


class DouyinClient(RedfoxClient):
    """在公共 Redfox 客户端之上增加抖音业务方法。"""

    def search_articles(
        self,
        keyword: str,
        page_num: int = 1,
        page_size: int = PAGE_SIZE,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Dict[str, Any]:
        """企业账号使用实时搜索，其余账号保留广域库搜索。"""
        if enterprise_enabled():
            target_page = max(1, int(page_num or 1))
            for number, data in enumerate(self._iter_realtime_pages(keyword, target_page), 1):
                if number == target_page:
                    return data
            return {}
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_articles: keyword 不能为空")
        page_num = max(1, int(page_num or 1))
        page_size = max(1, min(50, int(page_size or PAGE_SIZE)))
        payload: Dict[str, Any] = {
            "keyword": kw,
            "exactMatch": False,
            "pageNum": page_num,
            "pageSize": page_size,
        }
        if start_date:
            payload["startDate"] = start_date
        if end_date:
            payload["endDate"] = end_date
        return self._sdk_call(
            endpoint=SEARCH_ARTICLES_PATH,
            request_payload=payload,
            # 当前安装的 SDK 便捷方法尚未暴露 exactMatch；使用 SDK 自带的
            # 底层 post（仍保留鉴权、重试和错误处理）发送服务端已支持的参数。
            sdk_op=lambda: self._sdk.post(SEARCH_ARTICLES_PATH, data=payload),
        )

    def _iter_realtime_pages(self, keyword: str, max_pages: int):
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_articles: keyword 不能为空")
        offset = "0"
        seen = {offset}
        for _ in range(max(1, int(max_pages or 1))):
            # 不限时间避免漏掉历史补采；订阅时间条件在本地过滤。
            payload = {"queryWord": kw, "sort": "2", "timeRange": "0", "offset": offset}
            data = self._sdk_call(
                endpoint=REALTIME_SEARCH_PATH,
                request_payload=payload,
                sdk_op=lambda: self._sdk.post(REALTIME_SEARCH_PATH, data=payload),
            ) or {}
            yield data
            next_offset = data.get("nextOffset")
            if str(data.get("hasMore", 0)) != "1" or next_offset in (None, ""):
                return
            offset = str(next_offset)
            if offset in seen:
                return
            seen.add(offset)

    def iter_search_articles(
        self,
        keyword: str,
        max_pages: int = 5,
        page_size: int = PAGE_SIZE,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Iterable[ArticleSchema]:
        if enterprise_enabled():
            for data in self._iter_realtime_pages(keyword, max_pages):
                for item in extract_items("douyin", data):
                    published = str(item.get("publishTime") or "")[:10]
                    if start_date and published and published < start_date:
                        continue
                    if end_date and published and published > end_date:
                        continue
                    article = normalize_item(item)
                    if article is not None:
                        yield article
            return
        size = max(1, min(50, int(page_size or PAGE_SIZE)))
        for page_num in range(1, max(1, int(max_pages)) + 1):
            data = self.search_articles(
                keyword=keyword,
                page_num=page_num,
                page_size=size,
                start_date=start_date,
                end_date=end_date,
            ) or {}
            items = extract_items("douyin", data)
            if not items:
                return
            for raw in items:
                article = normalize_item(raw)
                if article is not None:
                    yield article
            total = int(data.get("total") or 0)
            actual_size = max(1, int(data.get("pageSize") or size))
            actual_page = max(1, int(data.get("pageNum") or page_num))
            if (total and actual_page * actual_size >= total) or (not total and len(items) < actual_size):
                return


def _get_default_client() -> DouyinClient:
    return _get_client_for("douyin", DouyinClient)


def search_articles(
    keyword: str,
    page_num: int = 1,
    page_size: int = PAGE_SIZE,
    start_date: str | None = None,
    end_date: str | None = None,
):
    return _get_default_client().search_articles(
        keyword, page_num, page_size, start_date, end_date
    )


def iter_search_articles(
    keyword: str,
    max_pages: int = 5,
    page_size: int = PAGE_SIZE,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Iterable[ArticleSchema]:
    return _get_default_client().iter_search_articles(
        keyword, max_pages, page_size, start_date, end_date
    )


def parse_work_publish_time(value: Any) -> int:
    """兼容秒/毫秒时间戳和 Redfox 日期字符串。"""
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    text = re.sub(r":\s+", ":", str(value).strip())
    if text.isdigit():
        number = int(text)
        return number // 1000 if number > 10_000_000_000 else number
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return 0


__all__ = [
    "normalize_item",
    "DouyinClient",
    "RedfoxError",
    "search_articles",
    "iter_search_articles",
    "parse_work_publish_time",
    "SEARCH_ARTICLES_PATH",
    "PAGE_SIZE",
]


# Redfox 原始作品 → 统一 Article 字段；不访问数据库。
def _pick(data: Any, *paths: str, default=None):
    """从 Redfox 新旧两种字段风格中取第一个非空值。"""
    for path in paths:
        current = data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(current, list):
            current = current[0] if current else None
        if current not in (None, ""):
            return current
    return default



def _as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0



def normalize_item(work: Dict[str, Any]) -> ArticleSchema | None:
    """把抖音作品转换成共用 Article 字段。"""
    raw_work_id = str(
        _pick(work, "workId", "awemeId", "aweme_id", "videoId", "id", default="")
    ).strip()
    if not raw_work_id:
        return None

    description = str(
        _pick(
            work, "content", "workDesc", "videoDesc", "desc", "description",
            "workTitle", "videoTitle", "title", default="",
        )
    )
    title = str(
        _pick(
            work, "workTitle", "videoTitle", "title", "content", "desc", "videoDesc",
            "workDesc", default="",
        )
    )
    cover_url = str(
        _pick(
            work,
            "coverUrl",
            "videoCover",
            "workCover",
            "cover",
            "video.cover.url_list",
            "video.dynamic_cover.url_list",
            default="",
        )
    )
    work_url = str(
        _pick(
            work, "opusUrl", "workUrl", "videoShareUrl", "shareUrl", "share_url",
            "videoUrl", "url", default="",
        )
    )
    video_url = str(
        _pick(
            work,
            "videoUrl",
            "playUrl",
            "video.play_addr.url_list",
            "video.download_addr.url_list",
            default="",
        )
    )
    publish_value = _pick(
        work, "workPublishTime", "videoCreateTime", "publishTime", "createTime",
        "create_time", default=0,
    )
    author = str(
        _pick(
            work, "authorName", "accountNickname", "accountName", "userNickname",
            "author.nickname", "nickname", default="",
        )
    )
    author_id = str(
        _pick(
            work,
            "accountUserid",
            "authorUid",
            "authorSecUid",
            "accountId",
            "authorId",
            "userId",
            "secUserId",
            "sec_uid",
            "author.sec_uid",
            "author.uid",
            "uid",
            default="",
        )
    )
    images = work.get("imageUrlList")
    image_urls = [url for url in images if isinstance(url, str) and url] if isinstance(images, list) else []
    if not image_urls and cover_url:
        image_urls = [cover_url]
    video_type = _as_int(work.get("videoType"))
    extinfo = {
        "platform": "dy",
        "work_id": raw_work_id,
        "video_type": video_type,
        "author_account": str(_pick(work, "authorAccount", "authorUniqueId", default="")),
        "author_avatar": str(_pick(work, "authorAvatar", "authorAvatarUrl", default="")),
        "author_sec_uid": str(work.get("authorSecUid") or ""),
        "author_short_id": str(work.get("authorShortId") or ""),
        "tag_list": work.get("tagList") if isinstance(work.get("tagList"), list) else [],
        "video_url": video_url,
        "duration": _as_int(_pick(work, "duration", "video.duration", default=0)),
    }

    # 企业接口独有字段仅在响应提供时保留，避免把“未知”当成零/否。
    for source, target in (
        ("authorFansCount", "author_fans_count"), ("forwardCount", "forward_count"),
        ("isDeleted", "is_deleted"), ("isProhibited", "is_prohibited"),
        ("tags", "tags"), ("bgmName", "bgm_name"), ("updateTime", "update_time"),
    ):
        if source in work:
            extinfo[target] = work[source]

    item = {
        "id": raw_work_id,
        "show_type": 0 if video_type == 68 else 5,
        "title": title[:1000],
        "content": description,
        "description": description,
        "pic_url": cover_url or None,
        "url": work_url[:500],
        "publish_time": parse_work_publish_time(publish_value),
        "author": author[:255] or None,
        "author_id": author_id[:255] or None,
        "image_urls": json.dumps(image_urls, ensure_ascii=False),
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "liked_count": _as_int(_pick(work, "workLikedCount", "likedCount", "likeCount", "diggCount", "statistics.digg_count")),
        "comments_count": _as_int(_pick(work, "workCommentsCount", "commentsCount", "commentCount", "statistics.comment_count")),
        "collected_count": _as_int(_pick(work, "workCollectedCount", "collectedCount", "collectCount", "statistics.collect_count")),
        "read_count": _as_int(_pick(work, "workReadedCount", "viewCount", "playCount", "statistics.play_count")),
        "share_count": _as_int(_pick(work, "workSharedCount", "sharedCount", "shareCount", "statistics.share_count")),
    }
    return ArticleSchema.from_record(checked_item("douyin", work, item))
