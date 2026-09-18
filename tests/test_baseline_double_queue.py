"""Regression checks of CLI manifests and skip-before-exec fold protection."""
import json
import fcntl
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_pibd_survpath_5fold as baseline


class BaselineDoubleQueueTests(unittest.TestCase):
    def test_execution_lock_survives_real_exec_and_releases_on_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            # Replace only the heavy official training command with a CPU child;
            # exercise the actual worker branch, flock, environment and exec.
            script = (
                'import sys; from pathlib import Path; '
                f'sys.path.insert(0, {str(baseline.ROOT / "scripts")!r}); '
                'import run_pibd_survpath_5fold as b; '
                f'b.REPOS["survpath"] = Path({directory!r}); '
                'b.baseline_command = lambda *a: [sys.executable, "-u", "-c", '
                '"import time; print(\\\"READY\\\", flush=True); time.sleep(0.5)"]; '
                f'sys.argv = ["runner", "--models", "survpath", "--cohorts", "hnsc", '
                f'"--results-root", {directory!r}, "--queue-name", "q", "--gpus", "0", '
                '"--execute-one", "survpath", "hnsc", "0"]; b.main()'
            )
            with subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True) as child:
                line = child.stdout.readline().strip()
                if line != 'READY':
                    self.fail(child.communicate(timeout=10)[1])
                with (Path(directory) / 'survpath/hnsc/folds/fold_0/execution.lock').open('a') as claim:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(claim, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.assertEqual(child.wait(timeout=10), 0)
                    fcntl.flock(claim, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_prepare_manifest_supports_peer_status_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            args = ['runner', '--models', 'survpath', '--cohorts', 'hnsc',
                    '--results-root', directory, '--queue-name', 'queue_test', '--gpus', '0',
                    '--prepare-only', '--allow-gpu-sharing', '--max-jobs-per-gpu', '2',
                    '--shared-queue-status', directory + '/peer.json']
            with patch.object(sys, 'argv', args), \
                 patch.object(baseline, 'validate_prepared', return_value={}), \
                 patch.object(baseline, 'prepare_repo', return_value={}):
                baseline.main()
            state = json.loads((Path(directory) / 'queue_test/run_manifest.json').read_text())
            self.assertEqual(state['arguments']['shared_queue_status'], [directory + '/peer.json'])
            self.assertEqual(len(state['jobs']), 5)

    def test_completed_worker_does_not_exec_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            args = ['runner', '--models', 'survpath', '--cohorts', 'hnsc',
                    '--results-root', directory, '--queue-name', 'queue_test', '--gpus', '0',
                    '--execute-one', 'survpath', 'hnsc', '0']
            with patch.object(sys, 'argv', args), \
                 patch.object(baseline, 'completed', return_value={'predictions': 'test', 'val_cindex': .6}), \
                 patch.object(baseline, 'validate_predictions') as validate, \
                 patch.object(baseline.os, 'execve') as execute:
                baseline.main()
            validate.assert_called_once()
            execute.assert_not_called()
            self.assertFalse((Path(directory) / 'survpath/hnsc/folds/fold_0/invocation.json').exists())

    def test_supplement_keeps_incomplete_peer_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            training = Path(directory) / 'survpath/hnsc/folds/fold_0/training'
            training.mkdir(parents=True)
            (training / 'marker').write_text('owned by live peer')
            args = ['runner', '--models', 'survpath', '--cohorts', 'hnsc',
                    '--results-root', directory, '--queue-name', 'queue_test', '--gpus', '0',
                    '--leave-existing-training']
            with patch.object(sys, 'argv', args), \
                 patch.object(baseline, 'validate_prepared', return_value={}), \
                 patch.object(baseline, 'prepare_repo', return_value={}), \
                 patch.object(baseline, 'gpu_queue') as queue:
                baseline.main()
            self.assertEqual((training / 'marker').read_text(), 'owned by live peer')
            self.assertEqual(len(queue.call_args.args[2]), 4)


if __name__ == '__main__':
    unittest.main()
