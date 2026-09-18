import sys
from pathlib import Path
import unittest
import json
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_author_patient_splits import filtered_split, read_split


class AuthorSplitTests(unittest.TestCase):
    def test_filter_preserves_fold_and_order(self):
        source = ',train,val\n0,TCGA-AA-0003,TCGA-AA-0001\n1,TCGA-AA-0002,TCGA-AA-0004\n'
        ids = {'TCGA-AA-0001', 'TCGA-AA-0002', 'TCGA-AA-0003'}
        result = read_split(filtered_split(source, ids))
        self.assertEqual(result, {'train': ['TCGA-AA-0003', 'TCGA-AA-0002'],
                                  'val': ['TCGA-AA-0001']})

    def test_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            filtered_split('train,val\nTCGA-AA-0001,TCGA-AA-0001\n', {'TCGA-AA-0001'})

    def test_missing_patient_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cover'):
            filtered_split('train,val\nTCGA-AA-0001,TCGA-AA-0002\n', {'TCGA-AA-0003'})

    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            filtered_split('train,val\nTCGA-AA-0001,TCGA-AA-0002\nTCGA-AA-0001,\n',
                           {'TCGA-AA-0001', 'TCGA-AA-0002'})

    def test_slide_id_rejected(self):
        with self.assertRaisesRegex(ValueError, 'patient IDs'):
            filtered_split('train,val\nTCGA-AA-0001-01Z.svs,TCGA-AA-0002\n',
                           {'TCGA-AA-0001', 'TCGA-AA-0002'})

    def test_empty_partition_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Empty'):
            filtered_split('train,val\nTCGA-AA-0001,TCGA-AA-0002\n', {'TCGA-AA-0001'})

    def test_old_output_cannot_be_reused_after_split_change(self):
        from run_hnsc_blca_bernoulli_kan import ensure_split_audit_matches
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'split_audit.json'
            old = {'folds': [{'fold': 0, 'split_sha256': 'old'}]}
            path.write_text(json.dumps(old))
            ensure_split_audit_matches(temp, old)
            with self.assertRaisesRegex(RuntimeError, 'NEW output directory'):
                ensure_split_audit_matches(temp, {'folds': [{'fold': 0, 'split_sha256': 'new'}]})
            self.assertEqual(json.loads(path.read_text()), old)
