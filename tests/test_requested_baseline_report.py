from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report_requested_baselines import groups


class ReportTests(unittest.TestCase):
    def test_partial_folds_never_have_five_fold_mean(self):
        records = [dict(model='pibd', cohort='blca', fold=f, val_cindex=.6 + .01*f)
                   for f in range(4)]
        report = next(g for g in groups(records) if g['model'] == 'pibd' and g['cohort'] == 'blca')
        self.assertEqual(report['completed_folds'], 4)
        self.assertIsNone(report['mean'])
        self.assertIsNone(report['std_ddof0'])

    def test_complete_folds_have_both_sd_conventions(self):
        records = [dict(model='survpath', cohort='hnsc', fold=f, val_cindex=.6 + .01*f)
                   for f in range(5)]
        report = next(g for g in groups(records) if g['model'] == 'survpath' and g['cohort'] == 'hnsc')
        self.assertAlmostEqual(report['mean'], .62)
        self.assertGreater(report['std_ddof1'], report['std_ddof0'])

    def test_duplicate_fold_is_not_silently_selected(self):
        r = dict(model='pibd', cohort='brca', fold=0, val_cindex=.7)
        with self.assertRaisesRegex(ValueError, 'Duplicate fold'):
            groups([r, dict(r)])


if __name__ == '__main__':
    unittest.main()
