"""Redfox 客户端交付给同步层的统一作品模型。"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ArticleSchema(BaseModel):
    """平台无关作品；图片和扩展信息在入库边界才序列化为 JSON。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = ""
    content: str = ""
    description: str = ""
    pic_url: Optional[str] = None
    url: str = ""
    publish_time: int = 0  # Unix 秒
    author: Optional[str] = None
    author_id: Optional[str] = None
    image_urls: list[str] = Field(default_factory=list)
    extinfo: Dict[str, Any] = Field(default_factory=dict)
    show_type: int = 5  # 0=图文，5=视频
    liked_count: int = 0
    comments_count: int = 0
    collected_count: int = 0
    read_count: int = 0
    share_count: int = 0

    @classmethod
    def from_record(cls, item: Dict[str, Any]) -> "ArticleSchema":
        """接纳平台映射结果；兼容现有映射中的 JSON 字符串。"""
        values = dict(item)
        for name in ("image_urls", "extinfo"):
            if isinstance(values.get(name), str):
                values[name] = json.loads(values[name])
        return cls.model_validate(values)

    def to_record(self) -> Dict[str, Any]:
        """转换为现有 Article 入库和字幕处理使用的字段字典。"""
        record = self.model_dump()
        record["image_urls"] = json.dumps(self.image_urls, ensure_ascii=False)
        record["extinfo"] = json.dumps(self.extinfo, ensure_ascii=False)
        return record
