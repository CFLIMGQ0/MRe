import csv
from pathlib import Path
import pickle
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_survival_predictions import validate_predictions


class PredictionAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, fields, rows in [
            ('datasets_csv/metadata/tcga_demo.csv',
             ['case_id', 'survival_months_dss', 'censorship_dss'],
             [['A', 1, 0], ['B', 2, 0], ['C', 3, 1]]),
            ('datasets_csv/raw_rna_data/combine/demo/rna_clean.csv', ['case_id', 'gene'],
             [['A', 1], ['B', 2], ['C', 3]]),
            ('splits/5folds/tcga_demo/splits_0.csv', ['train', 'val'],
             [['', 'A'], ['', 'B'], ['', 'C']])]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(fields)
                writer.writerows(rows)
        self.data = {p: dict(time=i, censorship=int(p == 'C'), risk=4-i)
                     for i, p in enumerate('ABC', 1)}
        self.predictions = self.root / 'predictions.pkl'

    def run_audit(self, score=1.):
        with self.predictions.open('wb') as stream:
            pickle.dump(self.data, stream)
        return validate_predictions(self.predictions, score, 'demo', 0, self.root)

    def test_matches(self):
        self.assertEqual(self.run_audit()['recomputed_cindex'], 1.)

    def test_missing_patient_rejected(self):
        self.data.pop('C')
        with self.assertRaisesRegex(ValueError, 'patient mismatch'):
            self.run_audit()

    def test_bad_label_rejected(self):
        self.data['A']['time'] = 42
        with self.assertRaisesRegex(ValueError, 'label mismatch'):
            self.run_audit()

    def test_nonfinite_risk_rejected(self):
        self.data['A']['risk'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'Invalid survival'):
            self.run_audit()

    def test_mismatching_summary_rejected(self):
        with self.assertRaisesRegex(ValueError, 'C-index mismatch'):
            self.run_audit(.5)

    def test_explicit_historical_split_does_not_follow_new_active_split(self):
        historical = self.root / 'historical.csv'
        active = self.root / 'splits/5folds/tcga_demo/splits_0.csv'
        historical.write_bytes(active.read_bytes())
        self.run_audit()
        active.write_text('train,val\nA,B\nC,\n')
        with self.assertRaisesRegex(ValueError, 'patient mismatch'):
            validate_predictions(self.predictions, 1., 'demo', 0, self.root)
        report = validate_predictions(self.predictions, 1., 'demo', 0, self.root,
                                      split_path=historical)
        self.assertEqual(report['patients'], 3)
        self.assertEqual(report['split_path'], str(historical))


if __name__ == '__main__':
    unittest.main()
