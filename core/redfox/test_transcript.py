import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.redfox.transcript import backfill_transcripts, enrich_direct_transcripts, enqueue_transcripts, extract_text, fetch_transcript, preserve_transcript


class TranscriptTests(unittest.TestCase):
    def test_switch_and_xhs_type(self):
        items = [dict(id=str(i), title='title', extinfo=json.dumps(meta)) for i, meta in enumerate([
            {'platform': 'xhs', 'work_type': 'normal'},
            {'platform': 'xhs', 'work_type': 'video'},
            {'platform': 'dy'}, {'platform': 'youtube'}, {'platform': 'x'},
        ])]
        with patch('core.queue.ContentTaskQueue.add_task', return_value=False) as add:
            with patch.dict(os.environ, REDFOX_CONVERT_VIDEO='False'):
                enqueue_transcripts(items)
                add.assert_not_called()
            with patch.dict(os.environ, REDFOX_CONVERT_VIDEO='True'):
                enqueue_transcripts(items)
                self.assertEqual(add.call_count, 3)

    def test_worker_platforms_and_resume(self):
        for platform, endpoint in [('dy', 'douyin'), ('xhs', 'xiaohongshu'), ('bili', 'bilibili')]:
            with self.subTest(platform=platform):
                article = SimpleNamespace(id='a', status=1, url='https://example.com/video',
                                          extinfo=json.dumps({'platform': platform}),
                                          description='原介绍', content='原介绍')
                session = MagicMock()
                session.query.return_value.filter.return_value.first.return_value = article
                client = MagicMock()
                client._sdk_call.side_effect = lambda path, payload, op: op()
                api = getattr(client._sdk, endpoint)
                api.transcript_submit.return_value = {'taskId': 'remote-id'}
                api.transcript_result.side_effect = [{'status': 'processing'}, {'status': 'success', 'text': '口播'}]
                api.get_transcript.return_value = {'segments': [{'text': '口播'}]}
                with patch('core.db.DB.get_session', return_value=session), patch('core.redfox.base._get_client_for', return_value=client), patch('core.redfox.transcript.time.sleep'):
                    fetch_transcript('a')
                    self.assertEqual(article.content, '原介绍\n\n口播')
                    self.assertEqual(json.loads(article.extinfo)['video_transcript'], '口播')
                    fetch_transcript('a')
                    if platform != 'youtube':
                        api.transcript_submit.assert_called_once()
                        article.extinfo = json.dumps({'platform': platform, 'transcript_task_id': 'remote-id'})
                        api.transcript_result.side_effect = None
                        api.transcript_result.return_value = {'text': '重试结果'}
                        fetch_transcript('a')
                        api.transcript_submit.assert_called_once()

    def test_backfill_existing_articles_and_batch_limit(self):
        articles = [SimpleNamespace(id=str(i), title='旧视频', extinfo=json.dumps(meta))
                    for i, meta in enumerate([
                        {'platform': 'xhs', 'work_type': 'normal'},
                        {'platform': 'youtube', 'video_transcript': '已完成'},
                        {'platform': 'youtube'}, {'platform': 'dy'}, {'platform': 'bili'},
                    ])]
        session = MagicMock()
        session.query.return_value.filter.return_value.order_by.return_value.yield_per.return_value = articles
        with patch.dict(os.environ, REDFOX_CONVERT_VIDEO='True'), patch('core.db.DB.get_session', return_value=session), patch('core.queue.ContentTaskQueue.add_task', return_value=True) as add:
            try:
                self.assertEqual(backfill_transcripts(limit=1), 1)
                self.assertEqual(add.call_args.args[1], '3')
                add.assert_called_once()
            finally:
                from core.redfox.transcript import _pending
                _pending.clear()
        session.close.assert_called_once()

    def test_video_scheduler_independent_of_wechat_switch(self):
        import jobs.fetch_no_article as job
        settings = {'gather.content_auto_check': False, 'gather.content_auto_interval': 10}
        with patch.object(job.cfg, 'get', side_effect=lambda key, default=None: settings.get(key, default)), patch.dict(os.environ, REDFOX_CONVERT_VIDEO='True'), patch.object(job, 'scheduler') as scheduler, patch.object(job.ContentTaskQueue, 'add_task') as add:
            job.start_sync_content()
            scheduler.add_cron_job.assert_called_once()
            add.assert_called_once_with(backfill_transcripts, task_name='扫描待提取视频文案')

    def test_youtube_direct_subtitles_without_queue(self):
        item = dict(id='youtube_a', url='https://youtube.com/watch?v=a',
                    description='介绍', content='介绍', extinfo='{"platform":"youtube"}')
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        with patch.dict(os.environ, REDFOX_CONVERT_VIDEO='True'), patch('core.redfox.youtube.client.get_transcript', return_value={'segments': [{'text': '字幕'}]}) as get, patch('core.queue.ContentTaskQueue.add_task') as add:
            enrich_direct_transcripts(session, [item])
            get.assert_called_once_with(item['url'])
            self.assertEqual(item['content'], '介绍\n\n字幕')
            enqueue_transcripts([item])
            enqueue_transcripts([dict(item, extinfo='{"platform":"youtube"}')])
            add.assert_not_called()
            enrich_direct_transcripts(session, [item])
            get.assert_called_once()

    def test_direct_subtitles_disabled_or_failed(self):
        item = dict(id='youtube_a', url='url', content='介绍', extinfo='{"platform":"youtube"}')
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        with patch('core.redfox.youtube.client.get_transcript', side_effect=RuntimeError('无字幕')) as get:
            with patch.dict(os.environ, REDFOX_CONVERT_VIDEO='False'):
                enrich_direct_transcripts(session, [item])
                get.assert_not_called()
            with patch.dict(os.environ, REDFOX_CONVERT_VIDEO='True'):
                enrich_direct_transcripts(session, [item])
                self.assertEqual(item['content'], '介绍')

    def test_refresh_preserves_transcript(self):
        article = SimpleNamespace(content='完整文案', extinfo=json.dumps({'video_transcript': '口播', 'transcript_task_id': 'id'}))
        self.assertEqual(preserve_transcript(article, 'content', '介绍'), '完整文案')
        meta = json.loads(preserve_transcript(article, 'extinfo', '{"platform":"youtube"}'))
        self.assertEqual(meta['transcript_task_id'], 'id')
        self.assertEqual(extract_text({'data': {'segments': [{'text': '第一句'}, {'text': '第二句'}]}}), '第一句\n第二句')


if __name__ == '__main__':
    unittest.main()
