"""视频字幕获取与文案补抓；任务型接口在作品提交后入队。"""
import json
import os
import threading
import time

from core.print import print_warning

_pending = set()
_lock = threading.Lock()
_ENDPOINTS = {"xhs": "xiaohongshu", "dy": "douyin", "bili": "bilibili"}


def _metadata(value):
    try:
        return json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}


def extract_text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(filter(None, (extract_text(v) for v in value)))
    if isinstance(value, dict):
        for key in ("text", "transcript", "content", "audioText", "segments", "subtitles", "result", "data"):
            if key in value:
                text = extract_text(value[key])
                if text:
                    return text
    return ""


def video_conversion_enabled():
    from core.config import cfg

    enabled = os.getenv("REDFOX_CONVERT_VIDEO", str(cfg.get("redfox.convert_video", False)))
    return enabled.lower() in ("true", "1", "yes", "on")


def needs_transcript(meta):
    platform = meta.get("platform")
    return bool(
        platform and platform not in ("wechat", "youtube")
        and not meta.get("video_transcript")
        and (platform != "xhs" or meta.get("work_type") == "video")
        and time.time() - meta.get("transcript_failed_at", 0) >= 3600
    )


def enqueue_transcripts(items):
    from core.queue import ContentTaskQueue

    if not video_conversion_enabled():
        return 0
    count = 0
    for item in items:
        meta = _metadata(item.get("extinfo"))
        platform = meta.get("platform")
        if not needs_transcript(meta):
            continue
        key = item["id"]
        with _lock:
            if key in _pending:
                continue
            _pending.add(key)
        try:
            accepted = ContentTaskQueue.add_task(
                fetch_transcript, key, task_name=f"视频文案提取 [{platform}] {key}: {item.get('title') or key}",
                max_retries=2 if platform in _ENDPOINTS else 0,
            )
            if accepted:
                count += 1
            else:
                with _lock:
                    _pending.discard(key)
        except Exception as exc:
            with _lock:
                _pending.discard(key)
            print_warning(f"视频文案任务入队失败 {key}: {exc}")
    return count


def enrich_direct_transcripts(session, items):
    """直接返回字幕的平台在采集时补齐，不投递异步提取任务。"""
    from core.models.article import Article
    from core.redfox.youtube.client import get_transcript

    if not video_conversion_enabled():
        return
    videos = [item for item in items if _metadata(item.get("extinfo")).get("platform") == "youtube"]
    if not videos:
        return
    existing = {a.id: a for a in session.query(Article).filter(
        Article.id.in_([item["id"] for item in videos])
    ).all()}
    for item in videos:
        meta = _metadata(item.get("extinfo"))
        previous = existing.get(item["id"])
        if meta.get("video_transcript") or (previous and _metadata(previous.extinfo).get("video_transcript")):
            continue
        try:
            text = extract_text(get_transcript(item["url"]))
            if text:
                meta["video_transcript"] = text
                item["extinfo"] = json.dumps(meta, ensure_ascii=False)
                original = item.get("description") or item.get("content") or ""
                item["content"] = f"{original}\n\n{text}".strip()
        except Exception as exc:
            print_warning(f"YouTube 字幕获取失败 {item['id']}: {exc}")


def backfill_transcripts(limit=10):
    """定时扫描已有作品，补齐增量采集不会再次返回的视频。"""
    from core.db import DB
    from core.models.article import Article

    if not video_conversion_enabled():
        return 0
    session = DB.get_session()
    count = 0
    try:
        articles = session.query(Article).filter(
            Article.status == 1,
            ~Article.feed_id.like("MP_WXS_%"),
            Article.extinfo.isnot(None),
        ).order_by(Article.publish_time.desc()).yield_per(100)
        for article in articles:
            count += enqueue_transcripts([{
                "id": article.id, "title": article.title, "extinfo": article.extinfo,
            }])
            if count >= limit:
                break
        return count
    finally:
        session.close()


def fetch_transcript(article_id):
    from core.db import DB
    from core.models.article import Article
    from core.redfox.base import RedfoxClient, _get_client_for

    session = DB.get_session()
    try:
        article = session.query(Article).filter(Article.id == article_id).first()
        if article is None or article.status != 1:
            return
        meta = _metadata(article.extinfo)
        if meta.get("video_transcript"):
            return
        platform = meta.get("platform")
        if platform == "youtube":
            return  # 兼容更新前已入队的任务，字幕改由采集流程直接获取。
        client = _get_client_for("transcript", RedfoxClient)
        if platform in _ENDPOINTS:
            endpoint = _ENDPOINTS[platform]
            api = getattr(client._sdk, endpoint)
            path = f"/story/api/parseWork/audioTextExtract"
            task_id = meta.get("transcript_task_id")
            if not task_id:
                task = client._sdk_call(
                    f"{path}/submit/{endpoint}", {"url": article.url},
                    lambda: api.transcript_submit(url=article.url),
                )
                task_id = task["taskId"]
                meta["transcript_task_id"] = task_id
                article.extinfo = json.dumps(meta, ensure_ascii=False)
                session.commit()
            # 有限轮询；超时保留 taskId，后续补抓可继续查询，避免重复付费提交。
            for attempt in range(60):
                result = client._sdk_call(
                    f"{path}/result/{endpoint}", {"taskId": task_id},
                    lambda: api.transcript_result(task_id=task_id),
                )
                status = str(result.get("status", result.get("taskStatus", ""))).lower() if isinstance(result, dict) else ""
                if status in ("failed", "failure", "error"):
                    raise RuntimeError(f"视频文案提取失败: {result}")
                if status not in ("pending", "processing", "running", "queued") and extract_text(result):
                    break
                if attempt == 59:
                    raise TimeoutError(f"视频文案提取超时: {task_id}")
                time.sleep(5)
        else:
            raise RuntimeError(f"Redfox SDK 暂不支持 {platform} 视频文案接口")
        text = extract_text(result)
        if not text:
            raise RuntimeError("视频文案接口返回空文案")
        # 重新读取，避免轮询期间覆盖其他任务更新的指标和扩展信息。
        session.refresh(article)
        meta = _metadata(article.extinfo)
        meta.pop("transcript_failed_at", None)
        meta["video_transcript"] = text
        original = article.description or article.content or ""
        article.content = f"{original}\n\n{text}".strip()
        article.extinfo = json.dumps(meta, ensure_ascii=False)
        article.has_content = 1
        article.updated_at = article.updated_at_millis = int(time.time() * 1000)
        session.commit()
    except Exception:
        session.rollback()
        # 定时补抓稍后再试，避免不支持的平台或持续失败的作品占满队列。
        try:
            session.refresh(article)
            meta = _metadata(article.extinfo)
            meta["transcript_failed_at"] = int(time.time())
            article.extinfo = json.dumps(meta, ensure_ascii=False)
            session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()
        with _lock:
            _pending.discard(article_id)


def preserve_transcript(article, field, value):
    """列表刷新不可抹掉已完成文案或远端任务 ID。"""
    meta = _metadata(article.extinfo)
    if field == "content" and meta.get("video_transcript"):
        return article.content
    if field == "extinfo":
        updated = _metadata(value)
        for key in ("video_transcript", "transcript_task_id", "transcript_failed_at"):
            if key in meta:
                updated[key] = meta[key]
        return json.dumps(updated, ensure_ascii=False)
    return value
