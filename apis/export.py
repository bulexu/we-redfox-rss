
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File,Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from core.auth import get_current_user_or_ak
from core.db import DB
from core.wx import search_Biz
from core.models.feed import Feed, PLATFORM_BILI, PLATFORM_DY, PLATFORM_INSTAGRAM, PLATFORM_MP, PLATFORM_TIKTOK, PLATFORM_X, PLATFORM_XHS, PLATFORM_YOUTUBE, infer_platform_from_id
from core.redfox.xhs.sync import XHS_KW_PREFIX, XHS_U_PREFIX
from core.redfox.douyin.sync import DY_KW_PREFIX
from core.redfox.bilibili.sync import BILI_KW_PREFIX
from core.redfox.x.sync import X_KW_PREFIX
from core.redfox.tiktok.sync import TIKTOK_KW_PREFIX
from core.redfox.youtube.sync import YOUTUBE_KW_PREFIX
from core.redfox.instagram.sync import INSTAGRAM_KW_PREFIX
from .base import success_response, error_response
from datetime import datetime
from core.config import cfg
from core.res import save_avatar_locally
import csv
import io
import os
import uuid
router = APIRouter(prefix=f"/export", tags=["导入/导出"])


# 统一 Excel 导出 sheet 配置: (sheet 名, 中文表头, 行生成器)
# 改这里就能扩展新平台 / 调表头,无需改主体逻辑。
_EXCEL_SHEETS = [
    (
        "公众号",
        ["id", "公众号名称", "封面图", "简介", "状态", "创建时间", "faker_id"],
        lambda f: [
            f.id, f.name, f.cover, f.intro, f.status,
            f.created_at.isoformat() if f.created_at else "",
            f.faker_id or "",
        ],
    ),
    (
        "小红书-关键词",
        ["id", "关键词(target)", "显示名", "封面", "简介", "状态", "创建时间"],
        lambda f: [
            f.id, getattr(f, "target", "") or "", f.name or "",
            f.cover or "", f.intro or "", f.status,
            f.created_at.isoformat() if f.created_at else "",
        ],
    ),
    (
        "小红书-账号",
        ["id", "账号ID(target)", "昵称", "头像", "简介", "状态", "创建时间"],
        lambda f: [
            f.id, getattr(f, "target", "") or "", f.name or "",
            f.cover or "", f.intro or "", f.status,
            f.created_at.isoformat() if f.created_at else "",
        ],
    ),
    (
        "抖音-关键词",
        ["id", "关键词(target)", "显示名", "封面", "简介", "状态", "创建时间"],
        lambda f: [
            f.id, getattr(f, "target", "") or "", f.name or "",
            f.cover or "", f.intro or "", f.status,
            f.created_at.isoformat() if f.created_at else "",
        ],
    ),
    (
        "B站-关键词",
        ["id", "关键词(target)", "显示名", "封面", "简介", "状态", "创建时间"],
        lambda f: [
            f.id, getattr(f, "target", "") or "", f.name or "",
            f.cover or "", f.intro or "", f.status,
            f.created_at.isoformat() if f.created_at else "",
        ],
    ),
    (
        "X-关键词",
        ["id", "关键词(target)", "显示名", "封面", "简介", "状态", "创建时间"],
        lambda f: [
            f.id, getattr(f, "target", "") or "", f.name or "",
            f.cover or "", f.intro or "", f.status,
            f.created_at.isoformat() if f.created_at else "",
        ],
    ),
    (
        "TikTok-关键词",
        ["id", "关键词(target)", "显示名", "封面", "简介", "状态", "创建时间"],
        lambda f: [f.id, getattr(f, "target", "") or "", f.name or "", f.cover or "", f.intro or "", f.status, f.created_at.isoformat() if f.created_at else ""],
    ),
    (
        "YouTube-关键词",
        ["id", "关键词(target)", "显示名", "封面", "简介", "状态", "创建时间"],
        lambda f: [f.id, getattr(f, "target", "") or "", f.name or "", f.cover or "", f.intro or "", f.status, f.created_at.isoformat() if f.created_at else ""],
    ),
    (
        "Instagram-关键词",
        ["id", "关键词(target)", "显示名", "封面", "简介", "状态", "创建时间"],
        lambda f: [f.id, getattr(f, "target", "") or "", f.name or "", f.cover or "", f.intro or "", f.status, f.created_at.isoformat() if f.created_at else ""],
    ),
]


def _classify_feed_for_export(feed: Feed) -> str | None:
    """把 feed 分类到对应 Excel sheet, 不属于任何已知平台返回 None (略过)。"""
    platform = feed.platform or infer_platform_from_id(feed.id)
    if platform == PLATFORM_MP and feed.id.startswith("MP_WXS_"):
        return "公众号"
    if platform == PLATFORM_XHS:
        if feed.id.startswith(XHS_KW_PREFIX):
            return "小红书-关键词"
        if feed.id.startswith(XHS_U_PREFIX):
            return "小红书-账号"
    if platform == PLATFORM_DY:
        if feed.id.startswith(DY_KW_PREFIX):
            return "抖音-关键词"
    if platform == PLATFORM_BILI:
        if feed.id.startswith(BILI_KW_PREFIX):
            return "B站-关键词"
    if platform == PLATFORM_X:
        if feed.id.startswith(X_KW_PREFIX):
            return "X-关键词"
    if platform == PLATFORM_TIKTOK and feed.id.startswith(TIKTOK_KW_PREFIX):
        return "TikTok-关键词"
    if platform == PLATFORM_YOUTUBE and feed.id.startswith(YOUTUBE_KW_PREFIX):
        return "YouTube-关键词"
    if platform == PLATFORM_INSTAGRAM and feed.id.startswith(INSTAGRAM_KW_PREFIX):
        return "Instagram-关键词"
    return None


@router.get("/feeds/export", summary="导出全部 feed (跨平台,按 sheet 区分)")
async def export_feeds_excel(
    limit: int = Query(5000, ge=1, le=20000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    current_user: dict = Depends(get_current_user_or_ak),
):
    """导出全平台 feed 列表为 xlsx, 按平台拆 sheet。

    * sheet "公众号": MP_WXS_* + platform=mp
    * sheet "小红书-关键词": XHS_KW_* + platform=xhs
    * sheet "小红书-账号": XHS_U_* + platform=xhs

    旧的 ``/export/mps/export`` 保留,内部委托此实现并固定只输出 mp sheet
    (向前兼容前端 URL)。
    """
    session = DB.get_session()
    try:
        query = session.query(Feed)
        if kw:
            query = query.filter(Feed.name.ilike(f"%{kw}%"))
        feeds = (
            query.order_by(Feed.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        from openpyxl import Workbook

        wb = Workbook()
        # 默认 sheet 删掉,改用每个平台一个 sheet
        wb.remove(wb.active)
        sheet_rows: dict[str, list[list]] = {}
        for sheet_name, headers, _row_builder in _EXCEL_SHEETS:
            sheet_rows[sheet_name] = [list(headers)]
        for f in feeds:
            sheet_name = _classify_feed_for_export(f)
            if not sheet_name:
                continue
            for sn, _, row_builder in _EXCEL_SHEETS:
                if sn == sheet_name:
                    sheet_rows[sn].append(row_builder(f))
                    break

        for sheet_name, headers, _ in _EXCEL_SHEETS:
            ws = wb.create_sheet(title=sheet_name)
            for row in sheet_rows[sheet_name]:
                ws.append(row)

        temp_file = "temp_feeds_export.xlsx"
        wb.save(temp_file)
        return FileResponse(
            temp_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="订阅列表.xlsx",
            background=BackgroundTask(lambda: os.remove(temp_file)),
        )
    except Exception as e:
        print(f"导出订阅列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="导出订阅列表失败"),
        )


@router.get("/mps/export", summary="(兼容) 导出公众号列表 — 委托 /export/feeds/export")
async def export_mps(
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """旧路径 — 返回与 ``/export/feeds/export`` 相同的 xlsx, 但只导出 mp sheet 数据
    (其它 sheet 表头存在但内容为空, 保留前端 ``ExportMPS`` 调用零改动)。
    """
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        # 仅 mp 数据
        query = session.query(Feed).filter(
            (Feed.platform == PLATFORM_MP) | Feed.platform.is_(None),
        ).filter(Feed.id.like("MP_WXS_%"))
        if kw:
            query = query.filter(Feed.name.ilike(f"%{kw}%"))
        mps = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()

        from openpyxl import Workbook

        wb = Workbook()
        wb.remove(wb.active)
        for sheet_name, headers, row_builder in _EXCEL_SHEETS:
            ws = wb.create_sheet(title=sheet_name)
            ws.append(list(headers))
            if sheet_name == "公众号":
                for mp in mps:
                    ws.append(row_builder(mp))
        # 其它 sheet 仅保留表头 (向前兼容旧前端)
        # 行生成器对于非 mp sheet 仍会被调, 但没有数据 → 自然空

        temp_file = "temp_mp_export.xlsx"
        wb.save(temp_file)
        return FileResponse(
            temp_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="订阅列表.xlsx",
            background=BackgroundTask(lambda: os.remove(temp_file)),
        )

    except Exception as e:
        print(f"导出公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message="导出公众号列表失败"
            )
        )

@router.post("/mps/import", summary="导入公众号列表")
async def import_mps(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed

        # 读取上传的CSV文件
        contents = (await file.read()).decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(contents))

        # 验证必要字段
        required_columns = ["公众号名称", "封面图", "简介"]
        if not all(col in csv_reader.fieldnames for col in required_columns):
            missing_cols = [col for col in required_columns if col not in csv_reader.fieldnames]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40001,
                    message=f"CSV文件缺少必要列: {', '.join(missing_cols)}"
                )
            )

        # 导入数据
        imported = 0
        updated = 0
        skipped = 0

        for row in csv_reader:
            mp_id = row["id"]
            mp_name = row["公众号名称"]
            mp_cover = row["封面图"]
            mp_intro = row.get("简介", "")
            status_val = int(row.get("状态", 1)) if row.get("状态") else 1
            faker_id = row.get("faker_id", "")

            # 检查是否已存在
            existing = session.query(Feed).filter(Feed.faker_id == faker_id).first()

            if existing:
                # 更新现有记录
                existing.cover = mp_cover
                existing.intro = mp_intro
                existing.status = status_val
                existing.faker_id = faker_id
                updated += 1
            else:
                # 创建新记录
                mp = Feed(
                    id=mp_id,
                    name=mp_name,
                    cover=mp_cover,
                    intro=mp_intro,
                    status=status_val,
                    faker_id=faker_id,
                    created_at=datetime.now()
                )
                import base64
                if mp.id == None:
                    _mp_id=base64.b64decode(faker_id).decode("utf-8")
                    mp.id=f"MP_WXS_{_mp_id}"
                session.add(mp)
                imported += 1

        session.commit()

        return success_response({
            "message": "导入公众号列表成功",
            "stats": {
                "total": imported + updated + skipped,
                "imported": imported,
                "updated": updated,
                "skipped": skipped
            }
        })

    except Exception as e:
        session.rollback()
        print(f"导入公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="导入公众号列表失败"
            )
        )

@router.get("/mps/opml", summary="导出公众号列表为OPML格式")
async def export_mps_opml(
    request: Request,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        query = session.query(Feed)
        if kw:
            query = query.filter(Feed.name.ilike(f"%{kw}%"))

        mps = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        rss_domain=cfg.get("rss.base_url",str(request.base_url))
        if rss_domain=="":
            rss_domain=str(request.base_url)
        # 生成OPML内容
        opml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
  <head>
    <title>公众号订阅列表</title>
    <dateCreated>{date}</dateCreated>
  </head>
  <body>
{outlines}
  </body>
</opml>'''.format(
            date=datetime.now().isoformat(),
            outlines=''.join([f'<outline text="{mp.name}" title="{mp.name}" type="rss"  xmlUrl="{rss_domain}feed/{mp.id}.atom"/>\n' for mp in mps])
        )

        # 创建临时OPML文件
        temp_file = "temp_mp_export.opml"
        with open(temp_file, "w", encoding='utf-8') as f:
            f.write(opml_content)

        # 返回文件下载
        return FileResponse(
            temp_file,
            media_type="application/xml",
            filename="公众号订阅列表.opml",
            background=BackgroundTask(lambda: os.remove(temp_file))
        )

    except Exception as e:
        print(f"导出OPML列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50002,
                message="导出OPML列表失败"
            )
        )

@router.get("/tags", summary="导出标签列表")
async def export_tags(
        limit: int = Query(1000, ge=1, le=10000),
        offset: int = Query(0, ge=0),
        kw: str = Query(""),
        current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.tags import Tags
        query = session.query(Tags)
        if kw:
            query = query.filter(Tags.name.ilike(f"%{kw}%"))

        tags = query.order_by(Tags.created_at.desc()).limit(limit).offset(offset).all()

        headers = ["id", "标签名称", "封面图", "描述", "状态", "创建时间", "feed_ids"]
        data = []
        for tag in tags:
            data.append([
                tag.id,
                tag.name,
                tag.cover,
                tag.intro,
                tag.status,
                tag.created_at.isoformat() if tag.created_at else "",
                tag.feed_ids
            ])

        # 创建临时CSV文件
        temp_file = "temp_tags_export.csv"
        with open(temp_file, "w", encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(data)

        return FileResponse(
            temp_file,
            media_type="text/csv",
            filename="标签列表.csv",
            background=BackgroundTask(lambda: os.remove(temp_file))
        )

    except Exception as e:
        print(f"导出标签列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50003,
                message="导出标签列表失败"
            )
        )

@router.post("/tags/import", summary="导入标签列表")
async def import_tags(
        file: UploadFile = File(...),
        current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.tags import Tags

        contents = (await file.read()).decode('utf-8-sig')
        csv_reader = csv.DictReader(io.StringIO(contents))

        required_columns = ["标签名称", "状态", "feed_ids"]
        if not all(col in csv_reader.fieldnames for col in required_columns):
            missing_cols = [col for col in required_columns if col not in csv_reader.fieldnames]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40002,
                    message=f"CSV文件缺少必要列: {', '.join(missing_cols)}"
                )
            )

        imported = 0
        updated = 0
        skipped = 0

        for row in csv_reader:
            tag_id = row.get("id")
            tag_name = row.get("标签名称")

            if not tag_name or not tag_name.strip():
                skipped += 1
                continue # 如果标签名称为空，则跳过此行

            existing_tag = None
            if tag_id and tag_id.strip():
                existing_tag = session.query(Tags).filter(Tags.id == tag_id.strip()).first()

            cover = row.get("封面图", "")
            intro = row.get("描述", "")
            try:
                status_val = int(row.get("状态", 1))
            except (ValueError, TypeError):
                status_val = 1
            feed_ids_str = row.get("feed_ids") or "[]"

            if existing_tag:
                existing_tag.name = tag_name
                existing_tag.cover = cover
                existing_tag.intro = intro
                existing_tag.status = status_val
                existing_tag.feed_ids = feed_ids_str
                existing_tag.updated_at = datetime.now()
                updated += 1
            else:
                new_tag = Tags(
                    id=str(uuid.uuid4()),
                    name=tag_name,
                    cover=cover,
                    intro=intro,
                    status=status_val,
                    feed_ids=feed_ids_str,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                session.add(new_tag)
                imported += 1

        session.commit()

        return success_response({
            "message": "导入标签列表成功",
            "stats": {
                "total_rows": imported + updated + skipped,
                "imported": imported,
                "updated": updated,
                "skipped": skipped
            }
        })

    except HTTPException as he:
        raise he
    except Exception as e:
        session.rollback()
        print(f"导入标签列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50004,
                message=f"导入标签列表失败: {str(e)}"
            )
        )
