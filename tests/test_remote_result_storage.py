"""Opt-in real filesystem smoke test; creates only a temporary test directory."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_hnsc_blca_bernoulli_kan import assert_output_mount, save_json


@unittest.skipUnless(os.environ.get('MREPATH_STORAGE_SMOKE_MOUNT'), 'No test mount selected')
class RemoteResultStorageTests(unittest.TestCase):
    def test_atomic_save_checkpoint_and_lock(self):
        import torch
        mount = Path(os.environ['MREPATH_STORAGE_SMOKE_MOUNT'])
        assert_output_mount(mount, mount)
        with tempfile.TemporaryDirectory(prefix='storage_smoke_', dir=mount) as directory:
            root = Path(directory)
            save_json(root / 'status.json', {'value': 1})
            save_json(root / 'status.json', {'value': 2})
            self.assertEqual(json.loads((root / 'status.json').read_text()), {'value': 2})
            expected = torch.arange(16).reshape(4, 4)
            torch.save({'tensor': expected}, root / 'checkpoint.pt')
            actual = torch.load(root / 'checkpoint.pt', weights_only=True)
            self.assertTrue(torch.equal(expected, actual['tensor']))
            with (root / 'execution.lock').open('a') as claim:
                fcntl.flock(claim, fcntl.LOCK_EX | fcntl.LOCK_NB)
                attempt = subprocess.run(['flock', '-n', str(root / 'execution.lock'), 'true'])
                self.assertEqual(attempt.returncode, 1)
            attempt = subprocess.run(['flock', '-n', str(root / 'execution.lock'), 'true'])
            self.assertEqual(attempt.returncode, 0)
