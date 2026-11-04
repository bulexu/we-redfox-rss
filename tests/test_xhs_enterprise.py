import copy
import os
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models.article import Article
from core.redfox.schema import ArticleSchema
from core.redfox.validation import get_reports, reset_reports
from core.redfox.xhs.client import XhsClient, REALTIME_SEARCH_PATH, normalize_item
from core.redfox.xhs.sync import _upsert_articles


NOTE = {
    'authorAvatar': 'https://example.com/avatar', 'authorName': '汤姆的日记',
    'authorUid': '6368ef18000000001f01cbdb',
    'coverImage': 'https://example.com/cover?format/heif',
    'favoriteCount': 7, 'forwardCount': 10, 'noteId': '6a3077960000000015025975',
    'noteTitle': '6.16美股热门基最新播报！宝子们幸福了', 'noteType': 'normal',
    'noteUrl': 'https://www.xiaohongshu.com/discovery/item/6a3077960000000015025975',
    'picUrls': ['https://example.com/one?format/heif', 'https://example.com/two'],
    'previewUrls': ['https://example.com/preview?format/heif'],
    'releaseTime': '2026-06-16 06:07:18', 'replyCount': 13, 'thumbCount': 18,
}


class XhsEnterpriseTests(unittest.TestCase):
    def client(self, pages):
        client = object.__new__(XhsClient)
        client._sdk = Mock()
        client._sdk.post.side_effect = pages
        client._record_call = Mock()
        return client

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'True'})
    def test_request_and_short_page_pagination(self):
        client = self.client([
            {'workList': [NOTE]},
            {'workList': [dict(NOTE, noteId='second', noteType='video')]},
            {'workList': []},
        ])
        articles = list(client.iter_search_articles(' A股 ', max_pages=5))
        self.assertEqual([a.id for a in articles], [NOTE['noteId'], 'second'])
        self.assertTrue(all(isinstance(a, ArticleSchema) for a in articles))
        self.assertEqual(articles[1].show_type, 5)
        calls = client._sdk.post.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args, (REALTIME_SEARCH_PATH,))
        self.assertEqual(calls[0].kwargs['data'], dict(note_type='不限', noteTime='不限', page=1, sort='最新', keyword='A股'))
        self.assertEqual(calls[1].kwargs['data']['page'], 2)
        client._sdk.xiaohongshu.search_articles.assert_not_called()

    def test_schema_maps_real_fields_without_claiming_body_content(self):
        original = copy.deepcopy(NOTE)
        reset_reports()
        article = normalize_item(NOTE)
        self.assertEqual(article.id, NOTE['noteId'])
        self.assertEqual(article.title, NOTE['noteTitle'])
        self.assertEqual(article.author, NOTE['authorName'])
        self.assertEqual(article.author_id, NOTE['authorUid'])
        self.assertEqual(article.url, NOTE['noteUrl'])
        self.assertEqual(article.content, '')
        self.assertEqual(article.description, '')
        self.assertEqual(article.show_type, 0)
        self.assertGreater(article.publish_time, 0)
        self.assertEqual((article.liked_count, article.comments_count, article.collected_count, article.share_count), (18, 13, 7, 10))
        self.assertEqual(article.read_count, 0)
        self.assertEqual(article.image_urls, ['https://example.com/one?format/webp', 'https://example.com/two'])
        self.assertEqual(article.extinfo['preview_urls'], ['https://example.com/preview?format/webp'])
        self.assertEqual(article.extinfo['author_avatar'], NOTE['authorAvatar'])
        self.assertFalse(get_reports())
        self.assertEqual(NOTE, original)

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'True'})
    def test_repeated_pages_and_explicit_end_stop(self):
        for pages, expected_calls in (
            ([{'workList': [NOTE]}, {'workList': [NOTE]}], 2),
            ([{'workList': [NOTE], 'hasMore': 0}], 1),
            ([{'workList': [NOTE]}], 1),
        ):
            client = self.client(pages)
            result = list(client.iter_search_articles('test', max_pages=len(pages)))
            self.assertEqual(len(result), 1)
            self.assertEqual(client._sdk.post.call_count, expected_calls)

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'False'})
    def test_legacy_request_remains_unchanged(self):
        client = self.client([])
        client._sdk.xiaohongshu.search_articles.return_value = {'list': []}
        client.search_articles('test', page=2, sort='最新')
        client._sdk.post.assert_not_called()
        client._sdk.xiaohongshu.search_articles.assert_called_once_with(keyword='test', offset=20, sort_type='2')

    @patch.dict(os.environ, {'REDFOX_ENTERPRISE': 'True'})
    def test_account_endpoint_does_not_switch(self):
        client = self.client([])
        client._sdk.xiaohongshu.get_user_works.return_value = {'list': []}
        client.get_user_works('user')
        client._sdk.post.assert_not_called()
        client._sdk.xiaohongshu.get_user_works.assert_called_once()

    def test_realtime_schema_stores_missing_body_as_empty(self):
        engine = create_engine('sqlite:///:memory:')
        Article.__table__.create(engine)
        session = sessionmaker(bind=engine)()
        try:
            article = normalize_item(NOTE)
            _upsert_articles(session, 'XHS_KW_test', [article.to_record()])
            session.commit()
            stored = session.query(Article).filter_by(id=article.id).one()
            self.assertEqual(stored.content, '')
            self.assertEqual(stored.has_content, 0)
            self.assertEqual(stored.show_type, 0)
            self.assertEqual(stored.liked_count, 18)
        finally:
            session.close()
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
