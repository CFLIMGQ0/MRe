"""CPU-only tests of resource admission, independent folds, and aggregation."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_hnsc_blca_bernoulli_kan as runner


class GPUQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.args = SimpleNamespace(output=self.output, data=self.output,
                                    min_gpu_free_mib=18000, gpu_poll_seconds=0.01)

    def test_admission_excludes_compute_process_and_used_memory(self):
        gpu = "0, GPU-0, 24000, 10\n1, GPU-1, 23000, 500\n2, GPU-2, 1500, 23000\n3, GPU-3, 21000, 3500\n"
        apps = "GPU-1, 123\nGPU-2, 456\n"
        with patch.object(runner.subprocess, "check_output", side_effect=[gpu, apps]):
            self.assertEqual(runner.idle_gpus(["0", "1", "2", "3"], 18000), ["0"])

    def test_resource_query_failure_is_not_permission_to_launch(self):
        with patch.object(runner.subprocess, "check_output", side_effect=RuntimeError("query failed")):
            with self.assertRaises(RuntimeError):
                runner.idle_gpus(["0"], 18000)

    def test_explicit_sharing_admits_occupied_gpu_with_enough_memory(self):
        gpu = "0, GPU-0, 19900, 4600\n1, GPU-1, 18800, 5700\n2, GPU-2, 17000, 7500\n"
        apps = "GPU-0, 123\nGPU-1, 456\nGPU-2, 789\n"
        with patch.object(runner.subprocess, "check_output", side_effect=[gpu, apps]):
            self.assertEqual(runner.idle_gpus(["1", "0", "2"], 18000, allow_sharing=True), ["1", "0"])

    def test_sharing_still_fails_closed_on_resource_query_error(self):
        with patch.object(runner.subprocess, "check_output", side_effect=RuntimeError("query failed")):
            with self.assertRaises(RuntimeError):
                runner.idle_gpus(["0"], 18000, allow_sharing=True)

    def test_sharing_keeps_one_owned_job_per_gpu_and_records_permission(self):
        self.args.allow_gpu_sharing = True
        launched, successful = self.simulate()
        self.assertEqual(len(launched), 5)
        self.assertEqual(len(successful), 5)
        state = json.loads((self.output / "pipeline_status.json").read_text())
        self.assertTrue(state["allow_gpu_sharing"])
        self.assertEqual(state["min_gpu_free_mib"], 18000)
        events = [json.loads(s) for s in (self.output / "gpu_dispatch.jsonl").read_text().splitlines()]
        self.assertTrue(all(e["allow_gpu_sharing"] for e in events if e["event"] == "started"))

    def test_sharing_respects_other_queue_reservations(self):
        self.args.allow_gpu_sharing = True
        self.args.reserved_until_unit = "prior.service"
        self.args.reserved_gpus = ["0"]
        with patch.object(runner, "space_check"), \
             patch.object(runner, "idle_gpus", side_effect=lambda pool, minimum, **kwargs: pool) as admission, \
             patch.object(runner.subprocess, "run", return_value=SimpleNamespace(stdout="active\n")):
            runner.gpu_queue(self.args, "reserved_shared", [("job", [sys.executable, "-c", "print('ok')"])], ["0", "1"])
        self.assertTrue(all(call.kwargs.get("allow_sharing") for call in admission.call_args_list))
        events = [json.loads(s) for s in (self.output / "gpu_dispatch.jsonl").read_text().splitlines()]
        self.assertEqual([e['gpu'] for e in events if e['event'] == 'started'], ['1'])

    def test_two_slots_overlap_without_exceeding_capacity(self):
        self.args.allow_gpu_sharing = True
        self.args.max_jobs_per_gpu = 2
        with patch.object(runner, 'space_check'), patch.object(runner, 'idle_gpus', return_value=['0']):
            jobs = [(f'job_{i}', [sys.executable, '-c', 'import time; time.sleep(0.12)']) for i in range(4)]
            runner.gpu_queue(self.args, 'double', jobs, ['0'])
        live = peak = 0
        for line in (self.output / 'gpu_dispatch.jsonl').read_text().splitlines():
            event = json.loads(line)
            live += 1 if event['event'] == 'started' else -1
            peak = max(peak, live)
            self.assertLessEqual(live, 2)
        self.assertEqual(peak, 2)
        self.assertEqual(live, 0)

    def test_peer_jobs_count_towards_two_slot_capacity(self):
        self.args.allow_gpu_sharing = True
        self.args.max_jobs_per_gpu = 2
        self.args.shared_queue_status = [self.output / 'peer.json']
        with patch.object(runner, 'space_check'), \
             patch.object(runner, 'idle_gpus', return_value=['0', '1']), \
             patch.object(runner, 'external_gpu_jobs', return_value={'0': 2, '1': 1}):
            jobs = [(f'job_{i}', [sys.executable, '-c', 'import time; time.sleep(0.04)']) for i in range(3)]
            runner.gpu_queue(self.args, 'peer', jobs, ['0', '1'])
        live = 0
        for line in (self.output / 'gpu_dispatch.jsonl').read_text().splitlines():
            event = json.loads(line)
            self.assertEqual(event['gpu'], '1')
            live += 1 if event['event'] == 'started' else -1
            self.assertLessEqual(live, 1)

    def test_multiple_slots_require_permission(self):
        self.args.max_jobs_per_gpu = 2
        with self.assertRaisesRegex(ValueError, 'sharing permission'):
            runner.gpu_queue(self.args, 'invalid', [], ['0'])

    def test_external_status_checks_pid_and_deduplicates(self):
        path = self.output / 'peer.json'
        runner.save_json(path, dict(at=runner.time.time(), active=[
            dict(gpu='0', pid=os.getpid()), dict(gpu='1', pid=99999999)]))
        with patch.object(runner, 'ROOT', Path.cwd()):
            self.assertEqual(runner.external_gpu_jobs([path, path]), {'0': 1})
        runner.save_json(path, dict(at=1, active=[dict(gpu='0', pid=os.getpid())]))
        self.assertEqual(runner.external_gpu_jobs([path]), {})
        with self.assertRaises(FileNotFoundError):
            runner.external_gpu_jobs([self.output / 'missing.json'])

    def simulate(self, fail=None):
        launched, live = [], {}
        successful = []

        class Child:
            def __init__(self, label, gpu):
                self.label, self.gpu = label, gpu
                self.pid = 99999900 + len(launched)
                self.ticks = 12 if label == "fold_0" else 1
                self.returncode = None

            def poll(self):
                if self.returncode is None:
                    self.ticks -= 1
                    if self.ticks <= 0:
                        self.returncode = 2 if self.label == fail else 0
                        live.pop(self.gpu)
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

        def launch(values, **kwargs):
            gpu = kwargs["env"]["CUDA_VISIBLE_DEVICES"]
            self.assertNotIn(gpu, live)
            launched.append((values[0], gpu, set(live)))
            child = Child(values[0], gpu)
            live[gpu] = child
            return child

        with patch.object(runner, "space_check"), \
             patch.object(runner, "idle_gpus", return_value=["0", "1"]), \
             patch.object(runner.subprocess, "Popen", side_effect=launch), \
             patch.object(runner.time, "sleep"):
            jobs = [(f"fold_{i}", [f"fold_{i}"]) for i in range(5)]
            if fail:
                with self.assertRaisesRegex(RuntimeError, fail):
                    runner.gpu_queue(self.args, "training", jobs, ["0", "1"], successful.append)
            else:
                runner.gpu_queue(self.args, "training", jobs, ["0", "1"], successful.append)
        return launched, successful

    def test_fast_gpu_takes_next_fold_without_waiting_for_slow_gpu(self):
        launched, successful = self.simulate()
        self.assertEqual(len(launched), 5)
        self.assertEqual(set(successful), {f"fold_{i}" for i in range(5)})
        self.assertEqual(launched[2][0:2], ("fold_2", "1"))
        self.assertIn("0", launched[2][2])
        events = [json.loads(line) for line in (self.output / "gpu_dispatch.jsonl").read_text().splitlines()]
        self.assertEqual(sum(e["event"] == "started" for e in events), 5)

    def test_failed_fold_does_not_discard_other_jobs(self):
        launched, successful = self.simulate(fail="fold_1")
        self.assertEqual(len(launched), 5)
        self.assertEqual(set(successful), {"fold_0", "fold_2", "fold_3", "fold_4"})

    def test_actual_child_processes_finish_and_write_separate_logs(self):
        # Real subprocess lifecycle; simulated GPU admission only. No CUDA used.
        with patch.object(runner, "space_check"), patch.object(runner, "idle_gpus", return_value=["0", "1"]):
            jobs = [(f"job_{i}", [sys.executable, "-c", f"print('job_{i}')"]) for i in range(3)]
            runner.gpu_queue(self.args, "cpu_test", jobs, ["0", "1"])
        self.assertEqual(len(list(self.output.glob("cpu_test_*.log"))), 3)
        state = json.loads((self.output / "pipeline_status.json").read_text())
        self.assertEqual(len(state["completed"]), 3)
        self.assertFalse(state["active"])

    def test_reserved_gpu_is_not_used_while_prior_queue_active(self):
        self.args.reserved_until_unit = "prior.service"
        self.args.reserved_gpus = ["0"]
        with patch.object(runner, "space_check"), \
             patch.object(runner, "idle_gpus", side_effect=lambda pool, minimum: pool), \
             patch.object(runner.subprocess, "run", return_value=SimpleNamespace(stdout="active\n")):
            runner.gpu_queue(self.args, "reserved", [("job", [sys.executable, "-c", "print('ok')"])], ["0", "1"])
        events = [json.loads(s) for s in (self.output / "gpu_dispatch.jsonl").read_text().splitlines()]
        self.assertEqual([e['gpu'] for e in events if e['event'] == 'started'], ['1'])

    def test_commands_are_isolated_but_model_parameters_unchanged(self):
        args = SimpleNamespace(cohort="hnsc", output=self.output, data=self.output / "data")
        commands = [runner.train_command(args, i) for i in range(5)]
        dirs = {c[c.index("--results_dir") + 1] for c in commands}
        self.assertEqual(len(dirs), 5)
        for i, command in enumerate(commands):
            for flag, value in {"--batch_size": "1", "--max_epochs": "30", "--seed": "1",
                    "--num_patches": "4096", "--mrepath_gene_aggregation": "kan",
                    "--pc_cmka_experiment": "C4_bernoulli_views", "--mrepath_weighting": "dynamic",
                    "--mrepath_fusion": "ifa", "--mrepath_rebalance_variant": "original",
                    "--k_start": str(i), "--k_end": str(i+1)}.items():
                self.assertEqual(command[command.index(flag)+1], value)

    def create_fold(self, fold, legacy=False):
        path = (self.output / "training" / "model" if legacy else
                self.output / "folds" / f"fold_{fold}" / "training" / "model")
        path.mkdir(parents=True, exist_ok=True)
        with (path / "summary.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["fold", "val_cindex"])
            writer.writeheader()
            writer.writerow(dict(fold=fold, val_cindex=0.60+fold*0.01))
        (path / f"split_{fold}_results.pkl").touch()
        (path / f"s_{fold}_best_checkpoint.pt").touch()
        return path

    def test_original_model_switch_changes_only_genomic_experiment(self):
        args = SimpleNamespace(cohort="blca", output=self.output, data=self.output / "data",
                               original_model=True)
        command = runner.train_command(args, 2)
        for flag, value in {"--mrepath_genomic_encoder": "original",
                            "--mrepath_gene_aggregation": "default",
                            "--mrepath_graph_type": "shgnn", "--mrepath_hyperedges": "both",
                            "--mrepath_weighting": "dynamic", "--mrepath_fusion": "ifa",
                            "--mrepath_rebalance_variant": "original", "--seed": "1",
                            "--max_epochs": "30", "--k_start": "2", "--k_end": "3"}.items():
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertNotIn("--pc_cmka_config", command)
        self.assertNotIn("--pc_cmka_experiment", command)
        self.assertEqual(command[command.index("--mrepath_hypergraph_cache_dir") + 1],
                         str(args.data / "hypergraph_cache"))

    def test_merge_out_of_order_folds_and_resume_requires_all_artifacts(self):
        for i in [3, 1, 4, 0, 2]:
            self.create_fold(i)
        result = runner.merge_fold_metrics(self.output)
        self.assertEqual([int(row["fold"]) for row in result], list(range(5)))
        artifact = self.output / "folds/fold_1/training/model/s_1_best_checkpoint.pt"
        artifact.unlink()
        self.assertIsNone(runner.completed_fold(self.output, 1))

    def test_duplicate_complete_legacy_and_parallel_results_are_rejected(self):
        self.create_fold(0)
        self.create_fold(0, legacy=True)
        with self.assertRaisesRegex(RuntimeError, "Ambiguous"):
            runner.completed_fold(self.output, 0)

    @unittest.skipUnless(
        (runner.ROOT / "datasets_csv/metadata/tcga_blca.csv").is_file()
        and (runner.ROOT / "datasets_csv/raw_rna_data/combine/blca/rna_clean.csv").is_file(),
        "BLCA integration fixtures are host-local; host 202 has HNSC only")
    def test_archived_blca_overlap_still_requires_explicit_acceptance(self):
        archive = runner.ROOT / 'splits/archive/pre_author_patient_disjoint_20260914/project/tcga_blca'
        if not archive.is_dir():
            self.skipTest('Historical BLCA split archive is host-local')
        read_rows = runner.rows

        def archived_rows(path):
            path = Path(path)
            if path.parent == runner.ROOT / 'splits/5folds/tcga_blca':
                path = archive / path.name
            return read_rows(path)

        with patch.object(runner, 'rows', side_effect=archived_rows):
            with self.assertRaisesRegex(RuntimeError, "overlapping"):
                runner.audit("blca")
            self.assertEqual([len(f["overlapping_patients"]) for f in runner.audit("blca", True)["folds"]],
                             [11, 13, 13, 13, 13])

    @unittest.skipUnless(
        (runner.ROOT / 'splits/author_patient_disjoint_20260914/manifest.json').is_file()
        and (runner.ROOT / 'datasets_csv/metadata/tcga_blca.csv').is_file(),
        'Author-derived BLCA integration fixtures are host-local')
    def test_active_blca_author_folds_are_patient_disjoint(self):
        report = runner.audit('blca')
        self.assertEqual(report['patients_used_by_repository_splits'], 357)
        self.assertEqual(report['validation_entries'], 357)
        self.assertEqual([len(f['overlapping_patients']) for f in report['folds']], [0] * 5)

    def test_reuse_inventory_requires_unchanged_complete_slide_list(self):
        source = self.output / "source"
        source.mkdir()
        slide = source / "test.svs"
        slide.write_bytes(b"test")
        with (self.output / "wsi_inventory.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["path", "size_bytes", "inventory_error", "patch_mode"])
            writer.writeheader()
            writer.writerow(dict(path=str(slide.resolve()), size_bytes=4, inventory_error="", patch_mode="true-20x"))
        self.assertTrue(runner.reusable_inventory(source, self.output))
        slide.write_bytes(b"changed")
        self.assertFalse(runner.reusable_inventory(source, self.output))
        slide.write_bytes(b"test")
        (source / "extra.svs").write_bytes(b"new")
        self.assertFalse(runner.reusable_inventory(source, self.output))


if __name__ == "__main__":
    unittest.main()
