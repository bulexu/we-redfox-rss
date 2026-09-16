from  .base import Base,Column,String,Integer,DateTime,Text

FEATURED_MP_ID = "MP_WXS_FEATURED_ARTICLES"
FEATURED_MP_NAME = "精选文章"
FEATURED_MP_INTRO = "手动导入的公众号单篇文章会归类到这里。"

class Feed(Base):
    """订阅源（公众号 / 小红书共用）。

    ``id`` 前缀约定（隐式 platform/kind 标识）：
      * ``MP_WXS_`` + fakeid      : 公众号
      * ``MP_WXS_FEATURED_ARTICLES``: 精选文章（虚拟 feed）
      * ``XHS_KW_`` + keyword     : 小红书关键词订阅
      * ``XHS_U_``  + userId      : 小红书账号订阅

    平台/kind 字段可通过解析 ``id`` 前缀推断,  不单独持久化,
    后续接入抖音/B 站只需遵守前缀约定即可。
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