from types import SimpleNamespace
import unittest
from unittest.mock import patch

import jobs.lark_push as lark_jobs
import core.lark_push as lark_core


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return FakeQuery(self.rows)

    def close(self):
        pass


class FakeScheduler:
    def __init__(self):
        self.ids = ["other_job", "lark_auto_push_scan"]
        self.removed = []
        self.added = []
        self.started = False
        self._scheduler = SimpleNamespace(running=False)

    def get_job_ids(self):
        return list(self.ids)

    def remove_job(self, job_id):
        self.removed.append(job_id)
        if job_id in self.ids:
            self.ids.remove(job_id)
        return True

    def add_cron_job(self, func, cron_expr, kwargs, job_id, tag):
        self.added.append((cron_expr, kwargs, job_id, tag))
        self.ids.append(job_id)
        return job_id

    def start(self):
        self.started = True
        self._scheduler.running = True


class LarkPushScheduleTests(unittest.TestCase):
    def test_allowed_intervals_and_cron(self):
        for hours in (1, 2, 4, 6, 12, 24):
            self.assertEqual(lark_jobs._normalize_interval_hours(hours), hours)
        self.assertEqual(lark_jobs._hours_to_cron(1), "0 */1 * * *")
        self.assertEqual(lark_jobs._hours_to_cron(6), "0 */6 * * *")
        self.assertEqual(lark_jobs._hours_to_cron(24), "0 0 * * *")

    def test_each_enabled_bitable_gets_its_own_job(self):
        rows = [
            SimpleNamespace(id="table-1", name="一小时表", push_interval_hours=1),
            SimpleNamespace(id="table-24", name="每日表", push_interval_hours=24),
        ]
        scheduler = FakeScheduler()
        fake_db = SimpleNamespace(get_session=lambda: FakeSession(rows))
        fake_cfg = SimpleNamespace(
            get=lambda key, default=None: True if key == "lark.enabled" else default
        )
        with (
            patch.object(lark_jobs, "_scheduler", scheduler),
            patch.object(lark_jobs, "DB", fake_db),
            patch.object(lark_jobs, "cfg", fake_cfg),
        ):
            lark_jobs.start_lark_push_scheduler()

        self.assertEqual(scheduler.removed, ["lark_auto_push_scan"])
        self.assertIn("other_job", scheduler.ids)
        self.assertEqual(
            [(item[0], item[1], item[2]) for item in scheduler.added],
            [
                ("0 */1 * * *", {"bitable_id": "table-1"}, "lark_auto_push_table-1"),
                ("0 0 * * *", {"bitable_id": "table-24"}, "lark_auto_push_table-24"),
            ],
        )
        self.assertTrue(scheduler.started)

    def test_bitable_batch_keeps_article_order_and_target(self):
        calls = []

        class ImmediateExecutor:
            def submit(self, func, *args):
                func(*args)

        fake_cfg = SimpleNamespace(get=lambda key, default=None: True)
        with (
            patch.object(lark_core, "cfg", fake_cfg),
            patch.object(lark_core, "_get_executor", return_value=ImmediateExecutor()),
            patch.object(
                lark_core,
                "_push_article_job",
                side_effect=lambda article_id, bitable_id=None: calls.append(
                    (article_id, bitable_id)
                ),
            ),
        ):
            lark_core.lark_push_bitable_batch(["old", "middle", "new"], "table-1")

        self.assertEqual(calls, [
            ("old", "table-1"),
            ("middle", "table-1"),
            ("new", "table-1"),
        ])


if __name__ == "__main__":
    unittest.main()
