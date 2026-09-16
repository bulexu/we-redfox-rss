"""小红书 redfox 接口薄封装。

对应 redfox SDK ``client.xiaohongshu.*`` 命名空间:
  * ``search_articles(keyword, offset, sort_type)`` —— 关键词搜索笔记
  * ``search_users(keyword, offset)``             —— 关键词搜索用户
  * ``get_user_works(user_id, offset, sort_type)`` —— 单用户作品列表

模块对外只暴露 ``search_articles`` / ``search_users`` / ``get_user_works``
三个便捷函数,  内部按线程懒缓存 ``_XhsClient``,  与
``core/redfox/client.py`` 一致:  httpx.Client 非线程安全,  需要每个
工作线程独立持有。
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from redfox import RedFoxClient
from redfox.exceptions import (
    RedFoxAPIError,
    RedFoxAuthError,
    RedFoxRateLimitError,
)

from core.config import cfg
from core.print import print_error, print_warning
from core.redis_client import record_redfox_call

# ---------------------------------------------------------------------------
# 与 wechat 命名空间对称: SDK 错误统一归一为 ``RedfoxError``
# ---------------------------------------------------------------------------
RedfoxError = RedFoxAPIError

DEFAULT_BASE_URL = "https://redfox.hk"
SEARCH_ARTICLES_PATH = "/story/api/xhsUser/searchArticle"
SEARCH_USERS_PATH = "/story/api/xhsUser/searchUser"
GET_USER_WORKS_PATH = "/story/api/xhsUser/getUserWorks"

SUCCESS_CODE = 2000
PAGE_SIZE = 20  # XHS 单页固定 20 条, 与 wechat 一致


class _XhsClient:
    """XHS redfox 接口薄封装。

    构造时从 ``config.yaml`` 的 ``redfox.api_key`` / ``redfox.base_url`` /
    ``redfox.timeout`` 读取,  缺省回落到环境变量。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        cfg_key = cfg.get("redfox.api_key", "") if cfg else ""
        cfg_url = cfg.get("redfox.base_url", "") if cfg else ""
        cfg_timeout = cfg.get("redfox.timeout", 15) if cfg else 15

        self._api_key = (
            api_key
            or cfg_key
            or os.getenv("REDFOX_API_KEY", "")
        )
        self._base_url = (
            base_url
            or cfg_url
            or os.getenv("REDFOX_BASE_URL", "")
            or DEFAULT_BASE_URL
        )
        self._timeout = timeout or cfg_timeout or 15

        if not self._api_key:
            raise RedfoxError(
                "REDFOX_API_KEY 未配置,  请在环境变量或 config.yaml 的 "
                "redfox.api_key 中设置"
            )

        self._sdk = RedFoxClient(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=int(self._timeout),
        )

    # ------------------------------------------------------------------
    # 日志归一
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_feed_id(payload: Dict[str, Any]) -> str:
        """从请求参数里提取用于日志归因的 feed_id。"""
        if not isinstance(payload, dict):
            return ""
        for k in ("keyword", "userId", "account"):
            v = payload.get(k)
            if v:
                return str(v)[:128]
        return ""

    def _record_call(
        self,
        endpoint: str,
        success: bool,
        latency_ms: int,
        feed_id: str = "",
        request: Optional[Dict[str, Any]] = None,
        error_msg: str = "",
        code: int = 0,
        http_status: int = 0,
    ) -> None:
        try:
            record_redfox_call(
                endpoint=endpoint,
                code=int(code or 0),
                success=success,
                latency_ms=int(latency_ms or 0),
                feed_id=feed_id,
                request=request or {},
                error_msg=error_msg,
                http_status=int(http_status or 0),
            )
        except Exception as exc:  # noqa: BLE001
            print_warning(f"记录 redfox XHS 调用日志失败: {exc}")

    def _sdk_call(
        self,
        endpoint: str,
        request_payload: Dict[str, Any],
        sdk_op,
    ) -> Dict[str, Any]:
        started = time.time()
        feed_id = self._extract_feed_id(request_payload)
        try:
            data = sdk_op()
        except RedFoxAuthError as e:
            latency = int((time.time() - started) * 1000)
            self._record_call(
                endpoint=endpoint,
                success=False,
                latency_ms=latency,
                feed_id=feed_id,
                request=request_payload,
                error_msg=f"auth: {e}",
                code=int(getattr(e, "code", 0) or 0),
                http_status=401,
            )
            raise RedfoxError(f"Redfox 鉴权失败: {e}") from e
        except RedFoxRateLimitError as e:
            latency = int((time.time() - started) * 1000)
            self._record_call(
                endpoint=endpoint,
                success=False,
                latency_ms=latency,
                feed_id=feed_id,
                request=request_payload,
                error_msg=f"rate_limit: {e}",
                code=int(getattr(e, "code", 0) or 0),
                http_status=429,
            )
            raise RedfoxError(f"Redfox 频率限制: {e}") from e
        except RedFoxAPIError as e:
            latency = int((time.time() - started) * 1000)
            self._record_call(
                endpoint=endpoint,
                success=False,
                latency_ms=latency,
                feed_id=feed_id,
                request=request_payload,
                error_msg=str(e),
                code=int(getattr(e, "code", 0) or 0),
            )
            raise RedfoxError(f"Redfox 业务错误: {e}") from e
        except Exception as e:  # noqa: BLE001
            latency = int((time.time() - started) * 1000)
            print_error(f"Redfox XHS 调用异常: {e}")
            self._record_call(
                endpoint=endpoint,
                success=False,
                latency_ms=latency,
                feed_id=feed_id,
                request=request_payload,
                error_msg=f"exception: {e}",
            )
            raise RedfoxError(f"Redfox XHS 调用异常: {e}") from e

        latency = int((time.time() - started) * 1000)
        data_dict = data if isinstance(data, dict) else {}
        self._record_call(
            endpoint=endpoint,
            success=True,
            latency_ms=latency,
            feed_id=feed_id,
            request=request_payload,
            code=SUCCESS_CODE,
        )
        return data_dict

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
        page_size: int = 20,
    ) -> Iterable[Dict[str, Any]]:
        """按页迭代关键词搜索结果。

        用于增量抓取时按页翻直到 ``publish_time <= last_publish_time``
        或达到 ``max_pages`` / ``max_count`` 上限。
        """
        if page_size <= 0:
            page_size = 20
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
                user_id=uid,
                offset=offset,
                sort_type=str(sort_type),
            ),
        )

    def iter_user_works(
        self,
        user_id: str = "",
        max_pages: int = 5,
        sort_type: str = "2",
        page_size: int = 20,
    ) -> Iterable[Dict[str, Any]]:
        """按页迭代单用户作品列表。"""
        if page_size <= 0:
            page_size = 20
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
# 线程局部客户端缓存 (与 core.redfox.client 一致)
# ---------------------------------------------------------------------------

_local_clients: dict[int, "_XhsClient"] = {}
_clients_lock = threading.Lock()


def _get_default_client() -> _XhsClient:
    tid = threading.get_ident()
    client = _local_clients.get(tid)
    if client is not None:
        return client
    with _clients_lock:
        client = _local_clients.get(tid)
        if client is None:
            client = _XhsClient()
            _local_clients[tid] = client
    return client


def close_all_clients() -> None:
    with _clients_lock:
        clients = list(_local_clients.values())
        _local_clients.clear()
    for client in clients:
        try:
            client.close()
        except Exception as exc:  # noqa: BLE001
            print_warning(f"关闭 redfox XHS 客户端失败: {exc}")


# ---------------------------------------------------------------------------
# 模块级便捷函数
# ---------------------------------------------------------------------------

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
    page_size: int = 20,
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
    page_size: int = 20,
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
    "RedfoxError",
    "search_articles",
    "iter_search_articles",
    "search_users",
    "get_user_works",
    "iter_user_works",
    "parse_work_publish_time",
    "close_all_clients",
    "DEFAULT_BASE_URL",
    "SEARCH_ARTICLES_PATH",
    "SEARCH_USERS_PATH",
    "GET_USER_WORKS_PATH",
    "SUCCESS_CODE",
    "PAGE_SIZE",
]