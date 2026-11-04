import os
import unittest
from unittest.mock import Mock, patch

from core.redfox.bilibili.client import BilibiliClient, REALTIME_SEARCH_PATH, SEARCH_WORKS_PATH, normalize_item
from core.redfox.schema import ArticleSchema
from core.redfox.validation import get_reports, reset_reports


WORK = dict(
    avId=33729980, bvId='BV1jb411F7BN', avatar='http://i2.hdslb.com/avatar.jpg',
    categoryId='21', categoryName='日常', collectNum=14654, commentNum=128,
    cover='//i2.hdslb.com/cover.jpg', danmakuCount=323, description='衣服的折叠方法',
    duration='332', likeNum=8866, nickname='妙招姐', publishTime=1539509605,
    tags='叠衣服,叠羽绒服,日常', title='教你<em class="keyword">冬装</em>收纳 &amp; 技巧',
    totalDanmakuCount=323, type='video', url='http://www.bilibili.com/video/av33729980', viewNum=304883,
)


class BilibiliEnterpriseTests(unittest.TestCase):
    def client(self, pages):
        client = object.__new__(BilibiliClient)
        client._sdk = Mock()
        client._sdk.post.side_effect = pages
        client._record_call = Mock()
        return client

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'True'})
    def test_enterprise_uses_documented_parameters_and_sorts(self):
        for order in ('', 'pubdate', 'click', 'dm', 'stow'):
            with self.subTest(order=order):
                client = self.client([{}])
                client.search_works(' 冬装 ', page=2, order=order)
                payload = dict(keyword='冬装', page='2')
                if order:
                    payload['order'] = order
                client._sdk.post.assert_called_once_with(REALTIME_SEARCH_PATH, data=payload)

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'True'})
    def test_short_pages_follow_total_pages_and_yield_schemas(self):
        client = self.client([
            dict(opusInfoList=[WORK], page=1, pages=2),
            dict(opusInfoList=[dict(WORK, bvId='BV-second')], page=2, pages=2),
        ])
        articles = list(client.iter_search_works('冬装', max_pages=5))
        self.assertEqual([a.id for a in articles], [WORK['bvId'], 'BV-second'])
        self.assertTrue(all(isinstance(a, ArticleSchema) for a in articles))
        self.assertEqual(client._sdk.post.call_count, 2)
        self.assertEqual(client._sdk.post.call_args.kwargs['data']['page'], '2')

    def test_realtime_mapping_has_no_false_missing_author_warning(self):
        reset_reports()
        article = normalize_item(WORK)
        self.assertEqual(article.title, '教你冬装收纳 & 技巧')
        self.assertEqual(article.content, WORK['description'])
        self.assertEqual(article.author, '妙招姐')
        self.assertIsNone(article.author_id)
        self.assertEqual(article.publish_time, 1539509605)
        self.assertEqual(article.url, 'https://www.bilibili.com/video/av33729980')
        self.assertEqual(article.pic_url, 'https://i2.hdslb.com/cover.jpg')
        self.assertEqual(article.extinfo['author_avatar'], 'https://i2.hdslb.com/avatar.jpg')
        self.assertEqual(article.extinfo['duration'], 332)
        self.assertEqual(article.extinfo['tags'], ['叠衣服', '叠羽绒服', '日常'])
        self.assertEqual((article.liked_count, article.collected_count, article.comments_count, article.read_count), (8866, 14654, 128, 304883))
        self.assertFalse(get_reports())

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'False'})
    def test_legacy_request_is_preserved(self):
        client = self.client([{}])
        client.search_works('test', order='pubdate')
        client._sdk.post.assert_called_once_with(SEARCH_WORKS_PATH, data=dict(keyword='test', exactMatch=False, page='1', pageSize=20, order='time'))

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'True'})
    def test_empty_repeated_and_page_limit_stop(self):
        for pages, max_pages, count in (
            ([{'opusInfoList': []}], 5, 0),
            ([{'opusInfoList': [WORK]}, {'opusInfoList': [WORK]}], 5, 1),
            ([{'opusInfoList': [WORK]}], 1, 1),
        ):
            with self.subTest(pages=len(pages), max_pages=max_pages):
                client = self.client(pages)
                self.assertEqual(len(list(client.iter_search_works('test', max_pages=max_pages))), count)
                self.assertEqual(client._sdk.post.call_count, len(pages))


if __name__ == '__main__':
    unittest.main()
