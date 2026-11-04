import os
import unittest
from unittest.mock import Mock, patch

from core.redfox.base import enterprise_enabled
from core.redfox.douyin.client import DouyinClient, REALTIME_SEARCH_PATH, SEARCH_ARTICLES_PATH
from core.redfox.douyin.client import normalize_item
from core.redfox.validation import get_reports, reset_reports


class EnterpriseTests(unittest.TestCase):
    def client(self, pages):
        client = object.__new__(DouyinClient)
        client._sdk = Mock()
        client._sdk.post.side_effect = pages
        client._record_call = Mock()
        return client

    @patch.dict(os.environ, {"REDFOX_ENTERPRISE": "True"})
    def test_cursor_and_response_mapping(self):
        work = dict(videoId="123", content="正文", publishTime="2026-06-11 10:00:05",
                    videoUrl="https://example.com/video", coverUrl="https://example.com/cover",
                    authorUid="456", authorName="作者", duration=19329,
                    likeCount=6739, collectCount=585, commentCount=285, shareCount=173)
        client = self.client([
            {"videoList": [work], "hasMore": 1, "nextOffset": "27"},
            {"videoList": [dict(work, videoId="124")], "hasMore": 0},
        ])
        items = list(client.iter_search_articles("测试", max_pages=5))
        self.assertEqual(len(items), 2)  # 短页仍按 hasMore 翻页
        calls = client._sdk.post.call_args_list
        self.assertEqual(calls[0].args, (REALTIME_SEARCH_PATH,))
        self.assertEqual(calls[0].kwargs['data'], dict(queryWord="测试", sort="2", timeRange="0", offset="0"))
        self.assertEqual(calls[1].kwargs['data']['offset'], "27")
        reset_reports()
        item = normalize_item(work).to_record()
        self.assertEqual(item['id'], "123")
        self.assertEqual(item['url'], work['videoUrl'])
        self.assertEqual(item['author_id'], "456")
        self.assertEqual(item['liked_count'], 6739)
        self.assertGreater(item['publish_time'], 0)
        self.assertEqual(get_reports().get('douyin', {}).get('issues', 0), 0)

    @patch.dict(os.environ, {"REDFOX_ENTERPRISE": "true"})
    def test_dates_and_repeated_cursor(self):
        client = self.client([{"videoList": [{"publishTime": "2026-01-01"}],
                               "hasMore": 1, "nextOffset": "0"}])
        self.assertEqual(list(client.iter_search_articles("测试", start_date="2026-06-01")), [])
        self.assertEqual(client._sdk.post.call_count, 1)

    @patch.dict(os.environ, {"REDFOX_ENTERPRISE": "False"})
    def test_legacy(self):
        self.assertFalse(enterprise_enabled())
        client = self.client([{"list": []}])
        client.search_articles("测试", page_num=2, start_date="2026-01-01")
        call = client._sdk.post.call_args
        self.assertEqual(call.args, (SEARCH_ARTICLES_PATH,))
        self.assertEqual(call.kwargs['data']['pageNum'], 2)
        self.assertEqual(call.kwargs['data']['startDate'], "2026-01-01")


if __name__ == '__main__':
    unittest.main()
