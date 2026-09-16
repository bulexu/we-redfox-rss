"""小红书 (XHS) redfox 接口薄封装。

对应 redfox SDK ``client.xiaohongshu.*`` 命名空间:
  * ``search_articles(keyword, offset, sort_type)`` —— 关键词搜索笔记
  * ``search_users(keyword, offset)``             —— 关键词搜索用户
  * ``get_user_works(user_id, offset, sort_type)`` —— 单用户作品列表

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


# ---------------------------------------------------------------------------
# 模块级常量 (XHS 平台路径)
# ---------------------------------------------------------------------------

SEARCH_ARTICLES_PATH = "/story/api/xhsUser/searchArticle"
SEARCH_USERS_PATH = "/story/api/xhsUser/searchUser"
GET_USER_WORKS_PATH = "/story/api/xhsUser/getUserWorks"


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
        offset: int = 0,
        sort_type: str = "0",
    ) -> Dict[str, Any]:
        """按关键词搜索小红书笔记。

        Args:
            keyword:  搜索关键词
            offset:   分页偏移,  每页 +20
            sort_type: "0"=默认(相关), "2"=最新(增量用), "4"=最热
        """
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("search_articles: keyword 不能为空")
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0

        return self._sdk_call(
            endpoint=SEARCH_ARTICLES_PATH,
            request_payload={
                "keyword": kw,
                "offset": offset,
                "sortType": str(sort_type),
            },
            sdk_op=lambda: self._sdk.xiaohongshu.search_articles(
                keyword=kw,
                offset=offset,
                sort_type=str(sort_type),
            ),
        )

    def iter_search_articles(
        self,
        keyword: str = "",
        max_pages: int = 5,
        sort_type: str = "2",
        page_size: int = PAGE_SIZE,
    ) -> Iterable[Dict[str, Any]]:
        """按页迭代关键词搜索结果。

        用于增量抓取时按页翻直到 ``publish_time <= last_publish_time``
        或达到 ``max_pages`` / ``max_count`` 上限。
        """
        if page_size <= 0:
            page_size = PAGE_SIZE
        for page in range(max(1, int(max_pages))):
            data = self.search_articles(
                keyword=keyword,
                offset=page * page_size,
                sort_type=sort_type,
            )
            notes = data.get("notes") or []
            if not notes:
                return
            yield from notes
            has_more = data.get("hasMore")
            if has_more is False:
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
            notes = data.get("notes") or []
            if not notes:
                return
            yield from notes
            has_more = data.get("hasMore")
            if has_more is False:
                return


# ---------------------------------------------------------------------------
# 模块级便捷函数
# ---------------------------------------------------------------------------

def _get_default_client() -> XhsClient:
    return _get_client_for("xhs", XhsClient)


def search_articles(
    keyword: str = "",
    offset: int = 0,
    sort_type: str = "0",
) -> Dict[str, Any]:
    return _get_default_client().search_articles(
        keyword=keyword, offset=offset, sort_type=sort_type,
    )


def iter_search_articles(
    keyword: str = "",
    max_pages: int = 5,
    sort_type: str = "2",
    page_size: int = PAGE_SIZE,
) -> Iterable[Dict[str, Any]]:
    return _get_default_client().iter_search_articles(
        keyword=keyword,
        max_pages=max_pages,
        sort_type=sort_type,
        page_size=page_size,
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

def parse_work_publish_time(text: str) -> int:
    """redfox workPublishTime → epoch 秒。

    输入格式 ``"2025-07-21 17:09:42"``。  解析失败返回 0。

    注意:  与 LarkBitable.last_pushed_at 不同,  Article.publish_time
    在本仓库内统一使用 ``Integer`` epoch **秒**,  见 ``core/models/article.py``。
    """
    if not text:
        return 0
    s = str(text).strip()
    if not s:
        return 0
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
    # 共用常量 (供旧 import 兼容)
    "PAGE_SIZE",
]
