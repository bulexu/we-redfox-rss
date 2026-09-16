"""小红书 (XHS) 集成包。

模块:
  * ``client``  — redfox SDK xiaohongshu 命名空间薄封装
  * ``sync``    — 单个 XHS feed 的增量同步 worker (do_job_xhs)
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
    PAGE_SIZE,
    RedfoxError,
    close_all_clients,
    get_user_works,
    iter_search_articles,
    iter_user_works,
    parse_work_publish_time,
    search_articles,
    search_users,
)
from .sync import (
    AUTO_DISABLE_ERROR_THRESHOLD,
    XHS_KW_PREFIX,
    XHS_U_PREFIX,
    build_feed_id,
    do_job_xhs,
)

__all__ = [
    "RedfoxError",
    "PAGE_SIZE",
    "XHS_KW_PREFIX",
    "XHS_U_PREFIX",
    "AUTO_DISABLE_ERROR_THRESHOLD",
    "search_articles",
    "iter_search_articles",
    "search_users",
    "get_user_works",
    "iter_user_works",
    "parse_work_publish_time",
    "build_feed_id",
    "do_job_xhs",
    "close_all_clients",
]
