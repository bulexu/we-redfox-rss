"""哔哩哔哩 Redfox 广域库接口封装。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable

from ..base import RedfoxClient, RedfoxError, _get_client_for, is_enterprise_account

SEARCH_WORKS_PATH = "/story/api/bili/search"                 # 广域库 (企业账号)
SEARCH_WORKS_PATH_LEGACY = "/story/api/bili/data/workSearch"  # 旧接口 (非企业账号)
PAGE_SIZE = 20  # 广域库单页固定 20 条

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

        if is_enterprise_account():
            payload: Dict[str, Any] = {"keyword": kw, "page": str(page)}
            if order:
                payload["order"] = order
            return self._sdk_call(
                endpoint=SEARCH_WORKS_PATH,
                request_payload=payload,
                # SDK 便捷方法未覆盖该搜索接口，直接通过 SDK 底层 post 发送；
                # 鉴权、重试和响应解包仍由官方 SDK 负责。
                sdk_op=lambda: self._sdk.post(SEARCH_WORKS_PATH, data=payload),
            )

        # 非企业账号不支持广域库接口，回落到旧接口。
        payload = {
            "keyword": kw,
            "exactMatch": False,
            "page": str(page),
            "pageSize": PAGE_SIZE,
            "order": LEGACY_ORDER_MAP.get(order, "time"),
        }
        return self._sdk_call(
            endpoint=SEARCH_WORKS_PATH_LEGACY,
            request_payload=payload,
            sdk_op=lambda: self._sdk.post(SEARCH_WORKS_PATH_LEGACY, data=payload),
        )

    def iter_search_works(self, keyword: str, max_pages: int = 5, order: str = ORDER_LATEST) -> Iterable[Dict[str, Any]]:
        for page in range(1, max(1, int(max_pages)) + 1):
            data = self.search_works(keyword, page, order) or {}
            # 广域库返回 opusInfoList；旧接口返回 workList/total。
            items = data.get("opusInfoList") or data.get("workList") or []
            if not isinstance(items, list) or not items:
                return
            for item in items:
                if isinstance(item, dict):
                    yield item
            pages = int(data.get("pages") or 0)
            total = int(data.get("total") or 0)
            if (
                len(items) < PAGE_SIZE
                or (pages and page >= pages)
                or (total and page * PAGE_SIZE >= total)
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


def iter_search_works(keyword: str, max_pages: int = 5, order: str = ORDER_LATEST):
    return _get_default_client().iter_search_works(keyword, max_pages, order)
