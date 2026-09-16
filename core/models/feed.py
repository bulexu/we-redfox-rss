from  .base import Base,Column,String,Integer,DateTime,Text

FEATURED_MP_ID = "MP_WXS_FEATURED_ARTICLES"
FEATURED_MP_NAME = "精选文章"
FEATURED_MP_INTRO = "手动导入的公众号单篇文章会归类到这里。"

# ===== platform 常量 =====
# 平台枚举 (字符串)。  新平台接入只需在这里加 (PLATFORM_* 常量 + 前缀识别),
# 不必改业务代码。
PLATFORM_MP = "mp"
PLATFORM_XHS = "xhs"
PLATFORM_UNKNOWN = "unknown"

# 各平台 id 前缀,  用于从现有 id 反推 platform。
# 注意:  这些是 *已知的* 前缀,  infer_platform_from_id 对未知前缀返回 "unknown",
# 不会抛异常,  方便后续接入新平台时老数据可以渐进迁移。
_MP_PREFIXES = ("MP_WXS_",)
_XHS_PREFIXES = ("XHS_KW_", "XHS_U_")


def infer_platform_from_id(feed_id: str) -> str:
    """根据 ``feed.id`` 前缀推断 platform。

    前缀约定:
      * ``MP_WXS_*``                  → ``"mp"``
      * ``XHS_KW_*`` / ``XHS_U_*``    → ``"xhs"``
      * 其它 / 空                     → ``"unknown"`` (不抛异常)
    """
    if not feed_id:
        return PLATFORM_UNKNOWN
    if feed_id.startswith(_MP_PREFIXES):
        return PLATFORM_MP
    if feed_id.startswith(_XHS_PREFIXES):
        return PLATFORM_XHS
    return PLATFORM_UNKNOWN


class Feed(Base):
    """订阅源（公众号 / 小红书共用）。

    ``id`` 前缀约定:
      * ``MP_WXS_`` + fakeid         : 公众号
      * ``MP_WXS_FEATURED_ARTICLES``: 精选文章（虚拟 feed, 也是 platform=mp）
      * ``XHS_KW_`` + uuid          : 小红书关键词订阅
      * ``XHS_U_``  + userId        : 小红书账号订阅

    ``platform`` 字段持久化平台信息,  业务侧可用
    :func:`infer_platform_from_id` 或直接读 ``platform`` 字段。
    旧数据 ``platform`` 为 NULL 时,  调用方应用 ``infer_platform_from_id`` 兜底。
    """
    from_attributes = True
    __tablename__ = 'feeds'
    id = Column(String(255), primary_key=True)
    name = Column(String(255))  # 显示名（公众号 mp_name / 小红书 keyword 或 nickname）
    cover = Column(String(255))  # 头像 / 关键词占位封面
    intro = Column(String(255))  # 简介
    status = Column(Integer, index=True)  # 状态（0=禁用, 1=启用; 连续失败超阈值会自动切 0）
    # 时间字段
    sync_time = Column(Integer)  # 上次同步时间戳（epoch sec）
    update_time = Column(Integer)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    faker_id = Column(String(255))  # 公众号 fakeid（仅公众号使用）
    # 增量同步字段（多平台通用）
    last_publish_time = Column(Integer, index=True)  # 上次抓到的最大 publish_time（epoch sec）
    last_cursor = Column(String(255))  # 平台特定游标（小红书: workId）
    max_fetch_count = Column(Integer, default=20)  # 每任务最大抓取条数
    refresh_interval_hours = Column(Integer, default=6)  # 刷新间隔（小时）
    # 错误追踪
    error_count = Column(Integer, default=0)  # 连续失败次数（成功一次清零）
    last_error = Column(Text)  # 最近一次错误信息
    last_error_at = Column(Integer)  # 最近错误时间（epoch sec）
    # 多平台通用：原始检索值（小红书 keyword 文本 / 账号 userId；公众号目前未使用）
    # 引入此字段后，XHS_KW_* 的 id 改为 uuid, target 单独保存以避免中文/特殊字符进入主键。
    target = Column(String(500))
    # 平台枚举 ("mp" / "xhs" / "unknown")。  业务过滤用 platform 列,  不再依赖 id 前缀扫描,
    # 索引后 list 接口性能更好, 也避免 id 改名 (XHS_KW_* → uuid) 时影响旧 like 过滤逻辑。
    platform = Column(String(16), index=True, default=PLATFORM_UNKNOWN)