import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from report_clean_baselines import merge_results


def snapshot(folds, protocol='clean'):
    return {'data': {'survpath:brca': {'protocol': protocol,
            'folds': [{'fold': f, 'val_cindex': 0.5 + 0.02 * f} for f in folds]}}}


class CleanReportTests(unittest.TestCase):
    def test_disjoint_host_folds_complete_one_five_fold_result(self):
        value = merge_results(snapshot([0, 1, 2]), snapshot([3, 4]))['survpath:brca']
        self.assertEqual(value['completed_folds'], 5)
        self.assertAlmostEqual(value['mean'], 0.54)
        self.assertEqual([r['fold'] for r in value['folds']], list(range(5)))

    def test_partial_folds_do_not_report_a_mean(self):
        value = merge_results(snapshot([0, 1]), snapshot([3]))['survpath:brca']
        self.assertIsNone(value['mean'])

    def test_duplicate_fold_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            merge_results(snapshot([0, 1]), snapshot([1, 2]))

    def test_protocol_mismatch_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'protocol mismatch'):
            merge_results(snapshot([0]), snapshot([1], 'old'))
