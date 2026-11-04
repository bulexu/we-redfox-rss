"""小红书 (XHS) redfox 接口薄封装。

对应 redfox 接口:
  * ``search_articles(keyword, page, sort)``        —— 关键词搜索笔记 (通用接口)
  * ``search_users(keyword, offset)``               —— 关键词搜索用户 (SDK)
  * ``get_user_works(user_id, offset, sort_type)``  —— 单用户作品列表 (SDK)

业务方法挂在 ``XhsClient`` (继承 ``RedfoxClient``) 上;  SDK 初始化 /
调用日志 / 异常归一 / 线程缓存都来自 ``core.redfox.base`` 共性层。
本模块包含 XHS 平台接口、分页和统一 ``ArticleSchema`` 映射。

模块对外通过 ``core.redfox.xhs`` 暴露模块级便捷函数,  内部按线程
懒缓存 ``XhsClient``,  httpx.Client 非线程安全,  需要每个工作线程
独立持有,  缓存机制见 ``core.redfox.base._get_client_for``。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable

from ..base import (
    PAGE_SIZE,
    RedfoxClient,
    RedfoxError,
    _get_client_for,
    enterprise_enabled,
)
from ..schema import ArticleSchema
from ..validation import checked_item, extract_items


# ---------------------------------------------------------------------------
# 模块级常量 (XHS 平台路径)
# ---------------------------------------------------------------------------

REALTIME_SEARCH_PATH = "/story/api/xhs/ability/searchWork"  # 企业关键词实时搜索
SEARCH_ARTICLES_PATH = "/story/api/xhsUser/searchArticle"  # 关键词搜索笔记 (通用接口)
SEARCH_USERS_PATH = "/story/api/xhsUser/searchUser"
GET_USER_WORKS_PATH = "/story/api/xhsUser/getUserWorks"

SORT_DEFAULT = "综合"
SORT_LATEST = "最新"
VALID_SORTS = {"综合", "最新", "最多点赞", "最多评论", "最多收藏"}
# 通用接口 sortType: "0"=综合, "2"=最新, "4"=最热
SORT_TO_LEGACY = {"综合": "0", "最新": "2", "最多点赞": "4", "最多评论": "4", "最多收藏": "4"}


# ---------------------------------------------------------------------------
# XHS 平台客户端
# ---------------------------------------------------------------------------

class XhsClient(RedfoxClient):
    """小红书 redfox 接口客户端 (继承 ``RedfoxClient`` 共性层)。

    只添加小红书特有业务方法;  日志 / 异常 / 计时 / 线程缓存都复用基类。
    """

    # ------------------------------------------------------------------
    # 业务方法
    # ------------------------------------------------------------------

    def search_articles(
        self,
        keyword: str = "",
        page: int = 1,
        sort: str = SORT_DEFAULT,
    ) -> Dict[str, Any]:
        """按关键词搜索笔记；企业账号使用实时接口。

        Args:
            keyword: 搜索关键词
            page:    页码,  从 1 开始
            sort:    "综合" / "最新" / "最多点赞" / "最多评论" / "最多收藏"
        """
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_articles: keyword 不能为空")
        try:
            page = max(1, int(page or 1))
        except (TypeError, ValueError):
            page = 1
        if sort not in VALID_SORTS:
            raise RedfoxError(f"search_articles: 不支持的排序方式 {sort!r}")

        if enterprise_enabled():
            payload = {
                "note_type": "不限", "noteTime": "不限", "page": page,
                "sort": sort, "keyword": kw,
            }
            return self._sdk_call(
                endpoint=REALTIME_SEARCH_PATH,
                request_payload=payload,
                sdk_op=lambda: self._sdk.post(REALTIME_SEARCH_PATH, data=payload),
            )

        offset = (page - 1) * PAGE_SIZE
        sort_type = SORT_TO_LEGACY.get(sort, "0")
        return self._sdk_call(
            endpoint=SEARCH_ARTICLES_PATH,
            request_payload={
                "keyword": kw,
                "offset": offset,
                "sortType": sort_type,
            },
            sdk_op=lambda: self._sdk.xiaohongshu.search_articles(
                keyword=kw,
                offset=offset,
                sort_type=sort_type,
            ),
        )

    def iter_search_articles(
        self,
        keyword: str = "",
        max_pages: int = 5,
        sort: str = SORT_LATEST,
    ) -> Iterable[ArticleSchema]:
        """按页迭代关键词搜索结果。

        用于增量抓取时按页翻直到 ``publish_time <= last_publish_time``
        或达到 ``max_pages`` / ``max_count`` 上限。
        """
        realtime = enterprise_enabled()
        seen: set[str] = set()
        for page in range(1, max(1, int(max_pages)) + 1):
            data = self.search_articles(
                keyword=keyword,
                page=page,
                sort=sort,
            ) or {}
            notes = extract_items("xhs", data)
            if not notes:
                return
            new_items = 0
            for note in notes:
                article = normalize_item(note)
                if article is None or (realtime and article.id in seen):
                    continue
                seen.add(article.id)
                new_items += 1
                yield article
            has_more = data.get("hasMore")
            if has_more is not None and str(has_more).lower() in ("0", "false"):
                return
            if realtime:
                # 实时接口未约定页大小/hasMore，短页不能代表结束。
                # 空页、重复页或 max_pages 到达时结束。
                if not new_items:
                    return
            elif len(notes) < PAGE_SIZE:
                return

    def search_users(
        self,
        keyword: str = "",
        offset: int = 0,
    ) -> Dict[str, Any]:
        """按关键词搜索小红书用户 (账号订阅前置查询)。"""
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_users: keyword 不能为空")
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0

        return self._sdk_call(
            endpoint=SEARCH_USERS_PATH,
            request_payload={"keyword": kw, "offset": offset},
            sdk_op=lambda: self._sdk.xiaohongshu.search_users(
                keyword=kw, offset=offset,
            ),
        )

    def get_user_works(
        self,
        user_id: str = "",
        offset: int = 0,
        sort_type: str = "2",
    ) -> Dict[str, Any]:
        """拉取指定小红书用户的作品列表 (账号订阅核心调用)。

        Args:
            user_id:  XHS userId (accountUserid)
            offset:   分页偏移
            sort_type: "0"=默认, "2"=最新, "4"=最热
        """
        uid = (user_id or "").strip()
        if not uid:
            raise RedfoxError("get_user_works: user_id 不能为空")
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0

        return self._sdk_call(
            endpoint=GET_USER_WORKS_PATH,
            request_payload={
                "userId": uid,
                "offset": offset,
                "sortType": str(sort_type),
            },
            sdk_op=lambda: self._sdk.xiaohongshu.get_user_works(
                userid=uid,
                offset=offset,
                sort_type=str(sort_type),
            ),
        )

    def iter_user_works(
        self,
        user_id: str = "",
        max_pages: int = 5,
        sort_type: str = "2",
        page_size: int = PAGE_SIZE,
    ) -> Iterable[ArticleSchema]:
        """按页迭代单用户作品列表。"""
        if page_size <= 0:
            page_size = PAGE_SIZE
        for page in range(max(1, int(max_pages))):
            data = self.get_user_works(
                user_id=user_id,
                offset=page * page_size,
                sort_type=sort_type,
            )
            # redfox 优质库返回 ``list`` 字段 (SDK 已解包 data,  老版本曾用 ``notes``)
            notes = extract_items("xhs", data)
            if not notes:
                return
            for raw in notes:
                article = normalize_item(raw)
                if article is not None:
                    yield article
            has_more = data.get("hasMore")
            if has_more is False or has_more == 0:
                return


# ---------------------------------------------------------------------------
# 模块级便捷函数
# ---------------------------------------------------------------------------

def _get_default_client() -> XhsClient:
    return _get_client_for("xhs", XhsClient)


def search_articles(
    keyword: str = "",
    page: int = 1,
    sort: str = SORT_DEFAULT,
) -> Dict[str, Any]:
    return _get_default_client().search_articles(
        keyword=keyword, page=page, sort=sort,
    )


def iter_search_articles(
    keyword: str = "",
    max_pages: int = 5,
    sort: str = SORT_LATEST,
) -> Iterable[ArticleSchema]:
    return _get_default_client().iter_search_articles(
        keyword=keyword,
        max_pages=max_pages,
        sort=sort,
    )


def search_users(keyword: str = "", offset: int = 0) -> Dict[str, Any]:
    return _get_default_client().search_users(keyword=keyword, offset=offset)


def get_user_works(
    user_id: str = "",
    offset: int = 0,
    sort_type: str = "2",
) -> Dict[str, Any]:
    return _get_default_client().get_user_works(
        user_id=user_id, offset=offset, sort_type=sort_type,
    )


def iter_user_works(
    user_id: str = "",
    max_pages: int = 5,
    sort_type: str = "2",
    page_size: int = PAGE_SIZE,
) -> Iterable[ArticleSchema]:
    return _get_default_client().iter_user_works(
        user_id=user_id,
        max_pages=max_pages,
        sort_type=sort_type,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# 解析工具: workPublishTime ("YYYY-MM-DD HH:MM:SS") → epoch 秒
# ---------------------------------------------------------------------------

def parse_work_publish_time(value: Any) -> int:
    """redfox workPublishTime → epoch 秒。

    兼容三种形式:  ``"2025-07-21 17:09:42"`` 日期字符串、
    秒/毫秒时间戳。  解析失败返回 0。

    注意:  与 LarkBitable.last_pushed_at 不同,  Article.publish_time
    在本仓库内统一使用 ``Integer`` epoch **秒**,  见 ``core/models/article.py``。
    """
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    s = str(value).strip()
    if not s:
        return 0
    if s.isdigit():
        number = int(s)
        return number // 1000 if number > 10_000_000_000 else number
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return int(dt.timestamp())
        except ValueError:
            continue
    return 0


__all__ = [
    "normalize_item",
    "XhsClient",
    "RedfoxError",
    "search_articles",
    "iter_search_articles",
    "search_users",
    "get_user_works",
    "iter_user_works",
    "parse_work_publish_time",
    # 路径常量
    "SEARCH_ARTICLES_PATH",
    "REALTIME_SEARCH_PATH",
    "SEARCH_USERS_PATH",
    "GET_USER_WORKS_PATH",
    # 搜索排序
    "SORT_DEFAULT",
    "SORT_LATEST",
    "VALID_SORTS",
    # 共用常量 (供旧 import 兼容)
    "PAGE_SIZE",
]


# Redfox 原始作品 → 统一 Article 字段；不访问数据库。
def _as_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "")))
    except (TypeError, ValueError):
        return 0



def _normalize_image_url(url: Any) -> str:
    # Redfox 偶尔返回要求 CDN 输出 HEIF 的图片链接。Chrome/Edge 在 Windows
    # 上通常无法直接渲染 HEIF，而小红书 CDN 接受相同链接输出 WebP。
    return str(url or "").replace("format/heif", "format/webp")



def _normalize_work_type(note: Dict[str, Any]) -> tuple[str, int]:
    """``workType`` → (原始类型, Article.show_type)。

    ``workType`` 为 ``normal`` / ``video``;  show_type 语义见
    ``core/models/article.py``:  0=图文,  5=视频。
    """
    raw = str(_field(note, "workType", "noteType") or "").strip().lower()
    if raw == "video":
        return raw, 5
    return raw, 0



def _field(note: Dict[str, Any], *names: str, default=None):
    """兼容普通/实时字段名；零值保留，不被其他别名覆盖。"""
    for name in names:
        value = note.get(name)
        if value is not None and value != "":
            return value
    return default


def normalize_item(note: Dict[str, Any]) -> ArticleSchema | None:
    """普通库和企业实时响应共用的作品映射。"""
    work_id = str(_field(note, "workId", "noteId", default="")).strip()
    if not work_id:
        return None

    cover_url = _normalize_image_url(_field(note, "coverUrl", "coverImage"))
    images = note.get("picUrls")
    previews = note.get("previewUrls")
    image_urls = [_normalize_image_url(url) for url in images if isinstance(url, str) and url] if isinstance(images, list) else []
    preview_urls = [_normalize_image_url(url) for url in previews if isinstance(url, str) and url] if isinstance(previews, list) else []
    image_urls = image_urls or preview_urls or ([cover_url] if cover_url else [])
    cover_url = cover_url or (image_urls[0] if image_urls else "")

    # 实时搜索未提供正文；保留空值，不把标题当作已采集的正文。
    content = str(_field(note, "workDesc", "noteDesc", default=""))
    work_type, show_type = _normalize_work_type(note)
    extinfo = {
        "platform": "xhs", "work_id": work_id, "work_type": work_type,
        "account_type": str(note.get("accountType") or ""),
    }
    if "authorAvatar" in note:
        extinfo["author_avatar"] = str(note.get("authorAvatar") or "")
    if isinstance(previews, list):
        extinfo["preview_urls"] = preview_urls

    item = {
        "id": work_id,
        "title": str(_field(note, "workTitle", "noteTitle", default=""))[:1000],
        "content": content,
        "description": content,
        "pic_url": cover_url or None,
        "url": str(_field(note, "workUrl", "noteUrl", default="")),
        "publish_time": parse_work_publish_time(_field(note, "workPublishTime", "releaseTime")),
        "author": str(_field(note, "accountNickname", "authorName", default=""))[:255] or None,
        "author_id": str(_field(note, "accountUserid", "authorUid", default=""))[:255] or None,
        "image_urls": json.dumps(image_urls, ensure_ascii=False),
        "extinfo": json.dumps(extinfo, ensure_ascii=False),
        "show_type": show_type,
        "liked_count": _as_int(_field(note, "workLikedCount", "thumbCount")),
        "comments_count": _as_int(_field(note, "workCommentsCount", "replyCount")),
        "collected_count": _as_int(_field(note, "workCollectedCount", "favoriteCount")),
        "read_count": _as_int(note.get("workReadedCount")),
        "share_count": _as_int(_field(note, "workSharedCount", "forwardCount")),
    }
    return ArticleSchema.from_record(checked_item("xhs", note, item))
