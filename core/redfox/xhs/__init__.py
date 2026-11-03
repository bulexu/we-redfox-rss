"""小红书 (XHS) redfox 接口封装 + 同步 worker。

子模块:
  * ``client`` — XHS SDK 客户端 (``XhsClient``) + 业务方法 + 解析工具
  * ``sync``   — 单个 XHS feed 的增量同步 worker (``do_job_xhs``)
  * ``tests``  — 不依赖网络的本地集成测试 (``python -m core.redfox.xhs.tests``)

公开入口 (模块级便捷函数):

    from core.redfox.xhs import (
        do_job_xhs,             # 单 feed 增量同步
        build_feed_id,          # ("keyword"/"account", target) -> "XHS_KW_xxx" / "XHS_U_xxx"
        search_articles,        # 关键词搜索笔记
        search_users,           # 关键词搜索用户
        get_user_works,         # 单用户作品列表
    )

公共异常与常量 (``RedfoxError`` / ``XHS_KW_PREFIX`` / ``XHS_U_PREFIX``)
也通过本 ``__init__`` 重新导出。
"""
import sys
import types


def _ensure_redfox_stub() -> None:
    """redfox SDK 未安装时 (CI / 单元测试) 塞一个最小 stub。

    仅当真实包缺失时执行;  安装了官方 SDK 时原样使用,  不会覆盖。
    """
    if "redfox" in sys.modules:
        return
    try:
        import redfox  # noqa: F401
        return
    except ImportError:
        pass

    stub = types.ModuleType("redfox")
    stub.RedFoxClient = object  # type: ignore
    ex = types.ModuleType("redfox.exceptions")
    for n in (
        "RedFoxAPIError",
        "RedFoxAuthError",
        "RedFoxRateLimitError",
    ):
        setattr(ex, n, type(n, (Exception,), {}))
    sys.modules["redfox"] = stub
    sys.modules["redfox.exceptions"] = ex


_ensure_redfox_stub()

from .client import (
    GET_USER_WORKS_PATH,
    PAGE_SIZE,
    RedfoxError,
    SEARCH_ARTICLES_PATH,
    SEARCH_USERS_PATH,
    XhsClient,
    get_user_works,
    iter_search_articles,
    iter_user_works,
    parse_work_publish_time,
    search_articles,
    search_users,
)
from .sync import (
    AUTO_DISABLE_ERROR_THRESHOLD,
    DEFAULT_SORT_TYPE,
    XHS_KW_PREFIX,
    XHS_U_PREFIX,
    build_feed_id,
    do_job_xhs,
)

__all__ = [
    # 客户端
    "XhsClient",
    "RedfoxError",
    # 业务函数
    "do_job_xhs",
    "build_feed_id",
    "search_articles",
    "iter_search_articles",
    "search_users",
    "get_user_works",
    "iter_user_works",
    "parse_work_publish_time",
    # 平台常量
    "XHS_KW_PREFIX",
    "XHS_U_PREFIX",
    "DEFAULT_SORT_TYPE",
    "AUTO_DISABLE_ERROR_THRESHOLD",
    # 路径 / 通用常量
    "SEARCH_ARTICLES_PATH",
    "SEARCH_USERS_PATH",
    "GET_USER_WORKS_PATH",
    "PAGE_SIZE",
]
