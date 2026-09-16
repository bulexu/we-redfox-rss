"""Redfox 数据接口封装（基于官方 redfox-python-sdk）

本目录按平台拆分:
  * ``base``    —— 共性层:  SDK 构造 / 调用日志 / 异常归一 / 线程缓存
  * ``wechat``  —— 公众号平台特定方法 (账号信息 / 作品列表 / 实时正文)
  * ``xhs``     —— 小红书平台特定方法 + 同步 worker

公众号正文仍由 ``driver.wxarticle`` 提供 (走 playwright),  本模块
只负责账号信息与作品列表的拉取 (走 redfox 广域库) 和实时正文补充。

顶层 (本 ``__init__``) 同时保留公众号模块级便捷函数,  以便旧调用方
无感知切换::

    from core.redfox import (
        get_account_info,        # 公众号账号信息
        search_user,             # 关键词搜索公众号
        query_work_list,         # 单公众号作品列表
        iter_work_list,          # 按页迭代作品列表
        fetch_article_content,   # 实时公众号正文
        RedfoxError,
        DEFAULT_BASE_URL,
        PAGE_SIZE,
        SUCCESS_CODE,
        close_all_clients,
    )

小红书入口请走 ``core.redfox.xhs``::

    from core.redfox.xhs import (
        do_job_xhs,
        build_feed_id,
        search_articles,
        search_users,
    )
"""
from .base import (
    DEFAULT_BASE_URL,
    PAGE_SIZE,
    RedfoxClient,
    RedfoxError,
    SUCCESS_CODE,
    close_all_clients,
)
from .wechat import (
    fetch_article_content,
    get_account_info,
    iter_work_list,
    query_work_list,
    search_user,
)

__all__ = [
    # 基础类 / 异常 / 常量
    "RedfoxClient",
    "RedfoxError",
    "DEFAULT_BASE_URL",
    "PAGE_SIZE",
    "SUCCESS_CODE",
    "close_all_clients",
    # 公众号便捷函数 (兼容旧 import)
    "get_account_info",
    "search_user",
    "query_work_list",
    "iter_work_list",
    "fetch_article_content",
    # 子包 (供 ``from core.redfox.xhs import ...``)
    "wechat",
    "xhs",
]
