"""Redfox 各平台返回字段一致性校验。

背景: redfox 不同平台的返回字段命名差异很大 (``workId`` / ``bvId`` /
``videoId`` / ``tweetId`` ...), 且接口升级时可能悄悄改名。 之前小红书的
企业字段 (``noteDesc`` 等) 就是手写后才被发现与真实响应不一致。

本模块提供两层校验:

1. **原始响应层** —— ``extract_items`` 统一从响应里取列表, 取不到时打印
   实际顶层字段;  ``validate_raw`` 检查平台依赖的核心字段是否存在。
2. **规范化结果层** —— ``validate_normalized`` 检查所有平台映射后的 dict
   是否包含同一套 ``Article`` 字段且类型正确 (``image_urls`` / ``extinfo``
   必须是合法 JSON)。

校验只打印告警, 不抛异常 / 不阻断采集; 同一平台同一问题只告警一次,
避免日志刷屏。 测试可用 ``reset_reports`` / ``get_reports`` 检查。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.print import print_warning


# ---------------------------------------------------------------------------
# 规范化字段契约 (所有平台 ``_normalize_*`` 必须返回同一套 key)
# ---------------------------------------------------------------------------

NORMALIZED_FIELDS: Tuple[str, ...] = (
    "id", "title", "content", "description", "pic_url", "url",
    "publish_time", "author", "author_id", "image_urls", "extinfo",
    "liked_count", "comments_count", "collected_count", "read_count",
    "share_count",
)

# 每个字段允许的类型 (``none`` 表示允许 None)
NORMALIZED_TYPES: Dict[str, Tuple[str, ...]] = {
    "id": ("str",),
    "title": ("str",),
    "content": ("str",),
    "description": ("str",),
    "pic_url": ("str", "none"),
    "url": ("str",),
    "publish_time": ("int",),
    "author": ("str", "none"),
    "author_id": ("str", "none"),
    "image_urls": ("str",),
    "extinfo": ("str",),
    "liked_count": ("int",),
    "comments_count": ("int",),
    "collected_count": ("int",),
    "read_count": ("int",),
    "share_count": ("int",),
}

# JSON 字段 → 解析后应有的类型
JSON_FIELDS: Dict[str, type] = {"image_urls": list, "extinfo": dict}


# ---------------------------------------------------------------------------
# 原始响应字段契约 (按平台声明依赖的核心字段)
# ---------------------------------------------------------------------------

# 只列"缺了会影响标题/正文/时间/作者"的字段; 互动数缺失是平台常态
# (如 YouTube 搜索不返回点赞/评论), 不在此处报警。
RAW_REQUIRED_FIELDS: Dict[str, Tuple[str, ...]] = {
    "xhs": (
        "workId", "workTitle", "workDesc", "coverUrl", "workUrl",
        "workPublishTime", "accountNickname", "accountUserid",
    ),
    "bilibili": (
        "bvId", "title", "description", "picUrl", "created",
        "author", "authorId",
    ),
    "douyin": (
        "videoId", "content", "coverUrl", "opusUrl", "publishTime",
        "authorName", "authorUid",
    ),
    "tiktok": (
        "workId", "content", "publishTime", "shareLink",
        "authorData", "statsData", "videoData",
    ),
    "youtube": (
        "videoId", "title", "description", "publishedTime",
        "channelId", "author",
    ),
    "instagram": (
        "mediaId", "code", "captionText", "imageUrl", "takenAt", "user",
    ),
    "x": (
        "tweetId", "text", "createdAt", "user", "username",
    ),
}

# 响应里承载列表的字段名候选 (按优先级)
LIST_KEYS: Dict[str, Tuple[str, ...]] = {
    "xhs": ("list", "notes"),
    "bilibili": ("workList",),
    "douyin": ("list", "works", "articles"),
    "tiktok": ("list", "items", "videos"),
    "youtube": ("videos", "items", "list"),
    "instagram": ("items", "posts", "list"),
    "x": ("tweets", "list", "items"),
    "wechat": ("list",),
}


# ---------------------------------------------------------------------------
# 校验结果统计 (供测试 / 排查使用)
# ---------------------------------------------------------------------------

_reports: Dict[str, Dict[str, Any]] = {}
_seen: set[Tuple[str, str, str]] = set()


def reset_reports() -> None:
    """清空告警去重状态与统计 (测试用)。"""
    _reports.clear()
    _seen.clear()


def get_reports() -> Dict[str, Dict[str, Any]]:
    """返回 ``{platform: {"items": n, "issues": n, "messages": [...]}}``。"""
    return _reports


def _report(platform: str, stage: str, issues: Sequence[str]) -> None:
    if not issues:
        return
    bucket = _reports.setdefault(
        platform, {"items": 0, "issues": 0, "messages": []},
    )
    bucket["items"] += 1
    bucket["issues"] += len(issues)
    unique = sorted(set(issues))
    for message in unique:
        key = (platform, stage, message)
        if key in _seen:
            continue
        _seen.add(key)
        bucket["messages"].append(message)
        print_warning(f"[redfox:{platform}] 字段校验: {message}")


# ---------------------------------------------------------------------------
# 原始响应层
# ---------------------------------------------------------------------------

def extract_items(
    platform: str,
    data: Any,
    keys: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """从响应 ``data`` 中取出作品列表。

    * ``data`` 本身是 list 时直接返回 (TikTok 搜索就是这种结构)。
    * dict 时按 ``keys`` / ``LIST_KEYS[platform]`` 依次查找第一个 list。
    * 都找不到且 data 非空时打印实际顶层字段, 方便第一时间发现接口改名。
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        _report(platform, "raw", [f"响应 data 类型为 {type(data).__name__},  期望 dict/list"])
        return []

    candidates = tuple(keys) if keys is not None else LIST_KEYS.get(platform, ())
    for key in candidates:
        items = data.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    if data:
        _report(
            platform,
            "raw",
            [f"未找到列表字段 {list(candidates)},  实际顶层字段 {sorted(data)}"],
        )
    return []


def validate_raw(platform: str, raw: Dict[str, Any]) -> List[str]:
    """检查单条原始数据是否包含平台核心字段。

    只判断字段是否存在 (``None`` 视为缺失),  空字符串不报警 ——
    无正文 / 无封面的作品是合法数据。
    """
    if not isinstance(raw, dict):
        return [f"原始数据不是 dict: {type(raw).__name__}"]
    required = RAW_REQUIRED_FIELDS.get(platform, ())
    return [
        f"缺少原始字段 {field}"
        for field in required
        if field not in raw or raw.get(field) is None
    ]


# ---------------------------------------------------------------------------
# 规范化结果层
# ---------------------------------------------------------------------------

def _type_ok(value: Any, expected: Sequence[str]) -> bool:
    for name in expected:
        if name == "none" and value is None:
            return True
        if name == "str" and isinstance(value, str):
            return True
        if name == "int" and isinstance(value, int) and not isinstance(value, bool):
            return True
    return False


def validate_normalized(platform: str, item: Dict[str, Any]) -> List[str]:
    """检查映射后的 dict 是否符合统一字段契约。"""
    if not isinstance(item, dict):
        return [f"规范化结果不是 dict: {type(item).__name__}"]

    issues: List[str] = []
    for field in NORMALIZED_FIELDS:
        if field not in item:
            issues.append(f"缺少规范字段 {field}")
            continue
        expected = NORMALIZED_TYPES[field]
        if not _type_ok(item[field], expected):
            issues.append(
                f"规范字段 {field} 类型错误: {type(item[field]).__name__} "
                f"(期望 {'/'.join(expected)})"
            )

    for field, json_type in JSON_FIELDS.items():
        value = item.get(field)
        if not isinstance(value, str):
            continue
        try:
            parsed = json.loads(value)
        except ValueError:
            issues.append(f"规范字段 {field} 不是合法 JSON")
            continue
        if not isinstance(parsed, json_type):
            issues.append(
                f"规范字段 {field} JSON 类型错误: "
                f"{type(parsed).__name__} (期望 {json_type.__name__})"
            )
    return issues


def checked_item(
    platform: str,
    raw: Dict[str, Any],
    item: Dict[str, Any],
) -> Dict[str, Any]:
    """在 ``_normalize_*`` 返回前统一跑一遍原始 + 规范字段校验。

    只打印告警并原样返回 ``item``,  不影响采集流程。
    """
    issues = validate_raw(platform, raw) + validate_normalized(platform, item)
    _report(platform, "item", issues)
    return item


__all__ = [
    "NORMALIZED_FIELDS",
    "NORMALIZED_TYPES",
    "JSON_FIELDS",
    "RAW_REQUIRED_FIELDS",
    "LIST_KEYS",
    "extract_items",
    "validate_raw",
    "validate_normalized",
    "checked_item",
    "get_reports",
    "reset_reports",
]
