"""公众号 (WeChat) redfox 接口封装。

本目录仅承载公众号平台特定的方法 (账号信息 / 作品列表 / 实时正文),
SDK 初始化 / 调用日志 / 异常归一 / 线程缓存等共性层在
``core.redfox.base``。

公开入口 (模块级便捷函数):

    from core.redfox.wechat import (
        get_account_info,       # 公众号账号信息
        search_user,            # 关键词模糊搜索公众号
        query_work_list,        # 单公众号作品列表
        iter_work_list,         # 按页迭代作品列表
        fetch_article_content,  # 实时拉取公众号文章正文
    )

公众号正文仍由 ``driver.wxarticle`` 提供 (走 playwright),  本模块
只负责账号信息与作品列表的拉取 (走 redfox 广域库) 和实时正文补充
(走 redfox SDK 直接 ``post``)。
"""
from .client import (
    ACCOUNT_INFO_PATH,
    ARTICLE_CONTENT_PATH,
    DEFAULT_BASE_URL,
    PAGE_SIZE,
    SEARCH_USER_PATH,
    SUCCESS_CODE,
    WORK_LIST_PATH,
    RedfoxError,
    WechatClient,
    fetch_article_content,
    get_account_info,
    iter_work_list,
    query_work_list,
    search_user,
)

__all__ = [
    # 路径常量
    "ACCOUNT_INFO_PATH",
    "ARTICLE_CONTENT_PATH",
    "SEARCH_USER_PATH",
    "WORK_LIST_PATH",
    # 共用常量 (兼容旧 import)
    "DEFAULT_BASE_URL",
    "PAGE_SIZE",
    "SUCCESS_CODE",
    # 类 + 异常
    "WechatClient",
    "RedfoxError",
    # 函数
    "get_account_info",
    "search_user",
    "query_work_list",
    "iter_work_list",
    "fetch_article_content",
]
