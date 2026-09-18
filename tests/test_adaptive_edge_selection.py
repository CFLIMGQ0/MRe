"""AES correctness, cache isolation and unchanged MRePath integration tests.

All p/T values here are test fixtures, NOT selected experiment settings.
Run on CPU: python -m unittest discover -s tests -p test_adaptive_edge_selection.py -v
"""
import contextlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import utils.adaptive_edge_selection as aes
from utils.hypergraph_cache import build_cache_record, load_cache_record, save_cache_record
from scripts import build_adaptive_hypergraph_cache as builder


def members(part, center):
    return part["incidence"][0, part["incidence"][1] == center].tolist()


def reference_members(coords, features, center, p, T, branch):
    """Small independent Python reference; no batched tensor selection."""
    scores = []
    for index in range(len(coords)):
        if index == center:
            continue
        if branch == "topology":
            score = -math.dist(coords[center], coords[index])
        else:
            left, right = features[center], features[index]
            norm = math.sqrt(sum(v*v for v in left)) * math.sqrt(sum(v*v for v in right))
            score = sum(a*b for a, b in zip(left, right)) / norm if norm else 0.0
        scores.append((index, score))
    if not scores:
        return [center]
    maximum = max(score for _, score in scores)
    unscaled = [(index, math.exp((score-maximum)/T)) for index, score in scores]
    total = sum(value for _, value in unscaled)
    probabilities = sorted(((i, v/total) for i, v in unscaled), key=lambda pair: (-pair[1], pair[0]))
    selected, cumulative = [center], 0.0
    for index, probability in probabilities:
        selected.append(index)
        cumulative += probability
        if p < 1 and cumulative >= p:
            break
    return selected


class AESAlgorithmTests(unittest.TestCase):
    def setUp(self):
        generator = torch.Generator().manual_seed(13)
        self.coords = torch.tensor([[0., 0.], [1., 0.], [0., 2.], [3., 0.], [9., 2.]], dtype=torch.float64)
        self.features = torch.randn(5, 7, generator=generator, dtype=torch.float64)

    def test_exactly_two_algorithm_parameters(self):
        self.assertEqual(list(inspect.signature(aes.AdaptiveEdgeSelection).parameters), ["p", "T"])
        self.assertFalse(isinstance(aes.AdaptiveEdgeSelection(.9, .1), torch.nn.Module))

    def test_invalid_p_and_T(self):
        for p in [0, -.1, 1.01, float("nan"), float("inf"), True]:
            with self.subTest(p=p), self.assertRaises(ValueError):
                aes.AdaptiveEdgeSelection(p, 1)
        for T in [0, -1, float("nan"), float("inf"), True]:
            with self.subTest(T=T), self.assertRaises(ValueError):
                aes.AdaptiveEdgeSelection(.9, T)

    def test_both_branches_match_independent_reference(self):
        for p, T in [(.21, .17), (.72, .45), (.94, 2.1), (1., .01)]:
            with self.subTest(p=p, T=T):
                output = aes.AdaptiveEdgeSelection(p, T)(self.coords, self.features)
                for branch in ["topology", "feature"]:
                    for center in range(len(self.coords)):
                        expected = reference_members(self.coords.tolist(), self.features.tolist(), center, p, T, branch)
                        self.assertEqual(members(output[branch], center), expected)

    def test_threshold_crossing_includes_last_neighbor_and_exact_equality_stops(self):
        scores = torch.zeros(1, 5, dtype=torch.float64)
        for p, expected in [(.5, 2), (.6, 3)]:
            order, counts = aes.AdaptiveEdgeSelection(p, 1)._select(scores.clone(), torch.tensor([0]))
            self.assertEqual(counts.tolist(), [expected])
            self.assertEqual(order[0, :expected].tolist(), list(range(1, expected+1)))

    def test_center_is_excluded_from_softmax_and_added_once(self):
        # A huge self-score must not absorb the probability distribution.
        order, counts = aes.AdaptiveEdgeSelection(.5, .5)._select(
            torch.tensor([[1e10, 0., 0., 0., 0.]], dtype=torch.float64), torch.tensor([0]))
        self.assertEqual(counts.tolist(), [2])
        self.assertNotIn(0, order[0].tolist())
        result = aes.AdaptiveEdgeSelection(.9, 1)(self.coords, self.features)
        for part in result.values():
            for center in range(5):
                nodes = members(part, center)
                self.assertEqual(nodes.count(center), 1)
                self.assertEqual(len(nodes), len(set(nodes)))
                self.assertEqual(len(nodes)-1, int(part["neighbor_counts"][center]))

    def test_temperature_changes_neighbor_count_without_changing_p(self):
        scores = torch.tensor([[99., 0., -1., -2., -3.]], dtype=torch.float64)
        cold = aes.AdaptiveEdgeSelection(.9, .01)._select(scores.clone(), torch.tensor([0]))[1]
        hot = aes.AdaptiveEdgeSelection(.9, 100)._select(scores.clone(), torch.tensor([0]))[1]
        self.assertEqual(cold.tolist(), [1])
        self.assertEqual(hot.tolist(), [4])

    def test_no_hidden_fixed_k_cap_and_p_one_includes_underflowed_candidates(self):
        coords = torch.stack((torch.arange(25), torch.zeros(25)), dim=1)
        features = torch.eye(25)
        result = aes.AdaptiveEdgeSelection(1., 1e-300)(coords, features)
        for part in result.values():
            self.assertEqual(part["neighbor_counts"].tolist(), [24]*25)
            self.assertEqual(tuple(part["incidence"].shape), (2, 625))

    def test_p_monotonicity(self):
        previous = None
        for p in [.1, .4, .8, 1.]:
            current = aes.AdaptiveEdgeSelection(p, .3)(self.coords, self.features)
            if previous is not None:
                for branch in current:
                    self.assertTrue(torch.all(current[branch]["neighbor_counts"] >= previous[branch]["neighbor_counts"]))
            previous = current

    def test_equal_probability_ties_are_deterministic_and_zero_vectors_are_supported(self):
        output = aes.AdaptiveEdgeSelection(.5, 1)(torch.zeros(5, 2), torch.zeros(5, 3))
        for part in output.values():
            self.assertEqual(members(part, 3), [3, 0, 1])
            self.assertEqual(members(part, 0), [0, 1, 2])

    def test_chunking_does_not_change_selections(self):
        baseline = aes.AdaptiveEdgeSelection(.81, .29)(self.coords, self.features)
        with patch.object(aes, "_MAX_SCORE_ELEMENTS", 5):
            chunked = aes.AdaptiveEdgeSelection(.81, .29)(self.coords, self.features)
        for branch in baseline:
            self.assertTrue(torch.equal(baseline[branch]["incidence"], chunked[branch]["incidence"]))

    def test_empty_singleton_and_two_nodes(self):
        for n in [0, 1, 2]:
            output = aes.AdaptiveEdgeSelection(.9, 1)(torch.zeros(n, 2), torch.zeros(n, 3))
            for part in output.values():
                self.assertEqual(part["centers"].tolist(), list(range(n)))
                self.assertEqual(part["neighbor_counts"].tolist(), [max(0, n-1)]*n)
                self.assertEqual(part["incidence"].shape[0], 2)

    def test_inputs_are_not_mutated_and_no_rng_or_gradients_are_added(self):
        features = self.features.clone().requires_grad_()
        coords = self.coords.clone()
        rng = torch.random.get_rng_state().clone()
        output = aes.AdaptiveEdgeSelection(.8, .2)(coords, features)
        self.assertTrue(torch.equal(features, self.features))
        self.assertTrue(torch.equal(coords, self.coords))
        self.assertTrue(torch.equal(torch.random.get_rng_state(), rng))
        self.assertTrue(all(not part["incidence"].requires_grad for part in output.values()))

    def test_invalid_input_shapes_and_nonfinite_values_fail(self):
        for coords, features in [(torch.zeros(5, 3), self.features),
                (self.coords, torch.zeros(4, 2)), (self.coords, torch.zeros(5, 0)),
                (self.coords*float("nan"), self.features),
                (self.coords, self.features*float("inf"))]:
            with self.assertRaises(ValueError):
                aes.AdaptiveEdgeSelection(.8, 1)(coords, features)

    def test_memory_guard_aborts_instead_of_capping_edges(self):
        with patch("builtins.open", return_value=io.StringIO("MemAvailable: 1 kB\n")):
            with self.assertRaisesRegex(MemoryError, "not approximated or capped"):
                aes._check_allocation(10000)


class AESCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mrepath_aes_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.graph_dir = self.root / "graph_files"
        self.graph_dir.mkdir()
        self.cache_dir = self.root / "hypergraph_cache_aes"
        self.source = self.graph_dir / "fixture.pt"
        generator = torch.Generator().manual_seed(23)
        index = torch.arange(8)
        self.graph = SimpleNamespace(
            x=torch.randn(8, 1024, generator=generator),
            centroid=torch.stack((index*256, torch.zeros(8)), dim=1),
            edge_index=torch.stack((index, (index+1) % 8)),
            edge_latent=torch.stack((index, (index+2) % 8)), hyperedge_size=9)
        torch.save(self.graph, self.source)

    def build(self, p=.8, T=.2):
        with builder.cache_directory(self.graph_dir, self.cache_dir, p, T):
            return builder.build_one(self.source, self.cache_dir, p, T)

    def test_new_cache_loads_through_unchanged_loader_and_resume_preserves_bytes(self):
        source_before = self.source.read_bytes()
        self.assertEqual(self.build()[0], "built")
        path = self.cache_dir / self.source.name
        first, mtime = path.read_bytes(), path.stat().st_mtime_ns
        record = load_cache_record(self.source, self.cache_dir)
        self.assertIsNone(record["hyperedge_size"])
        self.assertEqual(record["construction"]["method"], "adaptive_edge_selection")
        self.assertEqual(self.build()[0], "cached")
        self.assertEqual(path.read_bytes(), first)
        self.assertEqual(path.stat().st_mtime_ns, mtime)
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_p_or_T_change_cannot_reuse_or_overwrite_existing_directory(self):
        self.build()
        original = (self.cache_dir / self.source.name).read_bytes()
        for p, T in [(.7, .2), (.8, .3)]:
            with self.assertRaisesRegex(FileExistsError, "configuration/source mismatch"):
                self.build(p, T)
        self.assertEqual((self.cache_dir / self.source.name).read_bytes(), original)

    def test_fixed_k_cache_is_never_overwritten_or_misidentified_as_aes(self):
        fixed = self.root / "hypergraph_cache"
        fixed.mkdir()
        old = build_cache_record(self.graph, self.source)
        save_cache_record(old, fixed / self.source.name)
        original = (fixed / self.source.name).read_bytes()
        self.assertFalse(aes.adaptive_cache_matches(old, self.source, .8, .2))
        with self.assertRaises(ValueError):
            with builder.cache_directory(self.graph_dir, fixed, .8, .2):
                self.fail("Must not enter baseline directory")
        self.assertEqual((fixed / self.source.name).read_bytes(), original)
        self.assertEqual(list(p.name for p in fixed.iterdir()), [self.source.name])

    def test_unmarked_directory_and_source_directory_are_rejected(self):
        self.cache_dir.mkdir()
        (self.cache_dir / "keep.txt").write_text("user cache")
        for path, error in [(self.cache_dir, FileExistsError), (self.graph_dir, ValueError),
                            (self.root, ValueError), (self.graph_dir / "nested", ValueError)]:
            with self.assertRaises(error):
                with builder.cache_directory(self.graph_dir, path, .8, .2):
                    self.fail("Must reject directory")
        self.assertEqual((self.cache_dir / "keep.txt").read_text(), "user cache")

    def test_source_change_invalidates_cache_without_overwrite(self):
        self.build()
        path = self.cache_dir / self.source.name
        old = path.read_bytes()
        stat = self.source.stat()
        self.graph.x = self.graph.x + 1
        torch.save(self.graph, self.source)
        # Same-sized, same-mtime replacements still invalidate AES by SHA256.
        os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaisesRegex(FileExistsError, "Stale or different"):
            self.build()
        self.assertEqual(path.read_bytes(), old)

    def test_old_pairwise_edges_are_not_a_candidate_filter(self):
        first = aes.build_adaptive_cache_record(self.graph, self.source, .9, 1)
        self.graph.edge_index = torch.empty((2, 0), dtype=torch.long)
        self.graph.edge_latent = torch.empty((2, 0), dtype=torch.long)
        second = aes.build_adaptive_cache_record(self.graph, self.source, .9, 1)
        for branch in ["topology", "feature"]:
            self.assertTrue(torch.equal(first[branch]["incidence"], second[branch]["incidence"]))

    def test_same_directory_cannot_have_two_builders(self):
        with builder.cache_directory(self.graph_dir, self.cache_dir, .8, .2):
            with self.assertRaises(BlockingIOError):
                with builder.cache_directory(self.graph_dir, self.cache_dir, .8, .2):
                    self.fail("Duplicate builder")

    def test_cli_requires_explicit_p_and_T_and_builds_without_new_training_flags(self):
        paths = ["--graph-dir", str(self.graph_dir), "--cache-dir", str(self.cache_dir)]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                builder.parse_args(paths)
            with self.assertRaises(SystemExit):
                builder.parse_args(paths + ["--p", ".8", "--T", "0"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(builder.main(paths + ["--p", ".8", "--T", ".2"]), 0)
        self.assertTrue((self.cache_dir / "aes_manifest.json").is_file())

    def test_failed_build_does_not_publish_a_complete_cache(self):
        with patch.object(builder, "build_adaptive_cache_record", side_effect=MemoryError("test allocation")):
            with self.assertRaises(MemoryError):
                self.build()
        self.assertFalse((self.cache_dir / self.source.name).exists())

    def test_original_sampling_loader_accepts_aes_and_preserves_feature_rows(self):
        from datasets.dataset_survival import SurvivalDataset
        self.build()
        dataset = SimpleNamespace(hypergraph_cache_dir=str(self.cache_dir), num_patches=6, sample=False)
        features, graph = SurvivalDataset._load_wsi_embs_from_path(dataset, str(self.root), ["fixture.svs"])
        self.assertTrue(torch.equal(features, self.graph.x[:6]))
        for name in ["hyperedge_topology", "hyperedge_feature"]:
            H = getattr(graph, name)
            self.assertEqual(H.shape[0], 2)
            self.assertTrue(bool((H[0] < 6).all()))
        self.assertEqual(graph.edge_index.numel(), 0)

    def test_patient_with_two_slides_has_no_cross_slide_hyperedges(self):
        from datasets.dataset_survival import SurvivalDataset
        self.build()
        second = self.graph_dir / "second.pt"
        torch.save(self.graph, second)
        with builder.cache_directory(self.graph_dir, self.cache_dir, .8, .2):
            builder.build_one(second, self.cache_dir, .8, .2)
        dataset = SimpleNamespace(hypergraph_cache_dir=str(self.cache_dir), num_patches=16, sample=False)
        _, graph = SurvivalDataset._load_wsi_embs_from_path(dataset, str(self.root), ["fixture.svs", "second.svs"])
        for name in ["hyperedge_topology", "hyperedge_feature"]:
            H = getattr(graph, name)
            for edge in torch.unique(H[1]):
                nodes = H[0, H[1] == edge]
                self.assertEqual(len(torch.unique(nodes // 8)), 1)

    def test_original_sheaf_dynamic_ifa_and_nll_forward_backward_on_cpu(self):
        # CPU-only integration: change the TEST INSTANCE's allocation device,
        # not the original Sheaf forward implementation or any production file.
        from datasets.dataset_survival import SurvivalDataset
        from models.model_HGNN import MRePath
        from utils.loss_func import NLLSurvLoss
        self.build()
        dataset = SimpleNamespace(hypergraph_cache_dir=str(self.cache_dir), num_patches=6, sample=False)
        features, graph = SurvivalDataset._load_wsi_embs_from_path(dataset, str(self.root), ["fixture.svs"])
        torch.manual_seed(17)
        model = MRePath(omic_sizes=[3]*6, num_patches=6, genomic_encoder="original",
                       gene_aggregation="default", graph_type="shgnn", hyperedge_mode="both",
                       weighting_mode="dynamic", fusion_variant="ifa", rebalance_variant="original").eval()
        for conv in model.convs:
            conv.device = torch.device("cpu")
        keys = set(model.state_dict())
        inputs = {f"x_omic{i}": torch.randn(1, 3) for i in range(1, 7)}
        logits = model(x_path=features, graph=graph, **inputs)
        loss = NLLSurvLoss()(logits, torch.tensor([1]), torch.tensor([2.]), torch.tensor([0.]))
        loss.backward()
        self.assertEqual(logits.shape, (1, 4))
        self.assertTrue(torch.isfinite(loss))
        self.assertTrue(all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters()))
        for name in ["pathomics_fc", "convs", "dynamic_weighting", "attention_fusion", "classifier"]:
            self.assertTrue(any(p.grad is not None and p.grad.abs().sum() > 0 for p in getattr(model, name).parameters()), name)
        aes_sheaf_grad_presence = [p.grad is not None for p in model.sheaf_builder.parameters()]
        self.assertEqual(set(model.state_dict()), keys)
        # Switch back to baseline cache with the SAME model/inputs, then back
        # to AES. No forward modules, weights or input dimensions are replaced.
        fixed = self.root / "hypergraph_cache"
        fixed.mkdir()
        save_cache_record(build_cache_record(self.graph, self.source), fixed / self.source.name)
        dataset.hypergraph_cache_dir = str(fixed)
        old_features, old_graph = SurvivalDataset._load_wsi_embs_from_path(dataset, str(self.root), ["fixture.svs"])
        model.zero_grad(set_to_none=True)
        old_logits = model(x_path=old_features, graph=old_graph, **inputs)
        NLLSurvLoss()(old_logits, torch.tensor([1]), torch.tensor([2.]), torch.tensor([0.])).backward()
        baseline_sheaf_grad_presence = [p.grad is not None for p in model.sheaf_builder.parameters()]
        self.assertEqual(aes_sheaf_grad_presence, baseline_sheaf_grad_presence)
        if not any(baseline_sheaf_grad_presence):
            print("[existing_cpu_behavior] sheaf_builder parameter gradients are absent in BOTH "
                  "fixed-k and AES; diffusion-layer gradients are present. Original Sheaf code unchanged.", flush=True)
        again = model(x_path=features, graph=graph, **inputs)
        self.assertTrue(torch.isfinite(old_logits).all())
        torch.testing.assert_close(again, logits, rtol=0, atol=0)


if __name__ == "__main__":
    unittest.main()
