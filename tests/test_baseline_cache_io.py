import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import h5py
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from baseline_cache_io import load_cached_features
from run_pibd_survpath_5fold import baseline_command


class BaselineCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ['pt_files', 'h5_files', 'graph_files']:
            (self.root / name).mkdir()
        self.x = torch.randn(7, 1024)
        self.request = self.root / 'pt_files/slide.pt'

    def test_tensor_file_unmodified(self):
        torch.save(self.x, self.request)
        before = self.request.read_bytes()
        self.assertTrue(torch.equal(self.x, load_cached_features(self.request)))
        self.assertEqual(before, self.request.read_bytes())

    def test_hdf5_feature_values_exact_and_no_new_pt(self):
        with h5py.File(self.root / 'h5_files/slide.h5', 'w') as h:
            h['features'] = self.x.numpy()
        self.assertTrue(torch.equal(self.x, load_cached_features(self.request)))
        self.assertFalse(self.request.exists())

    def test_graph_only_reads_x(self):
        torch.save(SimpleNamespace(x=self.x, edge_index=torch.tensor([[0], [1]])),
                   self.root / 'graph_files/slide.pt')
        self.assertTrue(torch.equal(self.x, load_cached_features(self.request)))
        self.assertFalse(self.request.exists())

    def test_missing_features_fail(self):
        with self.assertRaises(FileNotFoundError):
            load_cached_features(self.request)

    def test_invalid_shapes_and_nonfinite_fail(self):
        for x in [torch.randn(7, 768), torch.full((7, 1024), float('nan')),
                  torch.randn(7, 1024, dtype=torch.float64)]:
            torch.save(x, self.request)
            with self.assertRaises(ValueError):
                load_cached_features(self.request)

    def test_baseline_specific_batch_and_architecture_preserved(self):
        for model, batch in [('pibd', '32'), ('survpath', '1')]:
            c = baseline_command(model, 'blca', 3, self.root)
            for flag, value in {'--batch_size': batch, '--max_epochs': '30',
                                '--k_start': '3', '--k_end': '4', '--seed': '1',
                                '--label_col': 'survival_months_dss', '--encoding_dim': '1024'}.items():
                self.assertEqual(c[c.index(flag) + 1], value)
            self.assertFalse(any(x.startswith('--mrepath_') or x.startswith('--pc_cmka') for x in c))


if __name__ == '__main__':
    unittest.main()
