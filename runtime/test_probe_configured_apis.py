import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import probe_configured_apis as probe

CODE=Path(os.environ.get('WCPP_PROBE_TEST_CODE','/workspace/Football-Analysis-nations-repair-20261116'))
sys.path.insert(0,str(CODE));sys.path.insert(0,str(CODE/'runtime'))

class ProbeTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def answer(self,response=None,**changes):
        call={'url':'https://example.org/synthetic','http_status':200,'api_success':True,'authenticated':True}
        call.update(changes);return {'call':call,'response':response}
    def test_missing_binding_performs_no_call(self):
        with patch.dict(os.environ,{'WCPP_BSD_API_KEY':''}):
            result=probe.generic_probe('bsd',self.root,'2026-11-16',call=lambda *a,**k:self.fail('network'))
        self.assertEqual(result['requests'],0);self.assertEqual(result['status'],'MISSING_CREDENTIAL')
    def test_access_denial_stops_api_football_after_one_request(self):
        calls=[]
        def fetch(*args,**kwargs):
            calls.append(args);return self.answer(http_status=403,api_success=False,authenticated=False,error_code='HTTP_ERROR',failure_kind='CLOUDFLARE_HTML_ACCESS_BLOCK')
        with patch.dict(os.environ,{'WCPP_API_FOOTBALL_KEY':'SYNTHETIC_API_FOOTBALL_TOKEN'}):
            result=probe.generic_probe('api-football',self.root,'2026-11-16',call=fetch,sleeper=lambda _:self.fail('retry'))
        self.assertEqual(len(calls),1);self.assertEqual(result['status'],'NO_USABLE_RESPONSE')
    def test_plan_rejection_checks_only_one_known_historical_window(self):
        answers=[self.answer({'response':{'account':{'email':'private@example.test'}}}),
                 self.answer({'response':[{'league':{'id':5,'name':'UEFA Nations League'}}]}),
                 self.answer({},api_success=False,authenticated=False,error_code='PROVIDER_ERROR',failure_kind='PROVIDER_PLAN_OR_PERMISSION_REJECTION'),
                 self.answer({'response':[]})]
        calls=[];sleeps=[]
        def fetch(provider,path,params,**kwargs):calls.append((path,params));return answers.pop(0)
        with patch.dict(os.environ,{'WCPP_API_FOOTBALL_KEY':'SYNTHETIC_API_FOOTBALL_TOKEN'}):
            result=probe.generic_probe('api-football',self.root,'2026-11-16',call=fetch,sleeper=sleeps.append)
        self.assertEqual(result['requests'],4);self.assertEqual(sleeps,[10,10,10])
        self.assertEqual(calls[-1][1],{'league':5,'season':2024,'date':'2024-11-16'})
        self.assertNotIn('private@example.test',''.join(p.read_text() for p in self.root.glob('*.json')))
    def test_secret_echo_cannot_be_written(self):
        with patch.dict(os.environ,{'WCPP_OPENFOOT_API_KEY':'SYNTHETIC_SECRET_MUST_NOT_LEAK'}):
            with self.assertRaises(ValueError):probe.write(self.root/'unsafe.json',{'message':'SYNTHETIC_SECRET_MUST_NOT_LEAK'})
        self.assertFalse((self.root/'unsafe.json').exists())

if __name__=='__main__':unittest.main()
