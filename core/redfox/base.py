"""Redfox SDK 基础设施层。

本模块只做与"平台无关"的共性封装:

  * SDK 客户端构造 (``RedFoxClient``),  从 ``config.yaml`` 的
    ``redfox.api_key`` / ``redfox.base_url`` / ``redfox.timeout`` 取值,
    缺省回落到环境变量。
  * ``_sdk_call`` —— 统一的 SDK 调用入口,  负责计时 / 异常归一 /
    Redis 调用日志。
  * ``_record_call`` —— 调用日志写入。
  * ``_extract_feed_id`` —— 从请求参数里提取用于日志归因的标识。
  * ``_local_clients`` —— 按线程懒缓存客户端,  解决 ``httpx.Client``
    非线程安全的问题 (官方 SDK 内部持有 ``httpx.Client``)。

具体业务方法 (公众号 / 小红书 / 其它平台) 由子模块实现:

  * ``core.redfox.wechat.client`` —— 公众号 ``_WechatClient``
  * ``core.redfox.xhs.client``    —— 小红书 ``_XhsClient``

依赖:
  * 环境变量 ``REDFOX_API_KEY`` 必须存在 (也可在 ``config.yaml`` 的
    ``redfox.api_key`` 中显式配置,  但请勿硬编码)。
  * ``pip install redfox-python-sdk`` (已在 requirements.txt)。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, Optional

# 官方 SDK
try:
    from redfox import RedFoxClient
    from redfox.exceptions import (
        RedFoxAPIError,
        RedFoxAuthError,
        RedFoxRateLimitError,
    )
except ImportError:  # CI / 单元测试环境无 SDK 时使用 stub,  见下
    RedFoxClient = object  # type: ignore
    RedFoxAPIError = Exception  # type: ignore
    RedFoxAuthError = Exception  # type: ignore
    RedFoxRateLimitError = Exception  # type: ignore

from core.config import cfg
from core.print import print_error, print_warning
from core.redis_client import record_redfox_call


# ---------------------------------------------------------------------------
# 异常兼容: 保留旧名 ``RedfoxError`` 以便外部引用不受影响。
# ---------------------------------------------------------------------------
#
# SDK 抛出层级:  RedFoxAuthError / RedFoxRateLimitError / RedFoxAPIError。
# 我们把 SDK 的 APIError 当作通用 RedfoxError,  认证/限流错误也都视为
# RedfoxError 的子类 (实际上就是 APIError 的子类)。
RedfoxError = RedFoxAPIError


# ---------------------------------------------------------------------------
# 模块级常量 (与平台无关)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://redfox.hk"
SUCCESS_CODE = 2000
PAGE_SIZE = 20  # redfox 广域库 / 小红书 单页固定 20


# ---------------------------------------------------------------------------
# 基础客户端类
# ---------------------------------------------------------------------------

class RedfoxClient:
    """Redfox SDK 客户端基类。

    子类通过继承获得统一的:
      * SDK 构造 (``__init__``)
      * 调用日志 (``_record_call``)
      * 异常归一 + 计时 (``_sdk_call``)
      * 请求体归因字段提取 (``_extract_feed_id``)
      * ``close()`` 释放底层连接池

    子类只需添加平台特定业务方法。

    线程安全:  由于底层 ``RedFoxClient`` 持有 ``httpx.Client`` (非线程
    安全),  本类实例不应跨线程共享。  业务模块应通过各平台模块的
    ``get_default_client()`` 按线程懒缓存取得实例,  每个工作线程持有
    独立对象。
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

        # 官方 SDK 客户端 (自带重试 / 退避 / 结构化异常)
        self._sdk = RedFoxClient(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=int(self._timeout),
        )

    # ------------------------------------------------------------------
    # 资源释放
    # ------------------------------------------------------------------

    def close(self) -> None:
        """释放底层 ``httpx.Client`` 连接池。

        业务模块不应直接调用本方法;  应调用 ``close_all_clients()``
        在优雅退出时统一清空。
        """
        sdk_close = getattr(self._sdk, "close", None)
        if callable(sdk_close):
            try:
                sdk_close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 日志归一
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_feed_id(payload: Dict[str, Any]) -> str:
        """从请求体里提取用于日志归因的标识。

        按平台常见的字段名顺序遍历:  ``account`` (公众号) / ``wxId`` /
        ``bizInfo`` / ``keyword`` (小红书) / ``userId`` (XHS)。
        任一命中即返回 (字符串前 128 字符,  避免 Redis 体积过大)。

        子类可重写本方法扩展字段优先级。
        """
        if not isinstance(payload, dict):
            return ""
        for k in ("account", "wxId", "bizInfo", "keyword", "userId", "accountId"):
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
        """把每次调用写一条 Redis 统计日志,  失败仅打印告警,  不影响主流程。

        ``feed_id`` 内部仍以 ``mp_id`` 写入 Redis (与现有日志格式兼容),
        避免改 ``record_redfox_call`` 签名。
        """
        try:
            record_redfox_call(
                endpoint=endpoint,
                code=int(code or 0),
                success=success,
                latency_ms=int(latency_ms or 0),
                mp_id=feed_id,
                request=request or {},
                error_msg=error_msg,
                http_status=int(http_status or 0),
            )
        except Exception as exc:  # noqa: BLE001
            print_warning(f"记录 redfox 调用日志失败: {exc}")

    # ------------------------------------------------------------------
    # SDK 调用入口
    # ------------------------------------------------------------------

    def _sdk_call(
        self,
        endpoint: str,
        request_payload: Dict[str, Any],
        sdk_op: Callable[[], Any],
    ) -> Any:
        """统一的 SDK 调用入口:  计时 + 异常归一 + 日志记录。

        Args:
            endpoint: 仅用于日志归因的接口路径。
            request_payload: 请求体,  用于日志与 feed_id 提取。
            sdk_op: 无参 lambda,  在内部调用 ``self._sdk.xxx()``。

        Returns:
            SDK 返回的 ``data`` 字段 (dict)。  失败抛 ``RedfoxError``。
        """
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
            print_error(f"Redfox 调用异常: {e}")
            self._record_call(
                endpoint=endpoint,
                success=False,
                latency_ms=latency,
                feed_id=feed_id,
                request=request_payload,
                error_msg=f"exception: {e}",
            )
            raise RedfoxError(f"Redfox 调用异常: {e}") from e

        latency = int((time.time() - started) * 1000)
        # SDK 已自动校验 code=2000 并解包 data,  这里只是拿到 dict
        # 大多数端点返回 dict；TikTok 关键词视频搜索的 data 顶层则是 list。
        # 保留 SDK 解包后的两种合法结构，避免数组响应被误丢弃成空字典。
        data_dict = data if isinstance(data, (dict, list)) else {}
        self._record_call(
            endpoint=endpoint,
            success=True,
            latency_ms=latency,
            feed_id=feed_id,
            request=request_payload,
            code=SUCCESS_CODE,
        )
        return data_dict


# ---------------------------------------------------------------------------
# 线程局部客户端缓存 (按 platform key 隔离,  支持公众号 / 小红书 并存)
# ---------------------------------------------------------------------------
#
# 为什么不直接用 ``threading.local``:
#   * 多平台 (公众号 / 小红书) 共存时,  同一线程内可能持有 2 个不同类型
#     的客户端实例。  ``threading.local`` 只能存一个值,  而 dict key 模式
#     可以按 ``(thread_id, platform)`` 缓存任意多类型实例。
#
# 为什么不共享一个 ``httpx.Client``:
#   * ``RedFoxClient`` 内部持有 ``httpx.Client`` (非线程安全)。
#   * TaskQueue 后台线程把一次 MessageTask 的多个 feed 用
#     ``ThreadPoolExecutor`` 并发跑时,  若共用一个客户端,  多个线程
#     会同时调用 ``self._client.request``,  轻则请求/响应错乱,  重则
#     抛 ``RuntimeError`` / 数据损坏。

_clients_by_platform: dict[str, dict[int, RedfoxClient]] = {}
_clients_lock = threading.Lock()


def _get_client_for(
    platform: str,
    factory: Callable[[], RedfoxClient],
) -> RedfoxClient:
    """按 ``(platform, thread_id)`` 懒缓存并返回 ``RedfoxClient`` 实例。

    Args:
        platform: 命名空间键,  例如 ``"wechat"`` / ``"xhs"``。
        factory:  创建新实例的工厂函数 (每个平台子类传自己的 ``_XxxClient``)。

    Returns:
        当前线程对应的客户端实例 (新线程首次调用时创建)。
    """
    tid = threading.get_ident()
    bucket = _clients_by_platform.setdefault(platform, {})
    client = bucket.get(tid)
    if client is not None:
        return client
    with _clients_lock:
        # 双重检查:  可能在上锁过程中其它线程已为本 tid 创建
        client = bucket.get(tid)
        if client is None:
            client = factory()
            bucket[tid] = client
    return client


def close_all_clients() -> None:
    """关闭并清空所有缓存的客户端 (主要用于优雅退出 / 测试)。

    会调用每个客户端底层 ``httpx.Client.close()`` 释放连接池。
    """
    with _clients_lock:
        all_buckets = list(_clients_by_platform.values())
        _clients_by_platform.clear()
    for bucket in all_buckets:
        for client in list(bucket.values()):
            try:
                client.close()
            except Exception as exc:  # noqa: BLE001
                print_warning(f"关闭 redfox 客户端失败: {exc}")


__all__ = [
    "RedfoxClient",
    "RedfoxError",
    "DEFAULT_BASE_URL",
    "SUCCESS_CODE",
    "PAGE_SIZE",
    "_get_client_for",
    "close_all_clients",
]
