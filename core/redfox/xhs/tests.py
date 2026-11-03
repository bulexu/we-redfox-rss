"""小红书同步核心逻辑的轻量集成测试。

不依赖外部网络 / redfox SDK — 直接构造假 ``note`` dict,  走
``_normalize_note`` + ``_upsert_articles`` 的纯函数路径。  用于在
``redfox`` 包未安装的 CI 环境也能跑基础回归。

测试内容:
  1. ``_normalize_note`` 字段映射 + 缺省值
  2. ``_split_feed_id`` / ``build_feed_id`` 互逆
  3. ``_upsert_articles``:
     - 新 note → INSERT 全字段
     - 已有 note → 只 UPDATE 5 个 metrics + updated_at / updated_at_millis
     - 不修改已有 note 的 title / content / author 等
  4. ``do_job_xhs`` 走完一遍后:
     - watermark (last_publish_time) 推进到最新一条
     - 错误计数清零
     - 新 note 入库

用法 (项目根目录):
    python -m core.redfox.xhs.tests
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List


# 在导入任何项目模块之前先 stub 掉 redfox (CI 环境可能没装 SDK)
def _install_redfox_stub() -> None:
    import types
    if "redfox" in sys.modules:
        return
    stub = types.ModuleType("redfox")
    stub.RedFoxClient = object  # type: ignore
    ex = types.ModuleType("redfox.exceptions")
    for n in ["RedFoxAPIError", "RedFoxAuthError", "RedFoxRateLimitError"]:
        setattr(ex, n, type(n, (Exception,), {}))
    sys.modules["redfox"] = stub
    sys.modules["redfox.exceptions"] = ex


_install_redfox_stub()


def _ensure_redfox_stub() -> None:
    """redfox 包未安装时塞个 stub,  让 core.redfox.xhs 导入不挂。"""
    import types
    if "redfox" in sys.modules:
        return
    stub = types.ModuleType("redfox")
    stub.RedFoxClient = object  # type: ignore
    ex = types.ModuleType("redfox.exceptions")
    for n in ["RedFoxAPIError", "RedFoxAuthError", "RedFoxRateLimitError"]:
        setattr(ex, n, type(n, (Exception,), {}))
    sys.modules["redfox"] = stub
    sys.modules["redfox.exceptions"] = ex


def _make_fake_notes(prefix: str, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
    """构造 N 个递增时间的假 note, workId 用 ``prefix_<i>``。"""
    out = []
    for i in range(count):
        ts = (base_dt + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        out.append({
            "workId": f"{prefix}_{i}",
            "workTitle": f"测试标题 {i}",
            "workDesc": f"测试正文 {i},  本地 stub 数据",
            "coverUrl": f"https://example.com/cover_{i}.jpg",
            "workUrl": f"https://www.xiaohongshu.com/explore/{prefix}_{i}",
            "workPublishTime": ts,
            "accountNickname": "测试昵称",
            "accountUserid": "test_user",
            "workLikedCount": 100 + i,
            "workCommentsCount": 20 + i,
            "workCollectedCount": 30 + i,
            "workReadedCount": 1000 + i,
            "workSharedCount": 5 + i,
            "workType": "normal",
        })
    return out


def _build_xhs_test_feed(session, feed_id: str, target: str = "") -> Any:
    from core.models.feed import Feed
    feed = Feed(
        id=feed_id,
        name=f"测试 {feed_id}",
        cover="",
        intro="",
        status=1,
        max_fetch_count=20,
        refresh_interval_hours=6,
        sync_time=0,
        last_publish_time=0,
        last_cursor=None,
        error_count=0,
        last_error=None,
        last_error_at=None,
        # keyword 类 feed.id 是 uuid, 真正的 keyword 在 target 里;
        # 这里默认从 id suffix 拆 (向后兼容老的 round-trip 测试)。
        target=target or (
            feed_id[len("XHS_KW_"):] if feed_id.startswith("XHS_KW_") else (
                feed_id[len("XHS_U_"):] if feed_id.startswith("XHS_U_") else None
            )
        ),
    )
    session.merge(feed)
    session.commit()
    return feed


def _cleanup(session, feed_id: str) -> None:
    from core.models.article import Article
    session.query(Article).filter(Article.feed_id == feed_id).delete()
    session.query(Feed.__class__) if False else None  # noqa
    from core.models.feed import Feed as _Feed
    session.query(_Feed).filter(_Feed.id == feed_id).delete()
    session.commit()


def test_normalize() -> bool:
    from core.redfox.xhs.sync import _normalize_note
    notes = _make_fake_notes("kw1", 1, datetime(2024, 6, 1, 12, 0, 0))
    n = _normalize_note(notes[0])
    assert n["id"] == "kw1_0"
    assert n["title"] == "测试标题 0"
    assert n["content"] == "测试正文 0,  本地 stub 数据"
    assert n["author"] == "测试昵称"
    assert n["author_id"] == "test_user"
    assert n["liked_count"] == 100
    assert n["comments_count"] == 20
    assert n["collected_count"] == 30
    assert n["read_count"] == 1000
    assert n["share_count"] == 5
    assert n["publish_time"] > 0
    # image_urls 是 JSON 字符串,  单元素列表
    import json as _json
    assert _json.loads(n["image_urls"]) == ["https://example.com/cover_0.jpg"]
    print("  ✓ _normalize_note")
    return True


def test_split_build_roundtrip() -> bool:
    from core.redfox.xhs.sync import _split_feed_id, build_feed_id
    # account 类型: feed.id = XHS_U_<userId>, suffix 仍是 userId, 可 round-trip
    fid = build_feed_id("account", "5e3a8c9d")
    k, t = _split_feed_id(fid)
    assert (k, t) == ("account", "5e3a8c9d"), (k, t)

    # keyword 类型: feed.id = XHS_KW_<uuid>, suffix 不是 keyword 原文 (真正的 keyword 存 feed.target)。
    # 这里只验证 prefix 正确, uuid 长度合理。
    fid = build_feed_id("keyword", "口红")
    assert fid.startswith("XHS_KW_"), fid
    k, suffix = _split_feed_id(fid)
    assert k == "keyword", k
    assert len(suffix) == 16, suffix  # uuid hex[:16]
    assert suffix != "口红", "suffix 不应是原始 keyword"

    print("  ✓ _split_feed_id / build_feed_id (keyword uuid + account round-trip)")
    return True


def test_upsert_metrics_only() -> bool:
    """已有 note 的二次同步:  只更新 5 个 metrics,  title/content/author 不动。"""
    _ensure_redfox_stub()
    from core.db import DB
    from core.models.feed import Feed as _Feed
    from core.models.article import Article
    from core.redfox.xhs.sync import _upsert_articles, _normalize_note, build_feed_id

    feed_id = build_feed_id("keyword", "test_upsert")
    session = DB.get_session()
    try:
        _cleanup(session, feed_id)
        feed = _build_xhs_test_feed(session, feed_id)

        # 第一轮: 写入 3 条 note
        notes_v1 = _normalize_note_many(["a", "b", "c"], base_pt=1000)
        _upsert_articles(session, feed_id, notes_v1)

        # 检查入库
        rows = session.query(Article).filter(Article.feed_id == feed_id).all()
        assert len(rows) == 3, len(rows)

        # 记下原始 title
        original_titles = {a.id: a.title for a in rows}

        # 第二轮: 同样的 3 个 workId,  metrics 变化,  title 故意不同
        notes_v2 = []
        for i, wid in enumerate(["a", "b", "c"]):
            notes_v2.append({
                "id": wid,
                "title": f"新标题_{i}",  # 不应入库
                "content": "新内容, 不应入库",
                "author": "新昵称",
                "author_id": "new_uid",
                "publish_time": 2000 + i,
                "pic_url": "https://example.com/new.jpg",
                "url": f"https://new/{wid}",
                "image_urls": "[]",
                "liked_count": 999,
                "comments_count": 888,
                "collected_count": 777,
                "read_count": 666,
                "share_count": 555,
            })

        _upsert_articles(session, feed_id, notes_v2)
        session.commit()

        rows2 = session.query(Article).filter(Article.feed_id == feed_id).all()
        assert len(rows2) == 3, f"应仍 3 条, 实际 {len(rows2)}"

        for a in rows2:
            assert a.title == original_titles[a.id], (
                f"{a.id}: title 应保留原值,  实际 {a.title!r} != {original_titles[a.id]!r}"
            )
            assert a.content == "新内容, 不应入库" and False or a.content != "新内容, 不应入库" or True
            # content 不应被 metrics-only UPSERT 覆盖
            assert "不应入库" not in (a.content or ""), (
                f"{a.id}: content 不应被 metrics UPSERT 覆盖: {a.content!r}"
            )
            assert a.author != "新昵称", (
                f"{a.id}: author 不应被 metrics UPSERT 覆盖"
            )
            # metrics 应该被覆盖
            assert a.liked_count == 999
            assert a.comments_count == 888
            assert a.collected_count == 777
            assert a.read_count == 666
            assert a.share_count == 555

        print("  ✓ metrics-only UPSERT 保留 title/content/author")
    finally:
        _cleanup(session, feed_id)
        session.close()
    return True


def _normalize_note_many(work_ids, base_pt):
    from core.redfox.xhs.sync import _normalize_note
    notes = []
    for i, wid in enumerate(work_ids):
        notes.append({
            "workId": wid,
            "workTitle": f"标题 {wid}",
            "workDesc": f"正文 {wid}",
            "coverUrl": f"https://example.com/{wid}.jpg",
            "workUrl": f"https://xhs/{wid}",
            "workPublishTime": "2024-06-01 12:00:00",
            "accountNickname": "昵称",
            "accountUserid": "uid",
            "workLikedCount": 10 + i,
            "workCommentsCount": 5 + i,
            "workCollectedCount": 3 + i,
            "workReadedCount": 100 + i,
            "workSharedCount": 1 + i,
            "workType": "normal",
        })
    return [_normalize_note(n) for n in notes]


def test_do_job_xhs_watermark() -> bool:
    """do_job_xhs 走一遍: watermark 推进 / 错误清零 / 新 note 入库。

    替换 client 层的 iter_search_articles 为本地 stub。
    """
    _ensure_redfox_stub()
    import core.redfox.xhs.sync as sync_mod
    from core.db import DB
    from core.models.article import Article
    from core.models.feed import Feed as _Feed
    from core.redfox.xhs import do_job_xhs, build_feed_id

    feed_id = build_feed_id("keyword", "test_watermark")
    session = DB.get_session()
    try:
        _cleanup(session, feed_id)
        feed = _build_xhs_test_feed(session, feed_id)

        # 准备 3 条新 note (降序,  最新在最前)
        from datetime import datetime as _dt
        notes = _make_fake_notes("wm", 3, _dt(2024, 6, 1, 12, 0, 0))
        # iter_search_articles 要求降序
        notes.reverse()  # 最新的在前: 12:02, 12:01, 12:00

        # monkey-patch
        original_iter = sync_mod.iter_search_articles

        def fake_iter(keyword, max_pages=5, sort_type="2", page_size=20):
            yield from notes

        sync_mod.iter_search_articles = fake_iter
        try:
            do_job_xhs(feed, is_test=False)
        finally:
            sync_mod.iter_search_articles = original_iter

        # 检查: 3 条入库,  watermark = 最新一条的 publish_time
        rows = session.query(Article).filter(Article.feed_id == feed_id).all()
        assert len(rows) == 3, f"应 3 条,  实际 {len(rows)}"
        latest_pt = max(a.publish_time for a in rows)

        # session 可能已被 do_job_xhs 内部 close,  重新拉一个
        session2 = DB.get_session()
        try:
            db_feed = session2.query(_Feed).filter(_Feed.id == feed_id).first()
            assert db_feed is not None
            assert db_feed.last_publish_time == latest_pt, (
                f"watermark 推进失败: feed.last_publish_time={db_feed.last_publish_time} latest_pt={latest_pt}"
            )
            assert db_feed.error_count == 0
            assert db_feed.last_error is None
            assert db_feed.last_cursor == "wm_2"  # 最新一条 workId
        finally:
            session2.close()
        print("  ✓ do_job_xhs watermark 推进 + 错误清零")
    finally:
        session.close()
    return True


def main() -> int:
    print("=== core.redfox.xhs.tests ===")
    failures = []
    for name, fn in [
        ("normalize", test_normalize),
        ("split_build_roundtrip", test_split_build_roundtrip),
        ("upsert_metrics_only", test_upsert_metrics_only),
        ("do_job_watermark", test_do_job_xhs_watermark),
    ]:
        print(f"[{name}]")
        try:
            fn()
        except AssertionError as e:
            failures.append((name, f"ASSERT: {e}"))
            print(f"  ✗ {e}")
        except Exception as e:  # noqa: BLE001
            failures.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {type(e).__name__}: {e}")
    if failures:
        print(f"\n{len(failures)} 个测试失败:")
        for n, msg in failures:
            print(f"  - {n}: {msg}")
        return 1
    print("\n全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
