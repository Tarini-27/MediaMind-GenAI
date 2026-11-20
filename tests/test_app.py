"""Run: python3 -m unittest discover -s tests -v (no API key/network needed)."""
import copy
import base64
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('knowledge_app',Path(__file__).resolve().parents[1]/'app.py')
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        app.DATA=Path(self.temp.name)
        app.DB=app.DATA/'knowledge.sqlite3'
        app.init()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        app.PORT=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base='http://127.0.0.1:'+str(app.PORT)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.temp.cleanup()

    def post(self,path,body,expected=200,origin=None):
        headers={'Content-Type':'application/json','X-App-Request':'1'}
        if origin: headers['Origin']=origin
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status,expected)
                return json.load(response)
        except urllib.error.HTTPError as ex:
            self.assertEqual(ex.code,expected,ex.read().decode())
            return {}

    def sample(self):
        return app.load_samples()[0]

    def approve(self,jid,edits=None):
        body={'id':jid,'edits':edits or {}}
        preview=self.post('/api/review',body)
        return self.post('/api/approve',{**body,'approval_hash':preview['approval_hash']})

    def test_samples_are_drafts_and_only_approved_notes_are_searchable(self):
        jid=self.sample()
        before=self.post('/api/search',{'query':'paneer'})
        self.assertEqual(before['results'],[])
        self.approve(jid)
        after=self.post('/api/search',{'query':'paneer without an oven'})
        self.assertEqual(len(after['results']),1)
        self.assertEqual(after['results'][0]['job']['id'],jid)
        self.assertEqual(after['oven_filter'],'not_required')

    def test_no_oven_constraint_does_not_match_unrelated_recipes(self):
        ids=app.load_samples()
        for jid in ids:
            self.approve(jid)
        result=app.search('paneer without an oven')
        self.assertEqual(len(result['results']),1)
        self.assertEqual(result['results'][0]['job']['id'],ids[0])
        self.assertEqual(len(app.search('no oven')['results']),2)

    def test_changed_payload_invalidates_approval(self):
        jid=self.sample()
        preview=self.post('/api/review',{'id':jid,'edits':{}})
        self.post('/api/approve',{'id':jid,'edits':{'title':'Changed after review'},'approval_hash':preview['approval_hash']},400)
        self.assertEqual(app.get_job(jid)['status'],'review')
        self.approve(jid,{'title':'Changed after review'})
        self.assertEqual(app.get_job(jid)['status'],'approved')

    def test_approval_without_preview_and_replay_are_rejected(self):
        jid=self.sample()
        self.post('/api/approve',{'id':jid,'approval_hash':'fake'},400)
        self.approve(jid)
        self.post('/api/approve',{'id':jid,'approval_hash':'fake'},400)

    def test_manual_import_keeps_unknown_quantities_and_deduplicates(self):
        text='Title: Chickpea pan\nIngredients:\nChickpeas\nSteps:\nWarm the chickpeas in a pan.'
        a=self.post('/api/import',{'text':text,'mode':'manual'},202)
        app.process(a['id'])
        r=app.get_job(a['id']);recipe=json.loads(r['recipe'])
        self.assertEqual(r['status'],'review')
        self.assertEqual(recipe['ingredients'][0]['quantity'],'Not stated')
        self.assertEqual(recipe['oven_requirement'],'unknown')
        b=self.post('/api/import',{'text':text,'mode':'manual'},202)
        self.assertTrue(b['duplicate']);self.assertEqual(a['id'],b['id'])
        self.approve(a['id'])
        self.assertEqual(len(self.post('/api/search',{'query':'chickpea'})['results']),1)
        self.assertEqual(self.post('/api/search',{'query':'chickpea without oven'})['results'],[])

    def test_unverifiable_text_evidence_is_removed(self):
        raw=app.manual_recipe(app.SAMPLES[0][1])
        raw['ingredients'].append({'name':'Unstated butter','quantity':'2 tbsp','evidence_ids':['E99']})
        raw['evidence'].append({'id':'E99','quote':'Add 2 tbsp butter','timestamp':'','kind':'provided_text'})
        result=app.validate_recipe(raw,app.SAMPLES[0][1],strict_text=True)
        self.assertFalse(any(i['name']=='Unstated butter' for i in result['ingredients']))
        self.assertFalse(any(e['id']=='E99' for e in result['evidence']))

    def test_reviewer_edits_have_no_fabricated_evidence(self):
        jid=self.sample();r=app.get_job(jid)
        original=json.loads(r['recipe'])
        unchanged=app.edit_recipe(r,{'ingredients':original['ingredients'],'steps':original['steps']})
        self.assertFalse(unchanged['reviewer_edited'])
        edited=app.edit_recipe(r,{'ingredients':[{'name':'Paneer','quantity':'300 g'}]})
        self.assertTrue(edited['reviewer_edited'])
        self.assertEqual(edited['ingredients'][0]['evidence_ids'],[])

    def test_failed_live_import_is_visible_and_secrets_are_not_persisted(self):
        key='test-secret-not-real'
        jid=app.create_job('recipe','text/plain',None,'Recipe source','gemini',app.MODEL,key)['id']
        with patch.object(app,'api_request',side_effect=ValueError('Provider temporarily unavailable. HTTP 503.')):
            app.process(jid)
        r=app.get_job(jid)
        self.assertEqual(r['status'],'failed')
        self.assertIn('503',r['error'])
        with app.conn() as c:
            self.assertNotIn(key,str([tuple(x) for x in c.execute('SELECT * FROM jobs')]))
            self.assertNotIn(key,str([tuple(x) for x in c.execute('SELECT * FROM events')]))

    def test_live_extraction_path_with_mocked_provider(self):
        key='test-key'
        jid=app.create_job('source','text/plain',None,app.SAMPLES[0][1],'gemini',app.MODEL,key)['id']
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(app.manual_recipe(app.SAMPLES[0][1]))}]}}], 'usageMetadata':{'totalTokenCount':123}}
        with patch.object(app,'api_request',return_value=response) as call:
            app.process(jid)
            self.assertIn(':generateContent',call.call_args.args[0])
        r=app.get_job(jid)
        self.assertEqual(r['status'],'review')
        self.assertEqual(json.loads(r['metrics'])['usage']['totalTokenCount'],123)

    def test_semantic_search_uses_real_vector_branch_when_available(self):
        jid=self.sample();self.approve(jid)
        with app.conn() as c:
            c.execute('UPDATE jobs SET embedding=? WHERE id=?',(json.dumps([1,0,0]),jid))
        with patch.object(app,'embed',return_value=[1,0,0]), patch.object(app,'semantic_matches',return_value=[jid]):
            result=app.search('unusual wording',key='test-key',semantic=True)
        self.assertEqual(result['results'][0]['job']['id'],jid)
        self.assertEqual(result['search_mode'],'Hybrid BM25 + vector RRF')

    def test_specific_search_does_not_match_only_a_shared_cooking_word(self):
        ids=app.load_samples()
        for jid in ids:self.approve(jid)
        self.assertEqual(app.search('show me how to cook dragonfruit')['results'],[])
        self.assertEqual([x['job']['id'] for x in app.search('show me how to cook paneer')['results']],[ids[0]])

    def test_framing_words_do_not_add_unrelated_sources(self):
        ids=app.load_library_samples()
        for jid in ids:self.approve(jid)
        hits=app.search('give me something related to that quiet beach video')['results']
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]['job']['category'],'travel')
        self.assertEqual(app.search('a dog at a quiet beach')['results'],[])

    def test_semantic_search_rejects_unrelated_high_cosine_candidates(self):
        ids=app.load_samples()
        for jid in ids:self.approve(jid)
        with app.conn() as c:c.execute("UPDATE jobs SET embedding=? WHERE status='approved'",(json.dumps([1,0,0]),))
        with patch.object(app,'embed',return_value=[1,0,0]),patch.object(app,'semantic_matches',return_value=[ids[0]]):
            result=app.search('paneer dinner',key='test',semantic=True)
        self.assertEqual([x['job']['id'] for x in result['results']],[ids[0]])
        with patch.object(app,'embed',return_value=[1,0,0]),patch.object(app,'semantic_matches',return_value=[]):
            self.assertEqual(app.search('space shuttle launch',key='test',semantic=True)['results'],[])

    def test_semantic_fallback_does_not_admit_unchecked_vector_matches(self):
        ids=app.load_samples()
        for jid in ids:self.approve(jid)
        with app.conn() as c:c.execute("UPDATE jobs SET embedding=? WHERE status='approved'",(json.dumps([1,0,0]),))
        with patch.object(app,'embed',return_value=[1,0,0]),patch.object(app,'semantic_matches',side_effect=ValueError('Keyword-only fallback.')):
            result=app.search('space shuttle launch',key='test',semantic=True)
        self.assertEqual(result['results'],[])
        self.assertIn('fallback',result['warning'])

    def test_search_matches_original_filename_and_generic_recipe_scope(self):
        jid=self.sample();self.approve(jid)
        with app.conn() as c:c.execute('UPDATE jobs SET filename=? WHERE id=?',('my-kitchen-tutorial.webm',jid))
        self.assertEqual(app.search('kitchen tutorial')['results'][0]['job']['id'],jid)
        self.assertEqual(app.search('recipes')['results'][0]['job']['id'],jid)

    def test_semantic_concepts_do_not_require_shared_query_words(self):
        text='Title: Orange cat at a door\nCategory: lifestyle\nKey points:\nAn orange cat jumps at the handle and opens a door.'
        note=app.manual_recipe(text)
        jid='c'*32
        with app.conn() as c:
            c.execute("INSERT INTO jobs(id,digest,filename,mime,mode,model,status,stage,recipe,original_recipe,embedding,created,updated,topic) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,jid,'cat.webm','text/plain','demo','fixture','approved','Fixture',json.dumps(note),json.dumps(note),json.dumps([0,1,0]),1,1,'lifestyle'))
        self.assertNotIn('animal',app.tokens(app.document_text(note)))
        for query in ('animal','pet animal','an animal opening the entrance'):
            payload={'matches':[{'id':jid,'supporting_quote':'An orange cat jumps at the handle and opens a door.'}]}
            response={'candidates':[{'content':{'parts':[{'text':json.dumps(payload)}]}}]}
            with patch.object(app,'embed',return_value=[1,0,0]),patch.object(app,'api_request',return_value=response) as request:
                result=app.search(query,key='test',semantic=True,model='selected-model')
            self.assertEqual([r['job']['id'] for r in result['results']],[jid],query)
            self.assertEqual(request.call_args.args[0],'/models/selected-model:generateContent')
            sent=json.loads(request.call_args.args[2]['contents'][0]['parts'][0]['text'])
            self.assertEqual(sent['query'],query)

    def test_semantic_judgement_rejects_unknown_ids_and_invented_quotes(self):
        payload={'matches':[{'id':'missing','supporting_quote':'A cat'},
                            {'id':'source','supporting_quote':'a dog opens a door'}]}
        response={'candidates':[{'content':{'parts':[{'text':json.dumps(payload)}]}}]}
        with patch.object(app,'api_request',return_value=response):
            self.assertEqual(app.semantic_matches('pet',[('source','An orange cat opens a door.')],'test'),[])

    def test_semantic_model_failure_is_explicit_and_has_no_unrelated_results(self):
        jid=self.sample();self.approve(jid)
        with app.conn() as c:c.execute('UPDATE jobs SET embedding=? WHERE id=?',(json.dumps([1,0,0]),jid))
        with patch.object(app,'embed',return_value=[1,0,0]),patch.object(app,'api_request',side_effect=ValueError('Provider unavailable.')):
            result=app.search('animal',key='test',semantic=True)
        self.assertEqual(result['results'],[])
        self.assertIn('Provider unavailable',result['warning'])

    def test_delete_removes_source_search_and_trace_and_export_requires_approval(self):
        jid=self.sample()
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(self.base+'/export/'+jid)
        self.assertEqual(context.exception.code,400)
        self.approve(jid)
        self.post('/api/delete',{'id':jid})
        self.assertIsNone(app.get_job(jid))
        self.assertEqual(app.search('paneer')['results'],[])
        with app.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM events WHERE job_id=?',(jid,)).fetchone()[0],0)

    def test_cross_origin_and_forged_media_rejected(self):
        self.post('/api/samples',{},403,origin='https://untrusted.example')
        self.post('/api/import',{'mode':'gemini','api_key':'test-key','mime':'image/png','data':'aGVsbG8='},400)

    def test_restart_marks_unfinished_jobs_as_retryable_failures(self):
        jid=app.create_job('notes','text/plain',None,'Ingredients:\nPaneer\nSteps:\nCook.','manual',app.MODEL)['id']
        app.init()
        r=app.get_job(jid)
        self.assertEqual(r['status'],'failed')
        self.assertIn('restarted',r['error'])

    def test_valid_media_upload_preview_range_and_deletion(self):
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SAAAAABJRU5ErkJggg==')
        result=self.post('/api/import',{'mode':'gemini','api_key':'fixture-key','filename':'fixture.png','mime':'image/png','data':base64.b64encode(png).decode()},202)
        jid=result['id']
        req=urllib.request.Request(self.base+'/media/'+jid,headers={'Range':'bytes=0-7'})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status,206)
            self.assertEqual(response.read(),png[:8])
        r=app.get_job(jid)
        self.assertTrue((app.DATA/'media'/r['media_path']).is_file())
        with patch.object(app,'api_request',side_effect=ValueError('Fixture provider failure.')):
            app.process(jid)
        self.post('/api/delete',{'id':jid})
        self.assertFalse((app.DATA/'media'/r['media_path']).exists())

    def test_transient_provider_retry_is_bounded(self):
        error=urllib.error.HTTPError('https://provider.example',503,'Unavailable',{},None)
        with patch.object(app.urllib.request,'urlopen',side_effect=error) as call, patch.object(app.STOP,'wait'):
            with self.assertRaisesRegex(ValueError,'503'):
                app.api_request('/models/fixture:generateContent','fixture-key',{})
            self.assertEqual(call.call_count,3)

    def test_available_models_uses_provider_list_and_filters_non_extraction_models(self):
        response={'models':[
            {'name':'models/gemini-fixture-flash','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-fixture-image','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-fixture-embed','supportedGenerationMethods':['embedContent']}]}
        with patch.object(app,'api_request',return_value=response):
            result=self.post('/api/models',{'api_key':'fixture-key'})
        self.assertEqual([m['id'] for m in result['models']],['gemini-fixture-flash'])

    def test_retry_uses_newly_selected_model(self):
        jid=app.create_job('source','text/plain',None,'Recipe source','gemini',app.MODEL,'fixture-key')['id']
        with patch.object(app,'api_request',side_effect=ValueError('Model not found. HTTP 404.')):
            app.process(jid)
        self.assertEqual(app.get_job(jid)['status'],'failed')
        self.post('/api/retry',{'id':jid,'api_key':'fixture-key','model':'gemini-fixture-new'})
        self.assertEqual(app.get_job(jid)['model'],'gemini-fixture-new')
        self.assertEqual(app.get_job(jid)['status'],'queued')

    def test_model_settings_check_generation_not_just_catalog_presence(self):
        with patch.object(app,'api_request',side_effect=ValueError('Model unavailable. HTTP 404.')):
            self.post('/api/test-model',{'api_key':'fixture-key','model':'gemini-fixture-old'},400)
        with patch.object(app,'api_request',return_value={'candidates':[]}) as call:
            result=self.post('/api/test-model',{'api_key':'fixture-key','model':'gemini-fixture-new'})
            self.assertEqual(call.call_args.args[0],'/models/gemini-fixture-new:generateContent')
            self.assertTrue(result['verified'])

    def test_general_travel_notes_are_not_forced_into_recipe_fields(self):
        text='Title: A quiet beach\nCategory: travel\nKey points:\nThe clip describes a quiet beach and a cafe.\nTags:\nbeach, quiet'
        note=app.manual_recipe(text)
        self.assertEqual(note['category'],'travel')
        self.assertEqual(len(note['key_points']),1)
        self.assertEqual(note['ingredients'],[])
        self.assertFalse(any('complete recipe' in x for x in note['unknowns']))

    def test_save_only_media_needs_no_key_and_can_be_analysed_later(self):
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SAAAAABJRU5ErkJggg==')
        result=self.post('/api/import',{'filename':'photo.png','mode':'bookmark','mime':'image/png','data':base64.b64encode(png).decode(),'collections':['travel'],'topic':'travel'},202)
        r=app.get_job(result['id'])
        self.assertEqual(r['status'],'saved')
        self.assertIsNone(r['recipe'])
        self.assertEqual(app.public_job(r)['collections'][0]['id'],'travel')
        self.post('/api/analyze',{'id':r['id'],'api_key':'fixture-key','model':'gemini-fixture'})
        r=app.get_job(r['id'])
        self.assertEqual(r['mode'],'gemini')
        self.assertEqual(r['status'],'queued')

    def test_collection_assign_and_delete_keep_original_saves(self):
        jid=self.sample()
        created=self.post('/api/collections',{'name':'Weekend ideas'})
        cid=created['id']
        self.post('/api/assign',{'id':jid,'collections':[cid,'food']})
        self.assertEqual(len(app.public_job(app.get_job(jid))['collections']),2)
        self.post('/api/collections',{'action':'delete','id':cid})
        self.assertIsNotNone(app.get_job(jid))
        self.assertEqual([c['id'] for c in app.public_job(app.get_job(jid))['collections']],['food'])

    def test_multidomain_search_respects_collection_and_topic(self):
        ids=app.load_library_samples()
        for jid in ids:self.approve(jid)
        travel=app.search('quiet beach',category='travel',collection_id='travel')
        self.assertEqual(len(travel['results']),1)
        self.assertEqual(travel['results'][0]['job']['note']['category'],'travel')
        self.assertEqual(app.search('quiet beach',category='learning')['results'],[])
        self.assertEqual(app.search('quiet beach',collection_id='food')['results'],[])

    def test_edited_key_points_lose_automatic_source_attribution(self):
        jid=app.load_library_samples()[1]
        r=app.get_job(jid)
        edits={'key_points':[{'text':'Reviewer-added detail'}]}
        updated=app.edit_recipe(r,edits)
        self.assertTrue(updated['key_points'][0]['reviewer_edited'])
        self.assertEqual(updated['key_points'][0]['evidence_ids'],[])

    def test_deleted_default_collection_is_not_recreated_on_restart(self):
        self.post('/api/collections',{'action':'delete','id':'food'})
        app.init()
        self.assertNotIn('food',[c['id'] for c in app.collection_list()])

    def test_video_thumbnail_is_local_and_deleted_with_source(self):
        result=self.post('/api/import',{'filename':'fixture.webm','mode':'bookmark','mime':'video/webm','data':base64.b64encode(bytes.fromhex('1a45dfa3')+b'fixture').decode()},202)
        jid=result['id']
        self.post('/api/thumbnail',{'id':jid,'data':base64.b64encode(bytes.fromhex('ffd8ff')+b'fixture').decode()})
        self.assertTrue(app.public_job(app.get_job(jid))['has_thumbnail'])
        self.post('/api/delete',{'id':jid})
        self.assertFalse((app.DATA/'media'/(jid+'.poster.jpg')).exists())

    def test_descriptive_provider_evidence_ids_are_preserved(self):
        raw=app.manual_recipe(app.SAMPLES[0][1])
        mapping={e['id']:'evidence_'+str(i+1) for i,e in enumerate(raw['evidence'])}
        for e in raw['evidence']:e['id']=mapping[e['id']]
        for field in ['ingredients','steps','key_points']:
            for item in raw[field]:item['evidence_ids']=[mapping[x] for x in item['evidence_ids']]
        raw['oven_evidence_ids']=[mapping[x] for x in raw['oven_evidence_ids']]
        result=app.validate_recipe(raw,app.SAMPLES[0][1],strict_text=True)
        self.assertEqual(len(result['ingredients']),4)
        self.assertEqual(len(result['steps']),3)
        self.assertTrue(result['evidence'])

    def test_reanalysis_retains_previous_note_and_requires_fresh_approval(self):
        jid=self.sample();self.approve(jid)
        before=app.get_job(jid)['recipe']
        self.post('/api/reanalyze',{'id':jid,'api_key':'fixture-key','model':'gemini-fixture'})
        r=app.get_job(jid)
        self.assertEqual(r['previous_recipe'],before)
        self.assertEqual(r['status'],'queued')
        self.assertEqual(app.search('paneer')['results'],[])


if __name__=='__main__':
    unittest.main()
