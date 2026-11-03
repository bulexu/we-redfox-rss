"""飞书多维表（Lark Bitable）配置模型。

单表 ``LarkBitable``: 每个 Bitable 一行,  字段映射 + 关联 feed + 推送时间水印。

去重机制 (2024 重构):
  原先依赖 ``article_lark_pushes(article_id, bitable_id)`` 复合主键做幂等,
  现简化为 ``LarkBitable.last_pushed_at`` 作为 publish_time 水印:
    * ``last_pushed_at IS NULL`` (新表 / 未推过):  推送全部命中 feed_ids 的文章
    * ``last_pushed_at = X``:  仅推送 ``article.publish_time > X`` 的文章
  每次成功推送后把 ``last_pushed_at`` 更新为 ``max(原值, article.publish_time)``。
  失败的 ``article`` 不更新水印,  下个周期会重试(只要它仍是「比水印新」)。

表通过 SQLAlchemy ``Base.metadata.create_all()`` 自动建表,  与现有
``AccessKey`` / ``CascadeNode`` 一致。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import BigInteger
from sqlalchemy.exc import SQLAlchemyError

from .base import Base, Column, String, Integer, DateTime, Boolean, Text

ALLOWED_PUSH_INTERVAL_HOURS: tuple[int, ...] = (1, 2, 4, 6, 12, 24)


class LarkBitable(Base):
    """一个飞书多维表 (Bitable) 的推送配置。

    字段映射 ``field_mapping`` 存为 JSON 字符串,
    形如 ``{"title":"标题","url":"链接",...}``。

    关联 Feed id 列表 ``feed_ids`` (改名自 ``mp_ids``) 也是字符串,
    存 JSON 数组,  形如 ``["MP_WXS_abc","XHS_KW_美食","XHS_U_xxx"]``。
    """
    __tablename__ = "lark_bitables"

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    app_token = Column(String(255), nullable=False)
    table_id = Column(String(255), nullable=False)
    feed_ids = Column(Text, default="[]", nullable=False)
    field_mapping = Column(Text, default="{}", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    # 每张多维表独立的自动写入间隔。
    push_interval_hours = Column(Integer, default=6, nullable=False)
    last_pushed_at = Column(BigInteger, nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_feed_ids(self) -> List[str]:
        try:
            data = json.loads(self.feed_ids or "[]")
            return [str(x) for x in data] if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_feed_ids(self, ids: List[str]) -> None:
        cleaned = [str(x) for x in (ids or []) if x]
        self.feed_ids = json.dumps(cleaned, ensure_ascii=False)

    def get_field_mapping(self) -> Dict[str, str]:
        try:
            data = json.loads(self.field_mapping or "{}")
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_field_mapping(self, mapping: Dict[str, str]) -> None:
        if not mapping:
            self.field_mapping = "{}"
            return
        self.field_mapping = json.dumps(
            {str(k): str(v) for k, v in mapping.items()},
            ensure_ascii=False,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "app_token": self.app_token,
            "table_id": self.table_id,
            "feed_ids": self.get_feed_ids(),
            "field_mapping": self.get_field_mapping(),
            "enabled": bool(self.enabled),
            "push_interval_hours": int(self.push_interval_hours or 6),
            "last_pushed_at": self.last_pushed_at,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# LHS 白名单: 字段映射允许的左侧 key 集合 (来自 Article / Feed)。
# 不在此白名单内的 key 在保存时直接 400 拒绝, 避免配置错时静默推送。
ALLOWED_FIELD_KEYS: frozenset = frozenset({
    "id",
    "title",
    "url",
    "description",
    "content",
    "pic_url",
    "publish_time",
    "feed_id",
    "name",  # Feed.name (改名自 mp_name)
    "art_type",
})


def validate_field_mapping(mapping: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """校验字段映射, 返回规范化后的 ``{LHS:RHS}`` 字典。

    抛出 ``ValueError`` 表示配置不合法;  ``ValueError`` 内携带明确原因。
    """
    if mapping is None:
        return {}
    if not isinstance(mapping, dict):
        raise ValueError("field_mapping 必须是对象 (dict)")
    normalized: Dict[str, str] = {}
    for lhs, rhs in mapping.items():
        if lhs not in ALLOWED_FIELD_KEYS:
            raise ValueError(
                f"field_mapping 包含不支持的 key: {lhs!r};"
                f"允许的 key: {sorted(ALLOWED_FIELD_KEYS)}"
            )
        if not isinstance(rhs, str) or not rhs.strip():
            raise ValueError(f"field_mapping[{lhs}] 必须是非空字符串")
        if lhs in normalized:
            raise ValueError(f"field_mapping 存在重复 key: {lhs}")
        normalized[lhs] = rhs.strip()
    return normalized
