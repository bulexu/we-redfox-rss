import copy
import importlib
import json
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models.article import Article
from core.redfox.schema import ArticleSchema
from core.redfox.tests_fields import _cases
from core.redfox.douyin.client import DouyinClient, normalize_item
from core.redfox.douyin.sync import _fetch_works, _upsert_articles


class ArticleSchemaTests(unittest.TestCase):
    def test_schema_validates_and_serializes_only_at_storage_boundary(self):
        article = ArticleSchema(id="1", image_urls=["https://example.com/image"], extinfo={"platform": "dy"})
        self.assertIsInstance(article.image_urls, list)
        self.assertIsInstance(article.extinfo, dict)
        record = article.to_record()
        self.assertEqual(json.loads(record['image_urls']), article.image_urls)
        self.assertEqual(ArticleSchema.from_record(record), article)
        self.assertEqual(ArticleSchema(id="2").extinfo, {})
        for values in ({"id": ""}, {"id": "1", "publish_time": "bad"}, {"id": "1", "unknown": 2}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ArticleSchema(**values)

    @patch.dict('os.environ', {"REDFOX_ENTERPRISE": "False"})
    def test_all_platform_iterators_yield_schema_and_skip_missing_ids(self):
        settings = {
            'douyin': ('DouyinClient', 'iter_search_articles', 'search_articles', 'list'),
            'bilibili': ('BilibiliClient', 'iter_search_works', 'search_works', 'workList'),
            'xhs': ('XhsClient', 'iter_search_articles', 'search_articles', 'list'),
            'x': ('XClient', 'iter_search_tweets', 'search_tweets', 'tweets'),
            'tiktok': ('TikTokClient', 'iter_search_videos', 'search_videos', 'list'),
            'youtube': ('YouTubeClient', 'iter_search_videos', 'search_videos', 'videos'),
            'instagram': ('InstagramClient', 'iter_search_posts', 'search_posts', 'items'),
        }
        for platform, raw, normalize in _cases():
            with self.subTest(platform=platform):
                cls_name, iterator, search, key = settings[platform]
                module = importlib.import_module(f'core.redfox.{platform}.client')
                client = object.__new__(getattr(module, cls_name))
                setattr(client, search, Mock(return_value={key: [copy.deepcopy(raw), {}]}))
                articles = list(getattr(client, iterator)('keyword', max_pages=1))
                self.assertEqual(articles, [normalize(raw)])
                self.assertIsInstance(articles[0], ArticleSchema)
        from core.redfox.xhs.client import XhsClient
        client = object.__new__(XhsClient)
        client.get_user_works = Mock(return_value={'list': [_cases()[0][1]], 'hasMore': 0})
        self.assertIsInstance(next(iter(client.iter_user_works('user'))), ArticleSchema)
        from core.redfox.wechat.client import WechatClient
        client = object.__new__(WechatClient)
        client.query_work_list = Mock(return_value={'list': [{'workUuid': 'ab-cd', 'title': '文章'}]})
        self.assertIsInstance(next(iter(client.iter_work_list(account='test'))), ArticleSchema)

    def test_douyin_both_interfaces_map_same_fields_and_preserve_metadata(self):
        common = dict(videoId="123", content="正文", publishTime="2026-06-11 10:00:05",
                      authorUid="456", authorName="作者", coverUrl="https://example.com/cover",
                      likeCount=10, collectCount=20, commentCount=30, shareCount=40, duration=19329)
        legacy = normalize_item(dict(common, opusUrl="https://example.com/share", videoType="0",
                                     authorAvatarUrl="https://example.com/avatar", authorUniqueId="account"))
        realtime = normalize_item(dict(common, videoUrl="https://example.com/play", videoType=0,
                                       publishTime="2026-06-11 10: 00: 05",
                                       authorAvatar="https://example.com/avatar", authorAccount="account",
                                       isDeleted=False, authorFansCount=100, forwardCount=2))
        for name in ('id', 'content', 'author_id', 'publish_time', 'liked_count', 'show_type'):
            self.assertEqual(getattr(legacy, name), getattr(realtime, name))
        self.assertEqual(legacy.extinfo['author_account'], realtime.extinfo['author_account'])
        self.assertEqual(legacy.extinfo['video_url'], '')
        self.assertEqual(realtime.extinfo['video_url'], realtime.url)
        self.assertFalse(realtime.extinfo['is_deleted'])
        images = ['https://example.com/1', 'https://example.com/2']
        graphic = normalize_item(dict(common, videoType='68', imageUrlList=images))
        self.assertEqual(graphic.show_type, 0)
        self.assertEqual(graphic.image_urls, images)

    @patch.dict('os.environ', {"REDFOX_ENTERPRISE": "False"})
    def test_douyin_uses_response_page_size(self):
        client = object.__new__(DouyinClient)
        client.search_articles = Mock(side_effect=[
            {'list': [{'videoId': '1'}], 'pageNum': 1, 'pageSize': 1, 'total': 2},
            {'list': [{'videoId': '2'}], 'pageNum': 2, 'pageSize': 1, 'total': 2},
        ])
        self.assertEqual([a.id for a in client.iter_search_articles('test', max_pages=5, page_size=20)], ['1', '2'])
        self.assertEqual(client.search_articles.call_count, 2)

    def test_douyin_sync_stores_client_schema_without_remapping(self):
        article = normalize_item(dict(videoId='schema-insert', content='图文', videoType='68',
                                      authorName='作者', imageUrlList=['https://example.com/image'],
                                      publishTime='2026-06-11 10:00:05', likeCount=10))
        with patch('core.redfox.douyin.sync.iter_search_articles', return_value=iter([article])):
            records = _fetch_works('test', 0, 20)
        engine = create_engine('sqlite:///:memory:')
        Article.__table__.create(engine)
        session = sessionmaker(bind=engine)()
        try:
            _upsert_articles(session, 'DY_KW_test', records)
            session.commit()
            stored = session.query(Article).filter_by(id=article.id).one()
            self.assertEqual(stored.content, article.content)
            self.assertEqual(stored.show_type, 0)
            self.assertEqual(json.loads(stored.image_urls), article.image_urls)
            self.assertEqual(json.loads(stored.extinfo), article.extinfo)
        finally:
            session.close()
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
