"""飞书多维表自动推送定时任务。

设计要点 (2024 重构,  二次):
  * 不在 ``apis/article.py`` / ``core/article_content.py`` / ``core/db.py``
    三个写入路径上调 ``lark_maybe_push``,  本文件按 cron 周期统一扫描。
  * 去重:  2024 重构删除 ``article_lark_pushes`` 表后,  改用
    ``LarkBitable.last_pushed_at`` 作为 publish_time 水印:
      - ``last_pushed_at IS NULL`` (新 Bitable / 升级后被重置):  推送全部命中 mp_ids 的文章
      - ``last_pushed_at = X``:  仅推送 ``article.publish_time > X`` 的文章
  * 提交:  走 ``lark_maybe_push(article_id)`` 入口(模块级线程池),  不阻塞
    cron 调度线程本身。worker 内部按 publish_time 倒序处理并抬升水印。
  * 间隔:  ``lark.push_interval_hours`` 配置,  允许值 0(关闭) / 2 / 4 / 6 / 12 / 24,
    0 表示关闭自动推送,  仍可通过 ``POST /api/v1/lark/bitables/{id}/push`` 手动推。

并发安全:
  * 单次扫描限速 ``lark.push_batch_size``,  超出的留到下一轮,  避免 worker 池被
    一次性打爆。
  * worker 内部按水印 + publish_time 排序,  调度重叠也不会重复推送同一篇。
"""
from __future__ import annotations

import time
from typing import Iterable, List

from core.config import cfg
from core.db import DB
from core.models.article import Article
from core.models.base import DATA_STATUS
from core.models.lark_bitable import LarkBitable
from core.print import print_info, print_warning
from core.task import TaskScheduler

# 允许的推送间隔(小时)。 其它值会被规整到列表里最接近的一项,  实在不像就直接关闭。
ALLOWED_PUSH_INTERVAL_HOURS: tuple[int, ...] = (2, 4, 6, 12, 24)
PUSH_JOB_ID = "lark_auto_push_scan"
DEFAULT_BATCH_SIZE = 100

# 独立 scheduler 实例,  与 ``jobs/mps.py`` / ``jobs/fetch_no_article.py``
# 互不干扰;  main.py 仅在主进程启动时调用 :func:`start_lark_push_scheduler` 增加一次。
_scheduler: TaskScheduler = TaskScheduler()


def _normalize_interval_hours(raw: object) -> int:
    """把配置值规整到允许列表里;  0 或非法值表示关闭。"""
    try:
        hours = int(raw) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        return 0
    if hours <= 0:
        return 0
    if hours in ALLOWED_PUSH_INTERVAL_HOURS:
        return hours
    # 落在区间内:  圆整到最近的允许值
    closest = min(ALLOWED_PUSH_INTERVAL_HOURS, key=lambda h: abs(h - hours))
    print_warning(
        f"[lark] push_interval_hours={hours} 不在 {list(ALLOWED_PUSH_INTERVAL_HOURS)} 内,"
        f"自动圆整到 {closest}"
    )
    return closest


def _hours_to_cron(hours: int) -> str:
    """小时数 → 5 段 cron 表达式。

    ``0 */N * * *`` 表示每小时第 0 分起每 N 小时执行一次。
    24 小时特殊处理成 ``0 0 * * *`` (每天 00:00 跑一次,  语义更清晰)。
    """
    if hours >= 24:
        return "0 0 * * *"
    return f"0 */{hours} * * *"


def _collect_pending_article_ids(bitable: LarkBitable, batch_size: int) -> List[str]:
    """单个 Bitable 取出「待推送」article_id 列表 (按发布时间倒序,  限 batch_size)。

    去重:  ``article.publish_time > COALESCE(bitable.last_pushed_at, 0)``。
    即:
      * ``last_pushed_at IS NULL`` → 0 → 全部命中 mp_ids 的有效文章都满足,  即「推送全部」
      * ``last_pushed_at = X`` → 仅推送比 X 更新的 article

    注:  ``COALESCE(NULL, 0)`` 在 SQL 里直接由 ORM 渲染,  与各数据库都兼容。
    """
    mp_ids = bitable.get_feed_ids()
    if not mp_ids:
        return []

    watermark = int(bitable.last_pushed_at or 0)

    session = DB.get_session()
    try:
        candidates: Iterable[Article] = (
            session.query(Article)
            .filter(
                Article.feed_id.in_(mp_ids),
                Article.status != DATA_STATUS.DELETED,
                Article.has_content == 1,
                # 水印过滤:  发布时间晚于上次推送时间(单位毫秒)
                Article.publish_time > watermark,
            )
            .order_by(Article.publish_time.desc())
            .limit(batch_size)
            .all()
        )
        return [a.id for a in candidates if a.id]
    finally:
        try:
            session.close()
        except Exception:
            pass


def scan_pending_push_articles() -> None:
    """cron 回调:  对所有 enabled Bitable 扫描待推送文章并提交 worker。

    单个 Bitable 内部是顺序的(同一 Bitable 内的 worker 任务数受
    ``ThreadPoolExecutor(max_workers=4)`` 控制),  多个 Bitable 之间互不影响。

    任何异常都吞掉只 log,  避免 APScheduler 标记失败后停止后续周期。
    """
    try:
        if not cfg.get("lark.enabled", False):
            return

        from core.lark_client import get_lark_client

        if get_lark_client() is None:
            print_warning("[lark] 自动推送扫描跳过: app_id / app_secret 未配置")
            return

        batch_size = int(cfg.get("lark.push_batch_size", DEFAULT_BATCH_SIZE) or DEFAULT_BATCH_SIZE)
        if batch_size <= 0:
            batch_size = DEFAULT_BATCH_SIZE

        session = DB.get_session()
        try:
            bitables = (
                session.query(LarkBitable)
                .filter(LarkBitable.enabled == True)  # noqa: E712
                .all()
            )
        finally:
            try:
                session.close()
            except Exception:
                pass

        if not bitables:
            return

        from core.lark_push import lark_maybe_push

        total_submitted = 0
        total_bitables_touched = 0
        for bitable in bitables:
            try:
                pending_ids = _collect_pending_article_ids(bitable, batch_size)
            except Exception as exc:  # noqa: BLE001
                print_warning(
                    f"[lark] 扫描 bitable={bitable.id}({bitable.name}) 失败: {exc}"
                )
                continue

            if not pending_ids:
                continue

            total_bitables_touched += 1
            print_info(
                f"[lark] auto-scan bitable={bitable.id}({bitable.name}) "
                f"待推送 {len(pending_ids)} 条"
            )
            for aid in pending_ids:
                try:
                    lark_maybe_push(aid)
                    total_submitted += 1
                except Exception as exc:  # noqa: BLE001
                    # lark_maybe_push 自身已捕获,  这里只是兜底
                    print_warning(f"[lark] 提交推送任务失败 article={aid}: {exc}")

        if total_submitted:
            print_info(
                f"[lark] auto-scan done bitables={total_bitables_touched} "
                f"submitted={total_submitted} at {int(time.time())}"
            )
    except Exception as exc:  # noqa: BLE001
        print_warning(f"[lark] auto-scan 整体异常(已吞掉): {exc}")


def start_lark_push_scheduler() -> None:
    """main.py 启动钩子:  按 ``lark.push_interval_hours`` 注册 / 刷新 cron。

    多次调用安全:  先移除同名旧 job 再注册新的,  保证「重启 / reload_job」
    之后间隔变化生效。
    """
    hours = _normalize_interval_hours(cfg.get("lark.push_interval_hours", 0))
    if hours <= 0:
        # 关闭自动推送,  同时移除可能存在的旧 job
        try:
            _scheduler.remove_job(PUSH_JOB_ID)
        except Exception:
            pass
        print_warning(
            "[lark] push_interval_hours=0,  自动推送已关闭(可手动调 /push 接口)"
        )
        return

    cron_expr = _hours_to_cron(hours)
    try:
        _scheduler.remove_job(PUSH_JOB_ID)
    except Exception:
        pass

    _scheduler.add_cron_job(
        scan_pending_push_articles,
        cron_expr=cron_expr,
        job_id=PUSH_JOB_ID,
        tag="飞书多维表自动推送扫描",
    )
    if not _scheduler._scheduler.running:  # noqa: SLF001 — 复用底层状态判断
        _scheduler.start()
    print_info(
        f"[lark] 自动推送扫描任务已注册: cron={cron_expr!r} "
        f"(每 {hours} 小时一次)"
    )


def reload_lark_push_scheduler() -> None:
    """暴露给 ``reload_job`` 用,  清掉 scheduler 里所有 lark 相关 job 后重注册。"""
    try:
        _scheduler.remove_job(PUSH_JOB_ID)
    except Exception:
        pass
    start_lark_push_scheduler()
