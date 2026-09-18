"""Adaptive Edge Selection: replace fixed-k neighbours with Softmax(S/T) Top-p.

This is an offline, non-trainable neighbour selector, not a new encoder. Both
branches share exactly two algorithm hyperparameters: p and T. It considers
all other patches in one WSI, not the old graph's fixed-k candidate edges.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

import torch

from utils.hypergraph_cache import CACHE_VERSION, cache_matches, graph_fingerprint


# Execution detail only: changes query batch size, never candidates or scores.
_MAX_SCORE_ELEMENTS = 1_048_576
AES_VERSION = 1


def source_sha256(path: str | Path) -> str:
    """Audit the actual source bytes, including on coarse-timestamp filesystems."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_allocation(required_bytes: int) -> None:
    """Fail instead of truncating neighbours or exhausting a shared Linux host."""
    try:
        with open("/proc/meminfo") as handle:
            available = next(int(line.split()[1]) * 1024 for line in handle
                             if line.startswith("MemAvailable:"))
    except (OSError, StopIteration):
        return
    if required_bytes > available // 2:
        raise MemoryError(
            f"Exact AES incidence needs {required_bytes / 2**30:.2f} GiB; "
            f"available host memory is {available / 2**30:.2f} GiB. "
            "Build aborted, not approximated or capped. Existing caches preserved."
        )


@dataclass(frozen=True)
class AdaptiveEdgeSelection:
    p: float
    T: float

    def __post_init__(self):
        if isinstance(self.p, bool) or not math.isfinite(self.p) or not 0 < self.p <= 1:
            raise ValueError("p must be finite and satisfy 0 < p <= 1")
        if isinstance(self.T, bool) or not math.isfinite(self.T) or self.T <= 0:
            raise ValueError("T must be finite and strictly positive")

    def configuration(self) -> dict:
        return dict(
            method="adaptive_edge_selection", algorithm_version=AES_VERSION,
            p=float(self.p), T=float(self.T),
            topology_score="negative_euclidean_original_coordinate_units",
            feature_score="cosine_cached_patch_features",
            candidate_scope="all_other_patches_within_each_full_wsi",
            center="excluded_from_softmax_then_added_to_hyperedge",
            tie_break="ascending_patch_index_for_equal_probabilities",
            precision="float64_cpu",
        )

    def _select(self, scores: torch.Tensor, centers: torch.Tensor):
        """Return sorted other-node indices and the minimum prefix lengths."""
        scores[torch.arange(len(centers)), centers] = -torch.inf
        # Subtraction before division is algebraically Softmax(S/T), but avoids
        # positive overflow when T is very small. The excluded centre stays -inf.
        logits = (scores - scores.max(dim=1, keepdim=True).values) / self.T
        probabilities = torch.softmax(logits, dim=1)
        # A sorting sentinel, applied AFTER softmax, puts self behind even
        # underflowed zero-probability neighbours. It is never in the prefix.
        probabilities[torch.arange(len(centers)), centers] = -1
        sorted_probabilities, order = torch.sort(
            probabilities, dim=1, descending=True, stable=True
        )
        sorted_probabilities = sorted_probabilities[:, :-1]
        order = order[:, :-1]
        if self.p == 1:
            # Mathematically every finite-score candidate has positive mass.
            # Include all at p=1 even if floating-point exp underflows to zero.
            counts = torch.full((len(centers),), order.shape[1], dtype=torch.long)
        else:
            cumulative = sorted_probabilities.cumsum(dim=1)
            counts = ((cumulative < self.p).sum(dim=1) + 1).clamp(max=order.shape[1])
        return order, counts

    def _batches(self, values: torch.Tensor, branch: str):
        n = len(values)
        rows_per_batch = max(1, _MAX_SCORE_ELEMENTS // n)
        for start in range(0, n, rows_per_batch):
            stop = min(n, start + rows_per_batch)
            centers = torch.arange(start, stop)
            if branch == "topology":
                scores = -torch.cdist(values[start:stop], values, p=2,
                                     compute_mode="donot_use_mm_for_euclid_dist")
            else:
                scores = (values[start:stop] @ values.T).clamp(-1, 1)
            if not torch.isfinite(scores).all():
                raise ValueError(f"Non-finite {branch} relationship scores")
            order, counts = self._select(scores, centers)
            yield centers, order, counts

    def _branch(self, values: torch.Tensor, branch: str) -> dict:
        n = len(values)
        centers = torch.arange(n)
        if n <= 1:
            # No neighbour exists. The unchanged training loader may discard
            # singleton hyperedges, as it already does for induced subgraphs.
            return dict(incidence=torch.stack((centers, centers)), centers=centers,
                        neighbor_counts=torch.zeros(n, dtype=torch.long))

        counts = torch.empty(n, dtype=torch.long)
        # Two passes avoid retaining all score matrices or duplicating a large
        # incidence list during concatenation. Neither pass restricts candidates.
        for ids, _, lengths in self._batches(values, branch):
            counts[ids] = lengths
        entries = n + int(counts.sum())
        _check_allocation(2 * entries * torch.tensor([], dtype=torch.long).element_size())
        incidence = torch.empty((2, entries), dtype=torch.long)
        offsets = torch.cat((torch.zeros(1, dtype=torch.long), (counts + 1).cumsum(0)))
        for ids, order, lengths in self._batches(values, branch):
            if not torch.equal(lengths, counts[ids]):
                raise RuntimeError("AES selections changed between exact construction passes")
            for row, center in enumerate(ids.tolist()):
                first, last = int(offsets[center]), int(offsets[center + 1])
                incidence[0, first] = center
                incidence[0, first + 1:last] = order[row, :int(lengths[row])]
                incidence[1, first:last] = center
        return dict(incidence=incidence, centers=centers, neighbor_counts=counts)

    @torch.no_grad()
    def __call__(self, coords: torch.Tensor, features: torch.Tensor) -> dict:
        coords = torch.as_tensor(coords).detach().to(device="cpu", dtype=torch.float64)
        features = torch.as_tensor(features).detach().to(device="cpu", dtype=torch.float64)
        if coords.ndim != 2 or coords.shape[1] != 2:
            raise ValueError("coords must have shape [N, 2]")
        if features.ndim != 2 or features.shape[0] != len(coords) or features.shape[1] == 0:
            raise ValueError("features must have shape [N, D], with matching N and D > 0")
        if not torch.isfinite(coords).all() or not torch.isfinite(features).all():
            raise ValueError("AES inputs must contain only finite coordinates/features")
        # L2 normalization here is exactly the definition of cosine similarity,
        # not an added score-normalization mechanism or a trainable transform.
        norms = torch.linalg.vector_norm(features, dim=1, keepdim=True)
        if not torch.isfinite(norms).all():
            raise ValueError("Feature norms overflowed")
        normalized = features / torch.where(norms > 0, norms, torch.ones_like(norms))
        # Zero vectors have zero similarity to every other vector (explicit,
        # deterministic convention); equal probabilities use patch-index ties.
        return dict(topology=self._branch(coords, "topology"),
                    feature=self._branch(normalized, "feature"))


def build_adaptive_cache_record(graph, source_path: str | Path, p: float, T: float) -> dict:
    source = graph_fingerprint(source_path)
    digest = source_sha256(source_path)
    selector = AdaptiveEdgeSelection(p, T)
    parts = selector(graph.centroid, graph.x)
    record = dict(version=CACHE_VERSION, source=source, num_nodes=int(graph.x.shape[0]),
                  hyperedge_size=None, construction=selector.configuration(), source_sha256=digest)
    record.update(parts)
    if source != graph_fingerprint(source_path) or digest != source_sha256(source_path):
        raise RuntimeError("Source graph changed during AES construction; cache not published")
    return record


def adaptive_cache_matches(record: dict, source_path: str | Path, p: float, T: float) -> bool:
    return (isinstance(record, dict) and cache_matches(record, source_path)
            and record.get("construction") == AdaptiveEdgeSelection(p, T).configuration()
            and record.get("source_sha256") == source_sha256(source_path))
