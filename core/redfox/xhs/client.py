"""小红书 (XHS) redfox 接口薄封装。

对应 redfox 接口:
  * ``search_articles(keyword, page, sort)``        —— 关键词搜索笔记 (通用接口)
  * ``search_users(keyword, offset)``               —— 关键词搜索用户 (SDK)
  * ``get_user_works(user_id, offset, sort_type)``  —— 单用户作品列表 (SDK)

业务方法挂在 ``XhsClient`` (继承 ``RedfoxClient``) 上;  SDK 初始化 /
调用日志 / 异常归一 / 线程缓存都来自 ``core.redfox.base`` 共性层。
本模块只添加 XHS 平台特定方法 + ``parse_work_publish_time`` 工具。

模块对外通过 ``core.redfox.xhs`` 暴露模块级便捷函数,  内部按线程
懒缓存 ``XhsClient``,  httpx.Client 非线程安全,  需要每个工作线程
独立持有,  缓存机制见 ``core.redfox.base._get_client_for``。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable

from ..base import (
    PAGE_SIZE,
    RedfoxClient,
    RedfoxError,
    _get_client_for,
)
from ..validation import extract_items


# ---------------------------------------------------------------------------
# 模块级常量 (XHS 平台路径)
# ---------------------------------------------------------------------------

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
        """按关键词搜索小红书笔记 (通用接口)。

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
    ) -> Iterable[Dict[str, Any]]:
        """按页迭代关键词搜索结果。

        用于增量抓取时按页翻直到 ``publish_time <= last_publish_time``
        或达到 ``max_pages`` / ``max_count`` 上限。
        """
        for page in range(1, max(1, int(max_pages)) + 1):
            data = self.search_articles(
                keyword=keyword,
                page=page,
                sort=sort,
            ) or {}
            notes = extract_items("xhs", data)
            if not notes:
                return
            for note in notes:
                if isinstance(note, dict):
                    yield note
            has_more = data.get("hasMore")
            # 通用接口返回 hasMore (1/0); 同时以不足一页兜底判断结束。
            if len(notes) < PAGE_SIZE or has_more is False or has_more == 0:
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
    ) -> Iterable[Dict[str, Any]]:
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
            yield from notes
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
) -> Iterable[Dict[str, Any]]:
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
) -> Iterable[Dict[str, Any]]:
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
    "SEARCH_USERS_PATH",
    "GET_USER_WORKS_PATH",
    # 搜索排序
    "SORT_DEFAULT",
    "SORT_LATEST",
    "VALID_SORTS",
    # 共用常量 (供旧 import 兼容)
    "PAGE_SIZE",
]
