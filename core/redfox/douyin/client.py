"""抖音 (Douyin) Redfox 接口薄封装。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable

from ..base import PAGE_SIZE, RedfoxClient, RedfoxError, _get_client_for


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
        """使用抖音广域库按关键词搜索作品。"""
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

    def iter_search_articles(
        self,
        keyword: str,
        max_pages: int = 5,
        page_size: int = PAGE_SIZE,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Iterable[Dict[str, Any]]:
        size = max(1, min(50, int(page_size or PAGE_SIZE)))
        for page_num in range(1, max(1, int(max_pages)) + 1):
            data = self.search_articles(
                keyword=keyword,
                page_num=page_num,
                page_size=size,
                start_date=start_date,
                end_date=end_date,
            ) or {}
            items = data.get("list") or data.get("works") or data.get("articles") or []
            if not items:
                return
            yield from items
            total = int(data.get("total") or 0)
            if len(items) < size or (total and page_num * size >= total):
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
):
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


__all__ = [
    "DouyinClient",
    "RedfoxError",
    "search_articles",
    "iter_search_articles",
    "parse_work_publish_time",
    "SEARCH_ARTICLES_PATH",
    "PAGE_SIZE",
]
