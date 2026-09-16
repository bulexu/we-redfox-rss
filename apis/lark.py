"""飞书多维表 (Lark Bitable) 推送配置 API。

路由前缀: ``/api/v1/wx/lark/bitables`` (与其它 ``apis/*.py`` 保持一致)。
"""
from __future__ import annotations

import json
import time
import traceback
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from core.auth import get_current_user_or_ak
from core.config import cfg
from core.db import DB
from core.lark_client import LarkError, get_lark_client
from core.models.lark_bitable import (
    ALLOWED_FIELD_KEYS,
    LarkBitable,
    validate_field_mapping,
)
from core.print import print_error, print_info, print_warning
from .base import error_response, success_response

router = APIRouter(prefix="/lark", tags=["飞书多维表"])


# ===== Pydantic 请求模型 =====

class CreateBitableRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    app_token: str = Field(..., min_length=1, max_length=255)
    table_id: str = Field(..., min_length=1, max_length=255)
    # 改名自 mp_ids (commit 65aaffd1): 前端用 feed_ids 表达, 实际值是 Feed.id 列表
    feed_ids: List[str] = Field(default_factory=list)
    field_mapping: dict = Field(default_factory=dict)
    enabled: bool = True


class UpdateBitableRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    app_token: Optional[str] = Field(None, min_length=1, max_length=255)
    table_id: Optional[str] = Field(None, min_length=1, max_length=255)
    feed_ids: Optional[List[str]] = None
    field_mapping: Optional[dict] = None
    enabled: Optional[bool] = None


class ManualPushRequest(BaseModel):
    # 单条兼容字段:旧前端只传 article_id,保留向后兼容
    article_id: Optional[str] = Field(None, min_length=1)
    # 多选字段:新前端批量推送,优先于 article_id
    article_ids: Optional[List[str]] = Field(None)


# ===== Helper =====

def _bitable_to_dict(b: LarkBitable) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "app_token": b.app_token,
        "table_id": b.table_id,
        "feed_ids": b.get_feed_ids(),
        "field_mapping": b.get_field_mapping(),
        "enabled": bool(b.enabled),
        "last_pushed_at": b.last_pushed_at,
        "last_error": b.last_error,
        "last_error_at": b.last_error_at,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


# ===== CRUD =====

@router.get("/bitables", summary="列出飞书多维表配置")
async def list_bitables(
    enabled: Optional[bool] = Query(None),
    feed_id: Optional[str] = Query(None, description="按关联 feed_id 过滤"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        query = session.query(LarkBitable)
        if enabled is not None:
            query = query.filter(LarkBitable.enabled == enabled)
        all_rows = query.order_by(LarkBitable.created_at.desc()).all()
        if feed_id:
            all_rows = [b for b in all_rows if feed_id in b.get_feed_ids()]
        total = len(all_rows)
        items = [_bitable_to_dict(b) for b in all_rows[offset: offset + limit]]
        return success_response({
            "list": items,
            "total": total,
            "page": {"limit": limit, "offset": offset},
            "allowed_field_keys": sorted(ALLOWED_FIELD_KEYS),
        })
    except Exception as e:
        return error_response(code=500, message=f"查询多维表配置失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.post("/bitables", summary="创建飞书多维表配置")
async def create_bitable(
    req: CreateBitableRequest,
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        try:
            normalized_mapping = validate_field_mapping(req.field_mapping)
        except ValueError as ve:
            return error_response(code=400, message=str(ve))

        # 去重 feed_ids
        feed_ids = sorted({m.strip() for m in (req.feed_ids or []) if (m or "").strip()})
        bitable = LarkBitable(
            id=str(uuid.uuid4()),
            name=req.name.strip(),
            app_token=req.app_token.strip(),
            table_id=req.table_id.strip(),
            feed_ids=json.dumps(feed_ids, ensure_ascii=False),
            field_mapping=json.dumps(normalized_mapping, ensure_ascii=False),
            enabled=bool(req.enabled),
        )
        session.add(bitable)
        session.commit()
        session.refresh(bitable)
        return success_response(_bitable_to_dict(bitable), "创建成功")
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=f"创建失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.get("/bitables/{bitable_id}", summary="获取飞书多维表配置详情")
async def get_bitable(
    bitable_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        b = session.query(LarkBitable).filter(LarkBitable.id == bitable_id).first()
        if not b:
            return error_response(code=404, message="多维表配置不存在")
        return success_response(_bitable_to_dict(b))
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.put("/bitables/{bitable_id}", summary="更新飞书多维表配置")
async def update_bitable(
    bitable_id: str,
    req: UpdateBitableRequest,
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        b = session.query(LarkBitable).filter(LarkBitable.id == bitable_id).first()
        if not b:
            return error_response(code=404, message="多维表配置不存在")

        if req.name is not None:
            b.name = req.name.strip()
        if req.app_token is not None:
            b.app_token = req.app_token.strip()
        if req.table_id is not None:
            b.table_id = req.table_id.strip()
        if req.feed_ids is not None:
            feed_ids = sorted({m.strip() for m in req.feed_ids if (m or "").strip()})
            b.set_feed_ids(feed_ids)
        if req.field_mapping is not None:
            try:
                normalized = validate_field_mapping(req.field_mapping)
            except ValueError as ve:
                return error_response(code=400, message=str(ve))
            b.set_field_mapping(normalized)
        if req.enabled is not None:
            b.enabled = bool(req.enabled)

        session.commit()
        session.refresh(b)
        return success_response(_bitable_to_dict(b), "更新成功")
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=f"更新失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.delete("/bitables/{bitable_id}", summary="删除飞书多维表配置")
async def delete_bitable(
    bitable_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    session = DB.get_session()
    try:
        b = session.query(LarkBitable).filter(LarkBitable.id == bitable_id).first()
        if not b:
            return error_response(code=404, message="多维表配置不存在")
        session.delete(b)
        session.commit()
        return success_response(message="删除成功")
    except Exception as e:
        session.rollback()
        return error_response(code=500, message=f"删除失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


# ===== 验证可达 =====

@router.post("/bitables/{bitable_id}/test", summary="验证可达: 拉取字段定义")
async def test_bitable(
    bitable_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """通过 ``GET /bitable/v1/apps/{app_token}/tables/{table_id}/fields`` 验证:

    * LARK_APP_ID / LARK_APP_SECRET 是否能拿到 tenant_access_token
    * app_token / table_id 是否真实存在且有权限

    仅返回字段定义供 UI 提示, 不修改数据库。
    """
    session = DB.get_session()
    try:
        b = session.query(LarkBitable).filter(LarkBitable.id == bitable_id).first()
        if not b:
            return error_response(code=404, message="多维表配置不存在")
        client = get_lark_client()
        if client is None:
            return error_response(
                code=400,
                message="未配置 lark.app_id / lark.app_secret,"
                        "请检查 config.yaml 或环境变量 LARK_APP_ID / LARK_APP_SECRET",
            )
        try:
            fields = client.list_fields(b.app_token, b.table_id)
            return success_response({
                "ok": True,
                "field_count": len(fields),
                "fields": [
                    {"name": f.get("field_name"), "type": f.get("type"), "id": f.get("field_id")}
                    for f in fields
                ],
            }, "连通正常")
        except LarkError as le:
            return success_response({
                "ok": False,
                "code": getattr(le, "code", None),
                "message": str(le),
            }, "连通失败")
        except Exception as e:  # noqa: BLE001
            return success_response({"ok": False, "message": str(e)}, "连通失败")
    finally:
        try:
            session.close()
        except Exception:
            pass


# ===== 推送 =====

@router.post("/bitables/{bitable_id}/push", summary="手动推送文章到该 Bitable(支持单条 / 批量)")
async def manual_push(
    bitable_id: str,
    req: ManualPushRequest,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """手动把 article 推到指定 Bitable;  仍走 worker pool 异步执行。

    去重策略:  worker 内部按 ``LarkBitable.last_pushed_at`` 水印过滤
    (详见 ``core/lark_push._push_article_job``),  本接口不做额外去重判断,
    即使对同一 article 重复调也安全 —— 水印会保证后续 worker 跳过。

    支持两种入参:
      * ``article_id``:单条(旧前端兼容)
      * ``article_ids``:批量(新前端),优先于 ``article_id``
    批量模式下返回每条 article 的提交结果。
    """
    from core.models.article import Article as ArticleModel
    from core.lark_push import lark_maybe_push

    # 解析请求:article_ids 优先;缺失则回退到 article_id;都没有则报错
    targets: List[str] = []
    if req.article_ids:
        targets = [str(aid).strip() for aid in req.article_ids if str(aid).strip()]
    elif req.article_id:
        targets = [req.article_id.strip()]
    if not targets:
        return error_response(code=400, message="请传入 article_id 或 article_ids")

    # 批量上限保护,防止前端误传巨大列表拖垮 worker pool
    if len(targets) > 100:
        return error_response(code=400, message=f"单次最多推送 100 条,当前 {len(targets)} 条")

    # 去重保持顺序
    seen = set()
    deduped: List[str] = []
    for aid in targets:
        if aid and aid not in seen:
            seen.add(aid)
            deduped.append(aid)
    targets = deduped

    session = DB.get_session()
    try:
        b = session.query(LarkBitable).filter(LarkBitable.id == bitable_id).first()
        if not b:
            return error_response(code=404, message="多维表配置不存在")

        # 一次性查出所有目标文章,  校验存在性
        articles = (
            session.query(ArticleModel)
            .filter(ArticleModel.id.in_(targets))
            .all()
        )
        found_map = {a.id: a for a in articles}

        results = []
        for aid in targets:
            art = found_map.get(aid)
            if not art:
                results.append({
                    "article_id": aid,
                    "ok": False,
                    "error": "文章不存在",
                })
                continue
            try:
                lark_maybe_push(art.id)
                results.append({
                    "article_id": art.id,
                    "ok": True,
                })
            except Exception as e:  # noqa: BLE001
                # lark_maybe_push 自身已捕获异常吞掉,这里只是兜底
                results.append({
                    "article_id": art.id,
                    "ok": False,
                    "error": str(e),
                })

        submitted_count = sum(1 for r in results if r["ok"])
        return success_response({
            "submitted": submitted_count > 0,
            "bitable_id": b.id,
            "total": len(results),
            "submitted_count": submitted_count,
            "results": results,
            # 兼容旧前端:单条模式下平铺顶层字段
            "article_id": targets[0] if len(targets) == 1 else None,
        }, f"已提交 {submitted_count}/{len(results)} 条到 worker (异步执行)")
    except Exception as e:
        return error_response(code=500, message=f"提交推送失败: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@router.get("/status", summary="查询 lark 全局状态 (前端 banner 用)")
async def get_lark_status(
    current_user: dict = Depends(get_current_user_or_ak),
):
    """汇总诊断信息,帮助定位 "worker 没触发 / 没推出去" 的原因。

    返回字段:
      * ``enabled``         — 全局开关 ``cfg.lark.enabled`` 实际值
      * ``has_app_id``      — app_id 是否非空
      * ``has_app_secret``  — app_secret 是否非空
      * ``bitable_count``   — 数据库中 Bitable 行数 (含禁用)
      * ``enabled_count``   — enabled=True 的行数
      * ``token_ok``        — 是否能成功拿到 tenant_access_token (None 表示未尝试)
    """
    from core.lark_client import get_lark_client

    enabled = bool(cfg.get("lark.enabled", False))
    app_id = (cfg.get("lark.app_id") or "").strip()
    app_secret = (cfg.get("lark.app_secret") or "").strip()

    session = DB.get_session()
    try:
        bitable_count = session.query(LarkBitable).count()
        enabled_count = (
            session.query(LarkBitable)
            .filter(LarkBitable.enabled == True)  # noqa: E712
            .count()
        )
    finally:
        try:
            session.close()
        except Exception:
            pass

    token_ok: Optional[bool] = None
    if app_id and app_secret:
        try:
            client = get_lark_client()
            token_ok = bool(client and client.get_tenant_access_token())
        except Exception:  # noqa: BLE001
            token_ok = False

    issues: List[str] = []
    if not enabled:
        issues.append("全局未启用: 请在 config.yaml 设置 lark.enabled: True (或环境变量 LARK_ENABLED=True)")
    if not app_id:
        issues.append("缺少 lark.app_id (或环境变量 LARK_APP_ID)")
    if not app_secret:
        issues.append("缺少 lark.app_secret (或环境变量 LARK_APP_SECRET)")
    if enabled and app_id and app_secret and token_ok is False:
        issues.append("已配置但拉取 tenant_access_token 失败, 请检查 app_id / app_secret 是否有效")
    if enabled and bitable_count == 0:
        issues.append("还没有任何 Bitable 配置, 请新建一条")
    if enabled and enabled_count == 0:
        issues.append("Bitable 全部处于禁用状态, 请至少启用一条")

    return success_response({
        "enabled": enabled,
        "has_app_id": bool(app_id),
        "has_app_secret": bool(app_secret),
        "bitable_count": bitable_count,
        "enabled_count": enabled_count,
        "token_ok": token_ok,
        "issues": issues,
    })