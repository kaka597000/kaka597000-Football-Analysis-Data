import unittest
from development_replay import compare


class ReplayTests(unittest.TestCase):
    def test_only_probability_metrics_allow_roundoff(self):
        self.assertLess(compare({'score_log_loss':2.}, {'score_log_loss':2.+1e-15}),1e-12)
        with self.assertRaises(ValueError):compare({'score_log_loss':2.},{'score_log_loss':2.+1e-8})
        with self.assertRaises(ValueError):compare({'alpha':.75},{'alpha':.75+1e-15})
        with self.assertRaises(ValueError):compare({'primary':'1-1'},{'primary':'1-0'})
        with self.assertRaises(ValueError):compare({'hits':1},{'hits':True})
        with self.assertRaises(ValueError):compare({'sha':'a'},{'sha':'b'})

    def test_missing_rows_or_nonfinite_metrics_fail(self):
        with self.assertRaises(ValueError):compare([1,2],[1])
        with self.assertRaises(ValueError):compare({'wdl_brier':.5},{'wdl_brier':float('nan')})
