from pydantic import Json
from sqlalchemy import BigInteger

from  .base import Base,Column,String,Integer,DateTime,Text,DATA_STATUS
class ArticleBase(Base):
    """内容基础模型（公众号 + 小红书 + 抖音共用）"""
    from_attributes = True
    __tablename__ = 'articles'
    # 文章基础属性
    id = Column(String(255), primary_key=True)  # 文章全局唯一ID（公众号: App Message ID / 小红书: workId）
    feed_id = Column(String(255), index=True)  # 订阅源ID（公众号: MP_WXS_xxx / 小红书: XHS_KW_xxx, XHS_U_xxx）
    title = Column(String(1000))  # 文章标题
    # Instagram CDN 的带签名图片 URL 经常超过 500 字符，必须完整保存，
    # 否则截掉末尾的签名参数后图片会全部失效。
    pic_url = Column(Text)  # 封面图片URL地址（小红书: coverUrl）
    url=Column(String(500))  # 文章的永久链接（URL），用户点击阅读的地址（小红书: workUrl）
    description=Column(Text)  # 文章摘要（对应 digest / 小红书 RSS 摘要）
    extinfo = Column(Text)  # 扩展信息
    status = Column(Integer,default=1,index=True)  # 文章状态：删除状态标记（对应 is_deleted，false 表示未删除）
    publish_time = Column(Integer,index=True)  # 文章发布时间（对应 update_time，Unix时间戳格式，单位：秒）
    create_time = Column(Integer,index=True)  # 文章创建时间（Unix时间戳格式）
    publish_type = Column(Integer,index=True)  # 发布类型
    publish_src = Column(Integer,index=True)  # 发布来源
    publish_status = Column(Text,index=True)  # 发布状态
    art_type = Column(Integer,index=True)  # 内容类型(1=图文/视频/音频, 9=贴图等)
    show_type = Column(Integer,index=True)  # 展示类型(0=图文, 5=视频, 7=音频, 10=贴图)
    publish_info=Column(Text)  # 发布信息（JSON格式，包含文章的详细发布数据，如阅读数、点赞数等）
    # 状态与类型标识
    original_check_type = Column(Integer,index=True)  # 原创检测类型
    in_profile = Column(Integer,index=True)  # 是否在主页展示
    pre_publish_status = Column(Integer,index=True)  # 预发布状态
    service_type = Column(Integer,index=True)  # 服务类型
    item_show_type = Column(Integer,index=True)  # 展示类型（对应 item_show_type，0通常为普通图文，10可能为特定的无图或特殊样式）
    copyright_stat = Column(Integer,index=True)  # 原创状态（0通常表示非原创，1表示原创）
    has_red_packet_cover = Column(Integer,index=True)  # 封面是否有红包挂件（0为无）
    # 小红书扩展字段
    author = Column(String(255))  # 作者名（小红书 accountNickname）
    author_id = Column(String(255), index=True)  # 作者 ID（小红书 accountUserid，便于按作者聚合）
    image_urls = Column(Text)  # 图片 URL 列表（JSON 字符串；当前存 [coverUrl]，后续接入 get_work 补全）
    liked_count = Column(Integer, default=0)  # 点赞数
    comments_count = Column(Integer, default=0)  # 评论数
    collected_count = Column(Integer, default=0)  # 收藏数
    read_count = Column(Integer, default=0)  # 阅读数
    share_count = Column(Integer, default=0)  # 分享数
    # 系统字段
    created_at = Column(DateTime)  # 记录创建时间
    updated_at = Column(BigInteger)  # 记录更新时间
    updated_at_millis = Column(BigInteger,index=True)  # 记录更新时间（毫秒）
    is_export = Column(Integer)  # 是否已导出
    is_read = Column(Integer, default=0)  # 是否已读
    is_favorite = Column(Integer, default=0)  # 是否收藏
    fix_fail_count = Column(Integer, default=0)  # 修正内容失败次数
    web_fetch_fail_count = Column(Integer, default=0)  # web 抓取失败次数（>=3 时降级走 redfox）
    has_content = Column(Integer, default=0, index=True)  # 是否有正文内容（0=无，1=有），用于加速查询
class Article(ArticleBase):
    content = Column(Text)
    content_html = Column(Text)

    def to_dict(self):
        """将Article对象转换为字典"""
        return {
            # 文章基础属性
            'id': self.id,
            'feed_id': self.feed_id,
            'title': self.title,
            'pic_url': self.pic_url,
            'url': self.url,
            'description': self.description,
            'extinfo': self.extinfo,
            'status': self.status,
            'publish_time': self.publish_time,
            'create_time': self.create_time,
            'publish_type': self.publish_type,
            'publish_src': self.publish_src,
            'publish_status': self.publish_status,
            # 状态与类型标识
            'original_check_type': self.original_check_type,
            'in_profile': self.in_profile,
            'pre_publish_status': self.pre_publish_status,
            'service_type': self.service_type,
            'show_type': self.show_type,
            'item_show_type': self.item_show_type,
            'copyright_stat': self.copyright_stat,
            'has_red_packet_cover': self.has_red_packet_cover,
            'publish_info': self.publish_info,
            # 小红书扩展字段
            'author': self.author,
            'author_id': self.author_id,
            'image_urls': self.image_urls,
            'liked_count': self.liked_count,
            'comments_count': self.comments_count,
            'collected_count': self.collected_count,
            'read_count': self.read_count,
            'share_count': self.share_count,
            # 内容
            'content': self.content,
            'content_html': self.content_html,
            # 系统字段
            'created_at': self.created_at.isoformat() if self.created_at and hasattr(self.created_at, "isoformat") else self.created_at, #type: ignore
            'updated_at': self.updated_at.isoformat() if self.updated_at and hasattr(self.updated_at, "isoformat") else self.updated_at, #type: ignore
            'updated_at_millis': self.updated_at_millis,
            'is_export': self.is_export,
            'is_read': self.is_read,
            'is_favorite': self.is_favorite,
            'fix_fail_count': self.fix_fail_count,
            'web_fetch_fail_count': self.web_fetch_fail_count,
            'has_content': self.has_content
        }
