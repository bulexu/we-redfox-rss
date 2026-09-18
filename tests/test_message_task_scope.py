from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import jobs.mps as mps
from core.models.feed import Feed


def task(**overrides):
    values = {
        "id": "scope-test",
        "scope_type": "legacy",
        "target_feed_ids": "[]",
        "target_platforms": "[]",
        "platform": "wechat",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class MessageTaskScopeTests(unittest.TestCase):
    def test_resolve_all_platforms_and_custom_scopes(self):
        scope, platforms, feed_ids = mps.resolve_task_scope(task(scope_type="all"))
        self.assertEqual(scope, "all")
        self.assertEqual(platforms, list(mps.SUPPORTED_TASK_PLATFORMS))
        self.assertEqual(feed_ids, [])

        result = mps.resolve_task_scope(
            task(scope_type="platforms", target_platforms='["dy", "youtube"]')
        )
        self.assertEqual(result, ("platforms", ["dy", "youtube"], []))

        result = mps.resolve_task_scope(
            task(scope_type="custom", target_feed_ids='[{"id": "DY_KW_1"}]')
        )
        self.assertEqual(result, ("custom", [], ["DY_KW_1"]))

    def test_legacy_global_task_stays_on_its_original_platform(self):
        self.assertEqual(
            mps.resolve_task_scope(task(platform="xhs"))[:2],
            ("platforms", ["xhs"]),
        )
        self.assertEqual(
            mps.resolve_task_scope(
                task(platform="wechat", target_feed_ids='[{"id": "MP_WXS_1"}]')
            ),
            ("custom", [], ["MP_WXS_1"]),
        )

    def test_unknown_legacy_feed_is_inferred_from_its_id(self):
        legacy_xhs = SimpleNamespace(
            id="XHS_KW_legacy", platform="unknown"
        )
        self.assertEqual(mps._effective_feed_platform(legacy_xhs), "xhs")

    def test_real_feed_query_for_all_platform_and_custom_scopes(self):
        engine = create_engine("sqlite:///:memory:")
        Feed.__table__.create(engine)
        session_factory = sessionmaker(bind=engine)
        session = session_factory()
        session.add_all([
            Feed(id="MP_WXS_1", name="公众号", platform="mp", status=1),
            Feed(id="DY_KW_1", name="抖音", platform="dy", status=1),
            Feed(id="DY_KW_OFF", name="停用抖音", platform="dy", status=0),
            Feed(id="YOUTUBE_KW_1", name="YouTube", platform="youtube", status=1),
            # 模拟升级前 platform 未正确回填的旧小红书数据。
            Feed(id="XHS_KW_OLD", name="旧小红书", platform="unknown", status=1),
        ])
        session.commit()
        session.close()

        fake_db = SimpleNamespace(get_session=lambda: session_factory())
        with patch.object(mps.db, "DB", fake_db):
            grouped = mps.resolve_task_feeds(task(scope_type="all"))
            self.assertEqual(
                {key: [feed.id for feed in value] for key, value in grouped.items()},
                {
                    "mp": ["MP_WXS_1"],
                    "dy": ["DY_KW_1"],
                    "youtube": ["YOUTUBE_KW_1"],
                    "xhs": ["XHS_KW_OLD"],
                },
            )

            grouped = mps.resolve_task_feeds(
                task(scope_type="platforms", target_platforms='["dy", "youtube"]')
            )
            self.assertEqual(set(grouped), {"dy", "youtube"})
            self.assertEqual([feed.id for feed in grouped["dy"]], ["DY_KW_1"])

            grouped = mps.resolve_task_feeds(
                task(
                    scope_type="custom",
                    target_feed_ids=(
                        '[{"id":"MP_WXS_1"},{"id":"XHS_KW_OLD"},'
                        '{"id":"DY_KW_OFF"}]'
                    ),
                )
            )
            self.assertEqual(set(grouped), {"mp", "xhs"})
        engine.dispose()

    def test_dispatch_groups_platforms_without_fetching(self):
        calls = []

        def fake_dispatcher(platform):
            def dispatch(feeds=None, task=None, isTest=False):
                calls.append((platform, [getattr(item, "id", item) for item in feeds]))
            return dispatch

        grouped = {
            "mp": [SimpleNamespace(id="MP_WXS_1")],
            "dy": [SimpleNamespace(id="DY_KW_1")],
            "youtube": [SimpleNamespace(id="YOUTUBE_KW_1")],
        }
        dispatchers = {
            "add_job": "mp",
            "add_xhs_job": "xhs",
            "add_douyin_job": "dy",
            "add_bilibili_job": "bili",
            "add_x_job": "x",
            "add_tiktok_job": "tiktok",
            "add_youtube_job": "youtube",
            "add_instagram_job": "instagram",
        }
        patches = [patch.object(mps, "resolve_task_feeds", return_value=grouped)]
        patches.extend(
            patch.object(mps, name, fake_dispatcher(platform))
            for name, platform in dispatchers.items()
        )
        for current_patch in patches:
            current_patch.start()
        try:
            self.assertEqual(
                mps.dispatch_scheduled_task(task(), isTest=False),
                ["mp", "dy", "youtube"],
            )
        finally:
            for current_patch in reversed(patches):
                current_patch.stop()

        self.assertEqual(calls, [
            ("mp", ["MP_WXS_1"]),
            ("dy", ["DY_KW_1"]),
            ("youtube", ["YOUTUBE_KW_1"]),
        ])


if __name__ == "__main__":
    unittest.main()
