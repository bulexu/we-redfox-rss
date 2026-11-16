"""视频字幕获取与文案补抓；任务型接口在作品提交后入队。"""
import json
import os
import threading
import time
from urllib.parse import parse_qs, urlsplit, urlunsplit

from core.print import print_warning

_pending = set()
_lock = threading.Lock()
_ENDPOINTS = {"xhs": "xiaohongshu", "dy": "douyin", "bili": "bilibili"}
_MAX_TRANSCRIPT_CALLS = 3
_POLL_INTERVALS = (5, 15)


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


def xhs_transcript_url(url, work_id):
    """保留原始签名和来源参数，并统一为 Redfox 要求的作品路径。"""
    try:
        parts = urlsplit((url or "").strip())
        params = parse_qs(parts.query)
    except ValueError:
        return None
    if (
        not work_id or parts.scheme != "https"
        or parts.netloc.lower() not in ("www.xiaohongshu.com", "xiaohongshu.com")
        or parts.path.rstrip("/") not in (f"/explore/{work_id}", f"/discovery/item/{work_id}")
        or not params.get("xsec_token") or not params.get("xsec_source")
    ):
        return None
    return urlunsplit(("https", "www.xiaohongshu.com", f"/explore/{work_id}", parts.query, ""))


def transcript_url(platform, url, work_id):
    if platform == "xhs":
        return xhs_transcript_url(url, work_id)
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return None
    if parts.scheme != "https":
        return None
    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    if platform == "dy":
        if host in ("www.iesdouyin.com", "iesdouyin.com") and path.startswith("/share/video/"):
            video_id = path[len("/share/video/"):]
            if video_id.isascii() and video_id.isdigit():
                return f"https://www.douyin.com/video/{video_id}"
        valid = (
            (host in ("www.douyin.com", "douyin.com") and path.startswith(("/video/", "/note/"))
             and path.count("/") == 2 and path.rsplit("/", 1)[-1].isdigit())
            or (host == "v.douyin.com" and path.count("/") == 1 and path[1:].isalnum())
        )
    elif platform == "bili":
        valid = (
            (host in ("www.bilibili.com", "bilibili.com", "m.bilibili.com")
             and path.startswith("/video/") and path[7:].isalnum()
             and path[7:].startswith(("BV", "av")) and len(path) > 9)
            or (host == "b23.tv" and path.count("/") == 1 and path[1:].isalnum())
        )
    elif platform == "youtube":
        valid = host in ("www.youtube.com", "youtube.com", "m.youtube.com") and path == "/watch" and bool(parse_qs(parts.query).get("v"))
    else:
        valid = False
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "")) if valid else None


def needs_transcript(meta):
    platform = meta.get("platform")
    return bool(
        platform in _ENDPOINTS
        and meta.get("transcript_call_count", 0) < _MAX_TRANSCRIPT_CALLS
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
        if not meta.get("transcript_task_id") and not transcript_url(platform, item.get("url"), key):
            continue
        with _lock:
            if key in _pending:
                continue
            _pending.add(key)
        try:
            accepted = ContentTaskQueue.add_task(
                fetch_transcript, key, task_name=f"视频文案提取 [{platform}] {key}: {item.get('title') or key}",
                max_retries=2,
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
        previous_meta = _metadata(previous.extinfo) if previous else {}
        count = max(meta.get("transcript_call_count", 0), previous_meta.get("transcript_call_count", 0))
        url = transcript_url("youtube", item.get("url"), item["id"])
        if count >= _MAX_TRANSCRIPT_CALLS or not url:
            continue
        meta["transcript_call_count"] = count + 1
        item["extinfo"] = json.dumps(meta, ensure_ascii=False)
        try:
            text = extract_text(get_transcript(url))
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
                "id": article.id, "title": article.title, "extinfo": article.extinfo, "url": article.url,
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

    if not video_conversion_enabled():
        with _lock:
            _pending.discard(article_id)
        return

    session = DB.get_session()
    try:
        article = session.query(Article).filter(Article.id == article_id).first()
        if article is None or article.status != 1:
            return
        meta = _metadata(article.extinfo)
        if meta.get("video_transcript"):
            return
        platform = meta.get("platform")
        if platform not in _ENDPOINTS:
            return  # 兼容更新前已入队的任务，不支持的平台不发起接口请求。
        if meta.get("transcript_call_count", 0) >= _MAX_TRANSCRIPT_CALLS:
            return
        task_id = meta.get("transcript_task_id")
        submit_url = transcript_url(platform, article.url, article_id) if not task_id else None
        if not task_id and not submit_url:
            print_warning(f"跳过视频文案提取 {article_id}：链接格式无效")
            return

        client = _get_client_for("transcript", lambda: RedfoxClient(max_retries=0))
        endpoint = _ENDPOINTS[platform]
        api = getattr(client._sdk, endpoint)
        path = "/story/api/parseWork/audioTextExtract"

        def call(operation, payload, sdk_op):
            meta["transcript_call_count"] = meta.get("transcript_call_count", 0) + 1
            article.extinfo = json.dumps(meta, ensure_ascii=False)
            session.commit()
            return client._sdk_call(f"{path}/{operation}/{endpoint}", payload, sdk_op)

        if not task_id:
            task = call("submit", {"workId": article_id}, lambda: api.transcript_submit(url=submit_url))
            task_id = task["taskId"]
            meta["transcript_task_id"] = task_id
            article.extinfo = json.dumps(meta, ensure_ascii=False)
            session.commit()
        attempt = 0
        while meta.get("transcript_call_count", 0) < _MAX_TRANSCRIPT_CALLS:
            if not video_conversion_enabled():
                return
            result = call("result", {"taskId": task_id}, lambda: api.transcript_result(task_id=task_id))
            status = str(result.get("status", result.get("taskStatus", ""))).lower() if isinstance(result, dict) else ""
            if status in ("failed", "failure", "error"):
                raise RuntimeError(f"视频文案提取失败: {task_id}")
            if status not in ("pending", "processing", "running", "queued") and extract_text(result):
                break
            if meta["transcript_call_count"] < _MAX_TRANSCRIPT_CALLS:
                time.sleep(_POLL_INTERVALS[attempt])
                attempt += 1
        else:
            raise TimeoutError(f"视频文案提取已达三次接口调用上限: {task_id}")
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
        for key in ("video_transcript", "transcript_task_id", "transcript_failed_at", "transcript_call_count"):
            if key in meta:
                if key == "transcript_call_count":
                    updated[key] = max(updated.get(key, 0), meta[key])
                else:
                    updated[key] = meta[key]
        return json.dumps(updated, ensure_ascii=False)
    return value
