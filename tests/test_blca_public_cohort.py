import importlib.util
from pathlib import Path
import tempfile
import unittest

import pandas as pd


spec = importlib.util.spec_from_file_location(
    'blca_public_cohort', Path(__file__).resolve().parents[1] / 'scripts/prepare_blca_public_cohort.py')
cohort = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cohort)


class CohortMembershipTests(unittest.TestCase):
    def setUp(self):
        self.ids = [f'TCGA-AA-000{i}' for i in range(1, 7)]
        self.slides = [{'case_id': p} for p in self.ids]
        self.samples = [p + '-01' for p in self.ids[:5]]
        self.clinical = pd.DataFrame([
            {'bcr_patient_barcode': p, 'type': 'BLCA', 'DSS': 1,
             'DSS.time': 100.0, 'Redaction': None} for p in self.ids])

    def test_requires_primary_rna(self):
        rows, _ = cohort.select_patients(self.slides, self.samples + [self.ids[5] + '-11'], self.clinical)
        self.assertEqual(sum(r['selected'] for r in rows), 5)
        self.assertIn('no_primary_tumor_RNA', rows[-1]['reason'])

    def test_excludes_redacted_and_nonpositive_or_invalid_dss(self):
        self.clinical.loc[0, 'Redaction'] = 'Redacted'
        self.clinical.loc[1, 'DSS.time'] = 0
        self.clinical.loc[2, 'DSS.time'] = float('inf')
        self.clinical.loc[3, 'DSS'] = 2
        rows, _ = cohort.select_patients(self.slides, self.samples, self.clinical)
        self.assertEqual([r['case_id'] for r in rows if r['selected']], [self.ids[4]])
        self.assertIn('CDR_redacted', rows[0]['reason'])

    def test_rejects_ambiguous_rna_and_duplicate_clinical(self):
        with self.assertRaisesRegex(RuntimeError, 'Ambiguous'):
            cohort.select_patients(self.slides, self.samples + [self.ids[0] + '-01A'], self.clinical)
        with self.assertRaisesRegex(RuntimeError, 'Duplicate BLCA'):
            cohort.select_patients(self.slides, self.samples,
                                   pd.concat([self.clinical, self.clinical.iloc[:1]]))

    def test_deduplicates_slides_at_patient_level(self):
        rows, _ = cohort.select_patients(self.slides + self.slides, self.samples, self.clinical)
        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(r['selected'] for r in rows), 5)

    def test_does_not_admit_wrong_cancer_clinical(self):
        self.clinical.loc[0, 'type'] = 'BRCA'
        rows, _ = cohort.select_patients(self.slides, self.samples, self.clinical)
        self.assertIn('no_CDR_BLCA_record', rows[0]['reason'])

    def test_preserves_frozen_artifacts_and_existing_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            cohort.frozen(source, b'original')
            cohort.frozen(source, b'original')
            with self.assertRaisesRegex(RuntimeError, 'overwrite'):
                cohort.frozen(source, b'changed')
            link = root / 'link'
            cohort.link(source, link)
            cohort.link(source, link)
            other = root / 'other'
            cohort.frozen(other, b'another')
            with self.assertRaisesRegex(RuntimeError, 'Conflicting'):
                cohort.link(other, link)
            self.assertEqual(source.read_bytes(), b'original')
            self.assertEqual(link.resolve(), source)


if __name__ == '__main__':
    unittest.main()
