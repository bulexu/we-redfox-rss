import copy
import importlib
import unittest

from core.redfox.tests_fields import _cases
from core.redfox.validation import validate_normalized
from core.redfox.wechat.client import normalize_fillback_item, normalize_item as normalize_wechat
from core.redfox.schema import ArticleSchema


class PlatformMappingTests(unittest.TestCase):
    def test_clients_own_mapping_and_preserve_raw_responses(self):
        for platform, raw, normalize in _cases():
            with self.subTest(platform=platform):
                self.assertEqual(normalize.__module__, f"core.redfox.{platform}.client")
                original = copy.deepcopy(raw)
                self.assertIsInstance(normalize(raw), ArticleSchema)
                self.assertEqual(validate_normalized(platform, normalize(raw).to_record()), [])
                self.assertEqual(raw, original)
                self.assertIsNone(normalize({}))

    def test_legacy_sync_imports_delegate_to_clients(self):
        names = {"douyin": "work", "bilibili": "work", "xhs": "note",
                 "x": "tweet", "tiktok": "video", "youtube": "video", "instagram": "post"}
        for platform, name in names.items():
            with self.subTest(platform=platform):
                client = importlib.import_module(f"core.redfox.{platform}.client")
                sync = importlib.import_module(f"core.redfox.{platform}.sync")
                self.assertEqual(getattr(sync, f"_normalize_{name}")({}), {})

    def test_wechat_retains_fillback_fields(self):
        raw = dict(workUuid="ab-cd", publishTime=1735689600, title="标题",
                   workUrl="https://example.com/article", summary="摘要", likeCount=5)
        original = raw.copy()
        self.assertIsInstance(normalize_wechat(raw), ArticleSchema)
        result = normalize_fillback_item(raw, "mp-test")
        self.assertEqual(result['id'], "abcd")
        self.assertEqual(result['aid'], "abcd")
        self.assertEqual(result['mp_id'], "mp-test")
        self.assertEqual(result['publish_time'], 1735689600)
        self.assertEqual(result['digest'], "摘要")
        self.assertEqual(result['like_count'], 5)
        self.assertEqual(raw, original)


if __name__ == '__main__':
    unittest.main()
