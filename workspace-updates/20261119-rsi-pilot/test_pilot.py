import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
import pilot

class PilotTests(unittest.TestCase):
    def setUp(self):
        self.cutoff=datetime(2026,11,19,tzinfo=timezone.utc)
        self.fixtures=[{'match_id':f'espn:{i}','cohort':'eng.1','stage':'regular-season','status':'scheduled','cutoff_at':self.cutoff.isoformat(),'kickoff_at':'2026-11-21T12:30:00Z','model_home':'A','model_away':'B'} for i in range(10)]
        self.rows=[{'cohort':'EPL','date':'2026-11-08','home':'A','away':'B','score_basis':'regulation_90','observed_at':'2026-11-18T05:10:00Z'}]
    def test_training_cutoff_and_no_odds(self):
        pilot.check_training(self.rows,self.fixtures,self.cutoff)
        for patch in [{'observed_at':'2026-11-20T00:00:00Z'},{'date':'2026-11-21'},{'odds':2.1}]:
            with self.assertRaises(ValueError):pilot.check_training([dict(self.rows[0],**patch)],self.fixtures,self.cutoff)
    def test_duplicate_and_incomplete_population(self):
        with self.assertRaises(ValueError):pilot.check_training(self.rows*2,self.fixtures,self.cutoff)
        with self.assertRaises(ValueError):pilot.check_training(self.rows,self.fixtures[:9],self.cutoff)
    def test_cannot_freeze_after_kickoff(self):
        fixtures=copy.deepcopy(self.fixtures);fixtures[0]['kickoff_at']='2026-11-18T00:00:00Z'
        with self.assertRaises(ValueError):pilot.check_training(self.rows,fixtures,self.cutoff)
    def test_decisions_bounded_and_never_promote(self):
        p={'review_deadline':'2026-12-01T00:00:00Z'};t=self.cutoff
        self.assertEqual(pilot.decision(p,0,0,0,None,t),'PENDING')
        self.assertEqual(pilot.decision(p,10,10,0,0,t),'RETIRED_PILOT_NO_TOP1_GAIN')
        self.assertEqual(pilot.decision(p,10,10,2,.01,t),'RETIRED_PILOT_PROBABILITY_REGRESSION')
        self.assertEqual(pilot.decision(p,10,10,1,-.01,t),'RETAIN_SIGNAL_REQUEST_HUMAN_REVIEW_FOR_ONE_EXTENSION')
        self.assertEqual(pilot.decision(p,9,9,1,0,datetime(2026,12,2,tzinfo=timezone.utc)),'CLOSED_INCOMPLETE_AT_DEADLINE')
    def test_append_only_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'out.json';pilot.write_new(p,{'n':1})
            with self.assertRaises(FileExistsError):pilot.write_new(p,{'n':2})
            record={'stage':'prematch','payload':{'rule':'fixed'}};record['record_sha256']=pilot.digest(record);pilot.verify(record)
            record['payload']['rule']='changed'
            with self.assertRaises(ValueError):pilot.verify(record)
    def test_unverified_or_early_result_rejected(self):
        f=dict(self.fixtures[0],home='espn:1',away='espn:2');r=dict(f,score_basis='regulation_90',known_at='2026-11-19T00:00:00Z',raw_reference={'captured_at':'2026-11-19T00:00:00Z'})
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):pilot.certify_result(r,f,Path(d),self.cutoff)
    def test_certifier_requires_finished_regulation_and_original_home_away(self):
        import hashlib
        f=dict(self.fixtures[0],home='espn:1',away='espn:2')
        url='https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary?event=0'
        raw={'header':{'id':'0','league':{'slug':'eng.1'},'competitions':[{'date':f['kickoff_at'],'status':{'type':{'completed':True,'name':'STATUS_FULL_TIME'},'period':2},'competitors':[{'homeAway':'home','team':{'id':'1'},'score':'2'},{'homeAway':'away','team':{'id':'2'},'score':'1'}]}]}}
        r=dict(f,home_goals=2,away_goals=1,score_basis='regulation_90',source_url=url,known_at='2026-11-21T15:00:00Z')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'raw.json'
            def bind():
                p.write_text(json.dumps(raw));r['raw_reference']={'captured_at':r['known_at'],'source_url':url,'path':'raw.json','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            bind();at=datetime(2026,11,21,16,tzinfo=timezone.utc);self.assertEqual(pilot.certify_result(r,f,Path(d),at)['home'],2)
            raw['header']['competitions'][0]['status']['period']=3;bind()
            with self.assertRaises(ValueError):pilot.certify_result(r,f,Path(d),at)
            raw['header']['competitions'][0]['status']['period']=2;raw['header']['competitions'][0]['competitors'][0]['team']['id']='999';bind()
            with self.assertRaises(ValueError):pilot.certify_result(r,f,Path(d),at)

    def test_real_frozen_population_and_independent_display(self):
        policy,records=pilot.load_batch(pilot.HERE/'batch')
        self.assertEqual(len(records),10)
        self.assertEqual(sum(a['status']=='PREDICTED' for r in records.values() for a in r['payload']['arms'].values()),20)
        ix=pilot.read(pilot.HERE/'batch/index.json')
        self.assertEqual(len(ix['displays']),10)
        for ref in ix['displays']:
            r=pilot.verify(pilot.read(ref['path']));d=r['payload']
            self.assertEqual(r['track'],'rsi-user-display')
            self.assertEqual(d['status'],'ABSTAIN');self.assertIsNone(d['first_score'])
            self.assertEqual(len(d['alternatives']),2);self.assertTrue(all(a['score'] is None for a in d['alternatives']))
            self.assertNotIn('matrix_top3',d);self.assertNotIn('compared_scores',d)
    def test_no_results_are_not_zero_accuracy(self):
        r=pilot.read(pilot.HERE/'initial-review.json')
        self.assertEqual(r['registered_n'],10);self.assertEqual(r['paired_n'],0)
        self.assertEqual(r['decision'],'PENDING')
        for m in r['metrics'].values():
            self.assertIsNone(m['score_top1']);self.assertIsNone(m['score_top3']);self.assertIsNone(m['top1_hits'])

if __name__=='__main__':unittest.main(verbosity=2)
