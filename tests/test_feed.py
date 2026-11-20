"""Save-to-search behaviour, with isolated storage and mocked model providers."""
import json
from pathlib import Path
import queue
from unittest.mock import patch
import unittest
import test_app as fixture
app=fixture.app

class FeedTests(unittest.TestCase):
    setUp_base=fixture.WorkflowTests.setUp
    tearDown_base=fixture.WorkflowTests.tearDown
    post=fixture.WorkflowTests.post
    def setUp(self):
        self.setUp_base();self.old_queue=app.JOBS;app.JOBS=queue.Queue(maxsize=20)
        self.video=app.DATA/'fixture.mp4';self.video.write_bytes(b'\x00\x00\x00\x18ftypmp42fixture')
        self.item={'id':'f'+'1'*31,'title':'Paneer cooking clip','topic':'Food','duration':10,'mime':'video/mp4','created':0,'credit':'Test fixture','silent':False,'source_url':'','_media':self.video,'_poster':None,'saved_id':'','status':'','error':'','search_ready':False,'media_url':'/feed-media/'+'f'+'1'*31,'poster_url':''}
        self.catalog=patch.object(app,'feed_catalog',return_value=[self.item]);self.catalog.start()
        self.note=app.manual_recipe(app.SAMPLES[0][1]);self.vector=[1.]+[0.]*767
    def tearDown(self):
        self.catalog.stop();app.JOBS=self.old_queue
        with app.KEY_LOCK:app.KEYS.clear()
        self.tearDown_base()
    def save(self,**extra):
        return self.post('/api/feed/save',{'id':self.item['id'],'api_key':'TEST_ONLY','collections':['food'],**extra},202)
    def process(self,jid):
        with patch.object(app,'extract_live',return_value=(self.note,{})) as extract,patch.object(app,'embed',return_value=self.vector) as embedding:
            app.process(jid)
        return extract,embedding
    def test_feed_browsing_does_not_create_saves_or_call_models(self):
        import urllib.request
        with patch.object(app,'embed') as embedding,patch.object(app,'extract_live') as extract:
            with urllib.request.urlopen(self.base+'/api/feed') as r:body=json.load(r)
        self.assertEqual(len(body['items']),1);self.assertNotIn('_media',body['items'][0])
        with app.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        extract.assert_not_called();embedding.assert_not_called()
    def test_save_automatically_extracts_embeds_and_becomes_searchable(self):
        result=self.save();jid=result['id'];self.assertEqual(result['status'],'queued')
        self.assertEqual(app.search('paneer')['results'],[])
        extract,embedding=self.process(jid);extract.assert_called_once();embedding.assert_called_once()
        r=app.get_job(jid);self.assertEqual(r['status'],'approved');self.assertTrue(r['embedding'])
        public=app.public_job(r);self.assertTrue(public['search_ready']);self.assertTrue(public['auto_index'])
        self.assertIn('AI generated',public['note_review']);self.assertEqual(len(app.search('paneer')['results']),1)
        self.assertEqual([c['id'] for c in public['collections']],['food'])
    def test_embedding_failure_is_not_ready_and_retry_reuses_extraction(self):
        jid=self.save()['id']
        with patch.object(app,'extract_live',return_value=(self.note,{})),patch.object(app,'embed',side_effect=ValueError('Embedding quota reached')):app.process(jid)
        r=app.get_job(jid);self.assertEqual(r['status'],'failed');self.assertTrue(r['recipe']);self.assertFalse(app.public_job(r)['search_ready'])
        self.assertEqual(app.search('paneer')['results'],[])
        retry=self.save();self.assertEqual(retry['id'],jid)
        extract,embedding=self.process(jid);extract.assert_not_called();embedding.assert_called_once()
        self.assertTrue(app.public_job(app.get_job(jid))['search_ready'])
    def test_saving_again_updates_collections_without_reprocessing(self):
        jid=self.save()['id'];self.process(jid)
        with patch.object(app,'embed') as embedding,patch.object(app,'extract_live') as extract:
            result=self.save(api_key='',collections=['food','travel'])
        self.assertEqual(result['id'],jid);self.assertTrue(result['duplicate'])
        self.assertEqual(len(app.public_job(app.get_job(jid))['collections']),2)
        extract.assert_not_called();embedding.assert_not_called()
        with app.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
    def test_missing_key_invalid_collection_and_missing_video_do_not_create_jobs(self):
        with patch.dict(app.os.environ,{},clear=True):self.post('/api/feed/save',{'id':self.item['id'],'collections':['food']},400)
        self.post('/api/feed/save',{'id':self.item['id'],'api_key':'TEST_ONLY','collections':['missing']},400)
        self.post('/api/feed/save',{'id':'missing','api_key':'TEST_ONLY'},400)
        with app.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
    def test_upload_adds_only_to_feed_and_validates_file(self):
        import base64
        self.post('/api/feed/upload',{'filename':'A clip','mime':'video/mp4','data':base64.b64encode(self.video.read_bytes()).decode()},201)
        with app.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM feed_uploads').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        self.post('/api/feed/upload',{'mime':'video/mp4','data':base64.b64encode(b'not a video').decode()},400)
