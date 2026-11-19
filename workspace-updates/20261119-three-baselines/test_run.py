import gzip
import json
import sys
import unittest
from pathlib import Path
import numpy as np
import run

SOURCE=Path('/workspace/Football-Analysis')
sys.path.insert(0,str(SOURCE/'runtime/v2'))
from model import fit_baseline, fit_strength, matrix, partitions, rates
from training_inputs import history_inputs
HERE=Path(__file__).resolve().parent

class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=history_inputs(json.loads(gzip.decompress((HERE/'EPL-history.json.gz').read_bytes())))
        cls.train,_,_,cls.target=partitions(cls.rows)

    def test_equal_date_baseline_matches_legacy_equations(self):
        rows=[dict(r,date='2020-09-12') for r in self.train[:60]]
        a=run.ratio_fit(rows);b=fit_baseline(rows)
        for r in rows:np.testing.assert_allclose(rates(a,r)[:2],rates(b,r)[:2],rtol=1e-14)

    def test_decay_is_common_365_days(self):
        np.testing.assert_allclose(run.weights([{'date':'2020-01-01'},{'date':'2020-12-31'}]),[.5,1.])

    def test_heldout_outcomes_cannot_change_fits(self):
        boundary=self.target[0]['date']
        changed=[dict(r,home_goals=30,away_goals=30) if r['date']>=boundary else dict(r) for r in self.rows]
        alternate,*_=partitions(changed)
        self.assertEqual(self.train,alternate)
        self.assertEqual(run.ratio_fit(self.train),run.ratio_fit(alternate))
        self.assertEqual(fit_strength(self.train),fit_strength(alternate))
        self.assertLess(self.train[-1]['date'],boundary)

    def test_dc_zero_is_poisson_and_only_four_cells_change(self):
        a=matrix(1.4,.9);np.testing.assert_allclose(a,matrix(1.4,.9,'dixon_coles',0))
        b=matrix(1.4,.9,'dixon_coles',.006)
        self.assertAlmostEqual(float(b.sum()),1)
        self.assertTrue(np.all(b>0))
        mask=np.ones(a.shape,dtype=bool);mask[:2,:2]=False
        np.testing.assert_allclose(a[mask],b[mask],rtol=1e-13)

    def test_top3_is_unique_and_not_top1(self):
        m=np.array([[.4,.3],[.2,.1]])
        s=run.score(m,[1,0]);self.assertEqual(s['top1_hit'],0);self.assertEqual(s['top3_hit'],1)
        self.assertEqual(s['top3'],[[0,0],[0,1],[1,0]])
        self.assertEqual(run.score(np.full((2,2),.25),[0,0])['primary'],[0,0])

    def test_saved_rows_reconcile_metrics_and_matched_rates(self):
        report=json.loads((HERE/'result/report.json').read_text())
        rows=[json.loads(x) for x in gzip.decompress((HERE/'result/rows.jsonl.gz').read_bytes()).splitlines()]
        self.assertEqual(len(rows),report['target_n']);self.assertEqual(report['common_n'],474)
        self.assertEqual({r['match_id'] for r in rows},{r['match_id'] for r in self.target})
        for name,m in report['metrics'].items():
            self.assertEqual(m['top1_hits'],sum(r['arms'][name]['primary']==r['actual'] for r in rows))
            self.assertEqual(m['top3_hits'],sum(r['actual'] in r['arms'][name]['top3'] for r in rows))
            self.assertAlmostEqual(m['score_log_loss'],np.mean([-np.log(r['arms'][name]['actual_probability']) for r in rows]))
        for r in rows:
            self.assertEqual(r['arms']['opponent_poisson']['rates'],r['arms']['opponent_dixon_coles']['rates'])
            for arm in r['arms'].values():self.assertEqual(len({tuple(x) for x in arm['top3']}),3)

if __name__=='__main__':unittest.main(verbosity=2)
