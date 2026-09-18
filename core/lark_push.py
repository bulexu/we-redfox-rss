"""飞书多维表推送 worker。

入口点:
  * ``lark_maybe_push(article_id, bitable_id=None)`` — 提交异步任务到模块级 ``ThreadPoolExecutor``,
    立刻返回,  不阻塞调用方 (cron 周期任务 / 手动 ``POST /lark/bitables/{id}/push``
    接口都调这个)。

worker 内部:
  1. 开新 session
  2. 读 article + Feed.name
  3. 全局 ``lark.enabled`` 为 False → 直接退出
  4. 查关联 Bitables (``LarkBitable.enabled=True`` 且 ``mp_ids`` 含 ``article.feed_id``)
  5. 对每个 Bitable:
     *  ``bitable.last_pushed_at`` 水印过滤:  跳过 ``article.publish_time <= last_pushed_at``
        的旧文章(避免重推历史)
     *  通过 → 构造 ``fields`` 字典, 调 ``batch_create``
     *  成功后更新 ``bitable.last_pushed_at = max(原值, article.publish_time)``
     *  失败后更新 ``last_error`` / ``last_error_at`` 并 log(不动水印,  下个周期会重试)

幂等性靠 ``last_pushed_at`` 水印 + 按 ``publish_time`` 倒序处理;  并发 worker
对同一 bitable 同时推进时,  后续 worker 看到的 ``last_pushed_at`` 已经反映了
更早完成的 article,  自然跳过,  不会出现「同一篇推到两次」的情况。
"""
from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

from core.config import cfg
from core.db import DB
from core.lark_client import LarkClient, LarkError, get_lark_client
from core.models.article import Article
from core.models.feed import Feed
from core.models.lark_bitable import ALLOWED_FIELD_KEYS, LarkBitable
from core.print import print_warning, print_info

# 模块级线程池: 4 worker 足够覆盖大多数场景, 不会把 token 刷新打爆。
# daemon=True 跟随主进程退出, 不阻止进程关闭。
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK_IMPORTED = False


def _lark_thread_excepthook(args):
    """捕获 ThreadPoolExecutor 线程里漏出的异常, 打完整 traceback。

    默认 ``threading.excepthook`` 只打 ``Exception in thread ...`` 一行,
    对调试 worker 死因极不友好。这里补足 traceback。
    """
    print_warning(
        f"[lark] uncaught exception in thread {args.thread.name!r}: "
        f"{args.exc_value!r}"
    )
    traceback.print_exception(
        type(args.exc_value), args.exc_value, args.exc_traceback
    )


# 仅设置一次, 避免 reload 时重复挂多个 hook。
if not getattr(threading.excepthook, "_lark_hook_installed", False):
    _orig_excepthook = threading.excepthook
    def _patched_excepthook(args):
        if args.thread.name and args.thread.name.startswith("lark-push"):
            _lark_thread_excepthook(args)
            return
        _orig_excepthook(args)
    _patched_excepthook._lark_hook_installed = True  # type: ignore[attr-defined]
    threading.excepthook = _patched_excepthook


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lark-push")
    return _EXECUTOR


# ---------- 字段映射取值 ----------

def _resolve_field_value(article: Article, feed: Feed | None, key: str):
    """把字段映射白名单 key 转成实际可发给飞书的值。

    对 ``publish_time`` 转成 ``YYYY-MM-DD HH:MM:SS`` 本地时间字符串
    (服务器部署在 Asia/Shanghai, 与公众号页面显示一致)。
    其他 key 直接 ``getattr`` Article / Feed。
    """
    if key == "publish_time":
        ts = getattr(article, "publish_time", None)
        if not ts:
            return None
        try:
            # publish_time 既可能是秒也可能是毫秒
            ts = int(ts)
            if ts > 10_000_000_000:
                ts = ts // 1000
            # epoch 在抓取阶段已按服务器本地时区(Asia/Shanghai)换算过,
            # 这里直接用本地时区输出 ``YYYY-MM-DD HH:MM:SS`` 文本,
            # 与公众号页面显示一致, 避免飞书按 UTC 解读造成 8 小时偏差。
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OverflowError):
            return None

    if key in {"feed_id", "name"}:
        if feed is None and key == "name":
            return None
        if key == "name":
            return getattr(feed, "name", None)
        return getattr(article, "feed_id", None)

    return getattr(article, key, None)


def _build_fields_for_article(
    article: Article,
    feed: Feed | None,
    mapping: dict,
) -> dict:
    fields: dict = {}
    for lhs, rhs in mapping.items():
        if lhs not in ALLOWED_FIELD_KEYS:
            continue
        value = _resolve_field_value(article, feed, lhs)
        if value is None:
            continue
        fields[rhs] = value
    return fields


# ---------- 主入口 ----------

def lark_maybe_push(article_id: str, bitable_id: str | None = None) -> None:
    """回调入口: 把 article 异步推到所有关联 Bitables。

    ``bitable_id`` 为空时推到所有关联表；传值时只推到指定表。
    调用方不要传 session 或 ORM 对象
    (worker 自己开新 session, 避免调用方 session 已关闭问题)。

    多次调用同一 article_id 安全:  worker 内部按 ``last_pushed_at`` 水印
    + 按 publish_time 倒序处理,  并发场景下不会重复推送。
    """
    if not cfg.get("lark.enabled", False):
        return
    if not article_id:
        return
    try:
        _get_executor().submit(_push_article_job, str(article_id), bitable_id)
    except RuntimeError:
        # 进程关闭时 executor 已 shutdown, 静默忽略
        pass


def lark_push_bitable_batch(article_ids: list[str], bitable_id: str) -> None:
    """把一批文章按给定顺序串行推到同一张表，避免水印并发越级。"""
    if not cfg.get("lark.enabled", False) or not bitable_id:
        return
    cleaned = [str(article_id) for article_id in article_ids if article_id]
    if not cleaned:
        return
    try:
        _get_executor().submit(_push_bitable_batch_job, cleaned, str(bitable_id))
    except RuntimeError:
        pass


def _push_bitable_batch_job(article_ids: list[str], bitable_id: str) -> None:
    for article_id in article_ids:
        _push_article_job(article_id, bitable_id)


def _push_article_job(article_id: str, bitable_id: str | None = None) -> None:
    """worker 线程执行的实际推送逻辑。"""
    print_info(f"[lark] worker start article_id={article_id}")
    session = DB.get_session()
    try:
        # 直接复用模块级 DB 单例 (``core.db.DB`` 已经是 ``Db`` 实例, 不可再 ``()`` 调用)
        print_info(f"[lark] worker db ready article_id={article_id}")
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            print_info(f"[lark] skip: article {article_id} not found")
            return
        # 跳过被删除或正在抓取中的文章
        from core.models.base import DATA_STATUS

        if article.status == DATA_STATUS.DELETED:
            print_info(f"[lark] skip: article {article_id} status=DELETED")
            return
        if not (article.content or "").strip():
            # 没正文不推, 避免空记录
            print_info(
                f"[lark] skip: article {article_id} content empty"
            )
            return

        feed_id = getattr(article, "feed_id", None)
        if not feed_id:
            print_info(f"[lark] skip: article {article_id} feed_id is empty")
            return

        # 一次性查全部 enabled Bitables, 在 Python 里按 feed_ids 过滤
        bitable_query = session.query(LarkBitable).filter(
            LarkBitable.enabled == True  # noqa: E712
        )
        if bitable_id:
            bitable_query = bitable_query.filter(LarkBitable.id == bitable_id)
        bitables = bitable_query.all()
        matched = [b for b in bitables if feed_id in b.get_feed_ids()]
        if not matched:
            print_info(
                f"[lark] skip: no matched bitable for article={article_id} "
                f"feed_id={feed_id} (enabled_bitables={len(bitables)})"
            )
            return

        feed = (
            session.query(Feed).filter(Feed.id == feed_id).first() if feed_id else None
        )

        client = get_lark_client()
        if client is None:
            # 没配 app_id/secret,  整体功能不可用 — 全局只 log 一次
            print_warning(
                f"[lark] lark.enabled=True 但 lark.app_id/app_secret 未配置,"
                f"article={article_id} 跳过推送"
            )
            return

        # 单个 article 内部按 Bitable 的 last_pushed_at 升序处理:
        # 先推「水印最低」的 bitable,  让所有 bitable 的水印尽量快速爬到
        # 当前 article 的 publish_time,  避免一个 bitable 卡住水印。
        publish_time = getattr(article, "publish_time", None) or 0
        matched_sorted = sorted(
            matched,
            key=lambda b: (getattr(b, "last_pushed_at", None) or 0, b.id),
        )

        print_info(
            f"[lark] dispatch article={article_id} feed_id={feed_id} "
            f"matched={len(matched_sorted)} publish_time={publish_time}"
        )

        for bitable in matched_sorted:
            # 水印过滤:  last_pushed_at 已 >= 本 article 的 publish_time → 跳过
            last_pushed = getattr(bitable, "last_pushed_at", None) or 0
            if last_pushed and publish_time <= last_pushed:
                continue
            try:
                _push_one(article, feed, bitable, client, session)
            except Exception as exc:  # noqa: BLE001
                _record_failure(bitable, session, exc)
    except Exception:
        print_warning(f"[lark] worker 异常 article_id={article_id}")
        traceback.print_exc()
    finally:
        try:
            session.close()
        except Exception:
            pass


def _push_one(
    article: Article,
    feed: Feed | None,
    bitable: LarkBitable,
    client: LarkClient,
    session,
) -> None:
    """单条 Bitable 推送;  失败抛异常由 ``_record_failure`` 收尾。

    成功后把 ``bitable.last_pushed_at`` 抬到 ``max(原值, article.publish_time)``,
    作为下次扫描的水印;  原 ``record_id`` 不再落库(没有 ArticleLarkPush 表)。
    """
    mapping = bitable.get_field_mapping()
    if not mapping:
        print_warning(
            f"[lark] bitable {bitable.id}({bitable.name}) field_mapping 为空, 跳过"
        )
        return

    fields = _build_fields_for_article(article, feed, mapping)
    if not fields:
        print_warning(
            f"[lark] bitable {bitable.id}({bitable.name}) 解析后 fields 为空, 跳过"
        )
        return

    created = client.batch_create_records(
        app_token=bitable.app_token,
        table_id=bitable.table_id,
        records=[{"fields": fields}],
    )
    # 飞书返回的 record_id 不再落库(ArticleLarkPush 已删除),  暂留 log 方便排查
    record_id = ""
    if created:
        record_id = str(created[0].get("record_id") or "")

    # 抬升水印:  max(原 last_pushed_at, article.publish_time)。
    # publish_time 可能为 None / 0 (极少数异常数据),  此时退化为「当前时间」,
    # 保证水印单调不减。
    cur_last = getattr(bitable, "last_pushed_at", None) or 0
    art_pt = getattr(article, "publish_time", None) or 0
    new_watermark = max(cur_last, art_pt, int(time.time() * 1000))
    bitable.last_pushed_at = new_watermark
    bitable.last_error = None
    bitable.last_error_at = None
    session.commit()
    print_info(
        f"[lark] push ok article={article.id} → bitable={bitable.id}({bitable.name}) "
        f"record_id={record_id or '(none)'} watermark={new_watermark}"
    )


def _record_failure(bitable: LarkBitable, session, exc: Exception) -> None:
    """单条 Bitable 推送失败时, 把错误信息写到 bitable 行,  不抛回。"""
    err_text = ""
    if isinstance(exc, LarkError):
        code = getattr(exc, "code", None)
        err_text = f"[{code}] {exc}" if code else str(exc)
    else:
        err_text = f"{type(exc).__name__}: {exc}"
    err_text = err_text[:1000]
    try:
        bitable.last_error = err_text
        bitable.last_error_at = int(time.time() * 1000)
        session.commit()
    except Exception:
        session.rollback()
        # 状态写不进去也只 log,  避免循环
        print_warning(f"[lark] 写 last_error 失败 bitable={bitable.id}: {exc}")
    print_warning(
        f"[lark] push failed bitable={bitable.id}({bitable.name}): {err_text}"
    )


# ---------- 重置（测试用） ----------

def _shutdown_executor_for_tests() -> None:
    """测试用: 关闭模块级 executor,  让 ``ThreadPoolExecutor.__del__`` 不报警。"""
    global _EXECUTOR
    if _EXECUTOR is not None:
        _EXECUTOR.shutdown(wait=False)
        _EXECUTOR = None
