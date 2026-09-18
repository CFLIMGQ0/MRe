import sys
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_clean_baseline_queue import parse_job, check_splits
from run_hnsc_blca_bernoulli_kan import train_command, assert_output_mount, space_check
from run_pibd_survpath_5fold import baseline_command


class CleanQueueTests(unittest.TestCase):
    def test_external_storage_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            mount = Path(directory)
            with patch('run_hnsc_blca_bernoulli_kan.os.path.ismount', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'not mounted'):
                    assert_output_mount(mount / 'results', mount)
            with patch('run_hnsc_blca_bernoulli_kan.os.path.ismount', return_value=True):
                assert_output_mount(mount / 'results', mount)
                with self.assertRaises(RuntimeError):
                    assert_output_mount(mount.parent / 'elsewhere', mount)

    def test_remote_reservation_counts_against_actual_output_disk(self):
        args = SimpleNamespace(output=Path('/output'), reserve_manifest=None, reserve_raw=None,
                               min_free_gib=32, reserve_gib=22)
        with patch('run_hnsc_blca_bernoulli_kan.shutil.disk_usage',
                   return_value=SimpleNamespace(free=53 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, 'Disk guard'):
                space_check(args)
        with patch('run_hnsc_blca_bernoulli_kan.shutil.disk_usage',
                   return_value=SimpleNamespace(free=55 * 2**30)):
            space_check(args)

    def test_job_validation(self):
        self.assertEqual(parse_job('mrepath:brca:4'), ('mrepath', 'brca', 4))
        for value in ['mrepath:brca:5', 'aes:blca:0', 'pibd:hnsc:0']:
            with self.assertRaises(ValueError):
                parse_job(value)

    def test_current_splits_are_versioned(self):
        check_splits('blca')
        check_splits('brca')

    def test_original_brca_model_command(self):
        cmd = train_command(SimpleNamespace(cohort='brca', data=Path('/data'),
                                           output=Path('/new'), original_model=True), 2)
        for flag, value in [('--mrepath_genomic_encoder', 'original'),
                            ('--mrepath_gene_aggregation', 'default'),
                            ('--mrepath_rebalance_variant', 'original'),
                            ('--mrepath_fusion', 'ifa'), ('--max_epochs', '30'),
                            ('--k_start', '2'), ('--k_end', '3')]:
            self.assertEqual(cmd[cmd.index(flag)+1], value)
        self.assertNotIn('--pc_cmka_experiment', cmd)

    def test_baselines_keep_native_training_arguments(self):
        for model, batch in [('pibd', '32'), ('survpath', '1')]:
            cmd = baseline_command(model, 'brca', 4, Path('/new'))
            self.assertEqual(cmd[cmd.index('--batch_size')+1], batch)
            self.assertEqual(cmd[cmd.index('--label_col')+1], 'survival_months_dss')
            self.assertEqual(cmd[cmd.index('--max_epochs')+1], '30')
