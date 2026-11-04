"""公众号 (WeChat) redfox 接口薄封装。

对应 SDK ``client.wechat.*`` 命名空间:
  * ``get_account_wide``              —— 获取公众号账号信息 (广域库)
  * ``search_users_wide``             —— 按关键词模糊搜索公众号
  * ``get_user_works_wide``           —— 单公众号作品列表 (广域库)
  * ``post /article/content``         —— 实时拉取公众号文章正文
                                       (不走 ``wechat`` 命名空间,  是
                                       SDK 的原始 ``post`` 入口)

模块对外通过 ``core.redfox.wechat`` 暴露模块级便捷函数,  内部按线程
懒缓存 ``_WechatClient``。  httpx.Client 非线程安全,  需要每个工作
线程独立持有,  缓存机制见 ``core.redfox.base._get_client_for``。
"""
from __future__ import annotations

import time
from datetime import datetime
from html import escape as html_escape
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 官方 SDK —— 即使未安装也能让本模块被 import (基类有 try/except 兜底,
# 这里直接取 from-import 用于运行时调用,  实际未安装时不会跑到这层)。
try:
    from redfox import RedFoxClient  # noqa: F401
    from redfox.exceptions import RedFoxAPIError  # noqa: F401
except ImportError:  # CI 环境兜底
    pass

from core.config import cfg  # noqa: F401  (保留以便子类 / 旧调用方有引用)

from ..base import (
    DEFAULT_BASE_URL,
    PAGE_SIZE,
    RedfoxClient,
    RedfoxError,
    SUCCESS_CODE,
    _get_client_for,
    as_int,
)
from ..schema import ArticleSchema
from ..validation import extract_items


# ---------------------------------------------------------------------------
# 模块级常量
# ---------------------------------------------------------------------------

ACCOUNT_INFO_PATH = "/story/api/gzh/data/accountInfo"  # 广域库
WORK_LIST_PATH = "/story/api/gzh/data/queryWorkList"   # 广域库
SEARCH_USER_PATH = "/story/api/gzh/data/searchUser"     # 广域库
ARTICLE_CONTENT_PATH = "/story/api/gzh/ability/temp/article/content"  # 实时拉取文章正文


# ---------------------------------------------------------------------------
# 文章正文响应解析工具
# ---------------------------------------------------------------------------
#
# Redfox 实时正文端点 ``ARTICLE_CONTENT_PATH`` 返回的 data 形如::
#
#     {
#         "articleContent": "<p>...</p>",   # HTML 字符串,可能不含图片
#         "imageUrls": [                       # 补充的图片 URL 列表
#             "https://mmbiz.qpic.cn/...?wx_fmt=png&from=appmsg",
#             ...
#         ]
#     }
#
# 这两个字段是互补的:  ``articleContent`` 给出排版后的正文 HTML,
# ``imageUrls`` 给出该篇文章的原图列表 (正文中未必能直接引用到)。
# 为保证图片不被丢失,  本模块统一在返回前把 ``imageUrls`` 拼成
# ``<img>`` 标签追加到 ``articleContent`` 末尾。
# ---------------------------------------------------------------------------


def _extract_article_payload(data: Any) -> Tuple[str, List[str]]:
    """从 Redfox 响应 data 中解出 ``(articleContent, imageUrls)``。

    容错:  任一字段缺失 / 类型不符都返回空值,  而不是抛异常。
    过滤掉 ``imageUrls`` 中的非字符串与空字符串元素。
    """
    if not isinstance(data, dict):
        return "", []

    content = data.get("articleContent", "") or ""
    if not isinstance(content, str):
        content = ""

    raw_urls = data.get("imageUrls", []) or []
    if not isinstance(raw_urls, list):
        return content, []

    image_urls: List[str] = []
    for item in raw_urls:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                image_urls.append(stripped)
    return content, image_urls


def _append_image_urls(content: str, image_urls: List[str]) -> str:
    """把 ``imageUrls`` 拼成 ``<img>`` 标签追加到正文末尾。

    每个 URL 一行,  自闭合标签;  URL 经 ``html.escape`` 防注入。
    原 content 没有换行结尾时补一个换行,  保证 ``<img>`` 不会粘在
    最后一个 HTML 元素后面影响渲染。
    """
    if not image_urls:
        return content

    img_tags = "\n".join(
        f'<img src="{html_escape(url, quote=True)}" />' for url in image_urls
    )
    sep = "" if content.endswith("\n") else "\n"
    return f"{content}{sep}{img_tags}"


# ---------------------------------------------------------------------------
# WeChat 平台客户端
# ---------------------------------------------------------------------------

class WechatClient(RedfoxClient):
    """公众号 redfox 接口客户端 (继承 ``RedfoxClient`` 共性层)。

    只添加公众号特有业务方法;  日志 / 异常 / 计时 / 线程缓存都复用基类。
    """

    # ------------------------------------------------------------------
    # 业务方法
    # ------------------------------------------------------------------

    def get_account_info(
        self,
        account: Optional[str] = None,
        wxId: Optional[str] = None,
        bizInfo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取公众号账号信息 (广域库)。

        三个入参至少传入一个。  优先级与 SDK 一致:  ``wxId > bizInfo > account``。
        """
        # SDK 严格要求至少传一个
        if not any([account, wxId, bizInfo]):
            raise RedfoxError("get_account_info: account/wxId/bizInfo 至少传一个")

        return self._sdk_call(
            endpoint=ACCOUNT_INFO_PATH,
            request_payload={
                "account": account or "",
                "wxId": wxId or "",
                "bizInfo": bizInfo or "",
            },
            sdk_op=lambda: self._sdk.wechat.get_account_wide(
                account=account,
                wx_id=wxId,
                biz_info=bizInfo,
            ),
        )

    def search_user(
        self,
        keyword: str = "",
        offset: int = 0,
    ) -> Dict[str, Any]:
        """按关键词模糊搜索公众号账号 (广域库)。

        与 ``get_account_info`` 的「精确查找单个公众号」不同:  本接口返回与
        关键词相关的多条结果,  适合订阅前的账号发现场景。

        Returns:
            解包后的 ``data`` 字段,  形如::

                {
                    "list": [
                        {
                            "account": "duhaoshu",
                            "accountName": "十点读书",
                            "avatarUrl": "...",
                            "bizInfo": "MjM5MDMyMzg2MA==",
                            "description": "...",
                            "qrcodeUrl": "...",
                            "verifyInfo": "...",
                            "wxId": "gh_5c7e8b7f586b",
                            "updateTime": "...",
                        },
                        ...
                    ],
                    "total": 941407,
                }
        """
        kw = (keyword or "").strip()
        if not kw:
            raise RedfoxError("searchUser: keyword 不能为空")
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0

        return self._sdk_call(
            endpoint=SEARCH_USER_PATH,
            request_payload={"keyword": kw, "offset": offset},
            sdk_op=lambda: self._sdk.wechat.search_users_wide(
                keyword=kw, offset=offset
            ),
        )

    def query_work_list(
        self,
        account: Optional[str] = None,
        wxId: Optional[str] = None,
        bizInfo: Optional[str] = None,
        offset: int = 0,
        sortType: str = "2",
    ) -> Dict[str, Any]:
        """获取公众号作品列表 (广域库)。

        Args:
            account/wxId/bizInfo: 公众号标识,  三选一。
            offset: 分页偏移量,  每页 +20。
            sortType: 排序方式,  "0" 默认 / "2" 最新 / "4" 最热。
        """
        if not any([account, wxId, bizInfo]):
            raise RedfoxError("query_work_list: account/wxId/bizInfo 至少传一个")
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0

        return self._sdk_call(
            endpoint=WORK_LIST_PATH,
            request_payload={
                "account": account or "",
                "wxId": wxId or "",
                "bizInfo": bizInfo or "",
                "offset": offset,
                "sortType": str(sortType),
            },
            sdk_op=lambda: self._sdk.wechat.get_user_works_wide(
                account=account,
                wx_id=wxId,
                biz_info=bizInfo,
                offset=offset,
                sort_type=str(sortType),
            ),
        )

    def iter_work_list(
        self,
        account: Optional[str] = None,
        wxId: Optional[str] = None,
        bizInfo: Optional[str] = None,
        max_pages: int = 1,
        sortType: str = "2",
        page_size: int = PAGE_SIZE,
    ) -> Iterable[ArticleSchema]:
        """按页迭代公众号作品列表。

        Args:
            max_pages: 最多拉取的页数 (每页 page_size 条)。
            page_size: 每页条数,  红狐接口固定为 20,  这里仅做防御性
                校验,  避免外部传错值时出现意外翻页。
        """
        if page_size <= 0:
            page_size = PAGE_SIZE
        for page in range(max(1, max_pages)):
            data = self.query_work_list(
                account=account,
                wxId=wxId,
                bizInfo=bizInfo,
                offset=page * page_size,
                sortType=sortType,
            )
            items = extract_items("wechat", data)
            if not items:
                return
            for raw in items:
                article = normalize_item(raw)
                if article is not None:
                    yield article

    def fetch_article_content(self, article_url: str) -> str:
        """通过红狐实时接口拉取公众号文章正文。

        对应端点:  ``POST /story/api/gzh/ability/temp/article/content``
        请求体:    ``{"articleUrl": "<mp.weixin.qq.com/s/...>"}``

        注意:
          * 该端点不在 SDK 已封装的 ``wechat`` 端点中。
          * 响应 ``code=200`` 而非 SDK 默认校验的 ``code=2000``,
            因此 SDK 会把它当业务错误抛出。  本方法捕获 ``RedFoxAPIError``,
            并对 ``exc.response.code == 200`` 这种特例按成功处理,
            不修改 SDK 本身 (SDK 是三方包,  改它风险大)。
          * 仍然走 SDK 的 ``post()`` -> ``request()`` 链路,  享受
            自动鉴权头 / 超时 / 5xx & 429 指数退避重试。
          * 响应 data 同时含 ``articleContent`` (正文 HTML) 和
            ``imageUrls`` (补充原图列表),  本方法会把后者拼成
            ``<img>`` 标签追加到正文末尾,  避免图片丢失。

        Returns:
            文章正文 HTML (已 strip;  ``imageUrls`` 已合并为 ``<img>``)。
            失败抛出 ``RedfoxError``。
        """
        if not article_url:
            raise RedfoxError("article_url 不能为空")
        url = str(article_url).strip()
        if not url:
            raise RedfoxError("article_url 不能为空")
        request_payload = {"articleUrl": url}

        started = time.time()
        feed_id = url[:128]  # 用于日志归因 (短前缀避免 Redis 体积过大)

        try:
            # 正常情况:  SDK 已解包 data (响应 code=2000 时走这里)
            data = self._sdk.post(ARTICLE_CONTENT_PATH, request_payload)
        except RedFoxAPIError as exc:
            # 特例:  本端点响应 code=200,  SDK 当成业务错误抛出,  但
            # exc.response 里有完整 payload,  这里手动解出当成功处理。
            from redfox.exceptions import RedFoxAuthError, RedFoxRateLimitError

            if isinstance(exc, (RedFoxAuthError, RedFoxRateLimitError)):
                # 基类已经处理过这两个,  这里只是 fallback;  正常情况下
                # 不会到这里 (基类的 _sdk_call 路径走不通是因为 fetch 用
                # 了 _sdk.post 而非子方法)。
                raise RedfoxError(f"Redfox 调用失败: {exc}") from exc

            response_payload = getattr(exc, "response", None) or {}
            if isinstance(response_payload, dict) and response_payload.get("code") == 200:
                data = response_payload.get("data") or {}
            else:
                latency = int((time.time() - started) * 1000)
                self._record_call(
                    endpoint=ARTICLE_CONTENT_PATH,
                    success=False,
                    latency_ms=latency,
                    feed_id=feed_id,
                    request=request_payload,
                    error_msg=str(exc),
                    code=int(getattr(exc, "code", 0) or 0),
                )
                raise RedfoxError(f"Redfox 业务错误: {exc}") from exc

        # articleContent + imageUrls 合并:  解析两个字段,  把图片拼成 <img>
        # 标签追加到正文末尾。
        content, image_urls = _extract_article_payload(data)
        content = _append_image_urls(content, image_urls)

        latency = int((time.time() - started) * 1000)
        self._record_call(
            endpoint=ARTICLE_CONTENT_PATH,
            success=True,
            latency_ms=latency,
            feed_id=feed_id,
            request=request_payload,
            code=200,
        )
        return content.strip()


# ---------------------------------------------------------------------------
# 模块级便捷函数 (保留旧用法,  避免改动调用方)
# ---------------------------------------------------------------------------

def _get_default_client() -> WechatClient:
    return _get_client_for("wechat", WechatClient)


def get_account_info(
    account: Optional[str] = None,
    wxId: Optional[str] = None,
    bizInfo: Optional[str] = None,
) -> Dict[str, Any]:
    return _get_default_client().get_account_info(
        account=account, wxId=wxId, bizInfo=bizInfo
    )


def search_user(keyword: str = "", offset: int = 0) -> Dict[str, Any]:
    return _get_default_client().search_user(keyword=keyword, offset=offset)


def query_work_list(
    account: Optional[str] = None,
    wxId: Optional[str] = None,
    bizInfo: Optional[str] = None,
    offset: int = 0,
    sortType: str = "2",
) -> Dict[str, Any]:
    return _get_default_client().query_work_list(
        account=account, wxId=wxId, bizInfo=bizInfo, offset=offset, sortType=sortType
    )


def iter_work_list(
    account: Optional[str] = None,
    wxId: Optional[str] = None,
    bizInfo: Optional[str] = None,
    max_pages: int = 1,
    sortType: str = "2",
    page_size: int = PAGE_SIZE,
) -> Iterable[ArticleSchema]:
    """模块级便捷函数:  按页迭代作品列表。"""
    return _get_default_client().iter_work_list(
        account=account,
        wxId=wxId,
        bizInfo=bizInfo,
        max_pages=max_pages,
        sortType=sortType,
        page_size=page_size,
    )


def fetch_article_content(article_url: str) -> str:
    """模块级便捷函数:  实时拉取公众号文章正文 (走 redfox SDK)。

    对应端点:  ``POST /story/api/gzh/ability/temp/article/content``
    """
    return _get_default_client().fetch_article_content(article_url)


__all__ = [
    "WechatClient",
    "RedfoxError",
    "get_account_info",
    "search_user",
    "query_work_list",
    "iter_work_list",
    "fetch_article_content",
    # 路径常量
    "ACCOUNT_INFO_PATH",
    "WORK_LIST_PATH",
    "SEARCH_USER_PATH",
    "ARTICLE_CONTENT_PATH",
    # 共用常量 (供旧 import 兼容)
    "DEFAULT_BASE_URL",
    "PAGE_SIZE",
    "SUCCESS_CODE",
]


# 公众号保留 FillBack 所需字段，与历史入库格式兼容。
def parse_publish_time(value: Any) -> int:
    """把 ``publishTime`` 转成 unix 秒；解析失败时返回当前时间。"""
    if not value:
        return int(time.time())
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return int(time.time())



def work_uuid_to_aid(work_uuid: str) -> str:
    """将 redfox ``workUuid`` 转为 ``aid``（去掉连字符保证兼容旧代码）。"""
    if not work_uuid:
        return ""
    return work_uuid.replace("-", "").replace(" ", "")



def normalize_fillback_item(raw: Dict[str, Any], Mps_id: str) -> Dict[str, Any]:
    """把 redfox 单条作品数据映射为旧 FillBack 期待的字段。"""
    article = normalize_item(raw)
    if article is None:
        return {}
    work_uuid = raw.get("workUuid") or ""
    aid = article.id
    publish_ts = article.publish_time
    return {
        "id": aid,
        "aid": aid,
        "appmsgid": aid,
        "mp_id": Mps_id,
        "title": article.title,
        "link": raw.get("workUrl") or "",
        "url": article.url,
        "cover": raw.get("coverUrl") or "",
        "pic_url": article.pic_url or "",
        "digest": raw.get("summary") or "",
        "description": raw.get("summary") or "",
        "update_time": publish_ts,
        "create_time": publish_ts,
        "publish_time": publish_ts,
        # 状态/类型
        "is_deleted": False,
        "copyright_stat": int(raw.get("isOriginal") or 0),
        "item_show_type": 0,
        "show_type": 0,
        "art_type": 0,
        "publish_type": 0,
        "publish_src": 0,
        "publish_status": "200",
        "service_type": 0,
        "pre_publish_status": 0,
        "original_check_type": 0,
        "in_profile": 1,
        "has_red_packet_cover": 0,
        # redfox 扩展字段
        "redfox_work_uuid": work_uuid,
        "read_count": raw.get("readCount"),
        "like_count": raw.get("likeCount"),
        "watch_count": raw.get("watchCount"),
        "comment_count": raw.get("commentCount"),
        "share_count": raw.get("shareCount"),
        "collect_count": raw.get("collectCount"),
        "original_author": raw.get("originalAuthor"),
        "source_url": raw.get("sourceUrl"),
        "order_num": raw.get("orderNum"),
    }


def normalize_item(raw: Dict[str, Any]) -> ArticleSchema | None:
    """公众号作品映射为统一模型；完整正文仍由后续正文采集补齐。"""
    work_id = work_uuid_to_aid(str(raw.get("workUuid") or ""))
    if not work_id:
        return None
    cover = str(raw.get("coverUrl") or "")
    summary = str(raw.get("summary") or "")
    return ArticleSchema(
        id=work_id, title=str(raw.get("title") or ""),
        description=summary, content=summary,
        url=str(raw.get("workUrl") or ""), pic_url=cover or None,
        publish_time=parse_publish_time(raw.get("publishTime")),
        author=str(raw.get("originalAuthor") or "") or None,
        image_urls=[cover] if cover else [], show_type=0,
        read_count=as_int(raw.get("readCount")), liked_count=as_int(raw.get("likeCount")),
        comments_count=as_int(raw.get("commentCount")),
        collected_count=as_int(raw.get("collectCount")), share_count=as_int(raw.get("shareCount")),
        extinfo={"platform": "wechat", "work_uuid": str(raw.get("workUuid") or ""),
                 "source_url": raw.get("sourceUrl"), "watch_count": as_int(raw.get("watchCount")),
                 "is_original": as_int(raw.get("isOriginal")), "order_num": raw.get("orderNum")},
    )
