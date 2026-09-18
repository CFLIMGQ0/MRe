#!/usr/bin/env python3
"""Build separate Adaptive Edge Selection caches; only p and T tune the method.

The original graph/feature files, fixed-k caches, model, and training entry point
are never edited. Uses CPU only. Select the completed output with the existing
training option --mrepath_hypergraph_cache_dir.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.adaptive_edge_selection import (
    AdaptiveEdgeSelection, adaptive_cache_matches, build_adaptive_cache_record, source_sha256,
)
from utils.hypergraph_cache import graph_fingerprint, save_cache_record


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    # Intentionally no defaults: an example/test value must not silently become
    # a scientific experiment's chosen p/T. Both branches use these same values.
    parser.add_argument("--p", type=float, required=True)
    parser.add_argument("--T", type=float, required=True)
    args = parser.parse_args(argv)
    try:
        AdaptiveEdgeSelection(args.p, args.T)
    except ValueError as exc:
        parser.error(str(exc))
    return args


@contextmanager
def cache_directory(graph_dir: Path, cache_dir: Path, p: float, T: float):
    graph_dir, cache_dir = graph_dir.resolve(), cache_dir.resolve()
    if (cache_dir == graph_dir.parent / "hypergraph_cache"
            or cache_dir.is_relative_to(graph_dir) or graph_dir.is_relative_to(cache_dir)):
        raise ValueError("AES needs a separate directory, not source graphs or the fixed-k cache")
    manifest_path = cache_dir / "aes_manifest.json"
    if cache_dir.exists() and not manifest_path.exists():
        if any(path.name != ".aes_build.lock" for path in cache_dir.iterdir()):
            raise FileExistsError("Nonempty unmarked cache directory preserved; choose a new AES directory")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (cache_dir / ".aes_build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        expected = dict(graph_dir=str(graph_dir), construction=AdaptiveEdgeSelection(p, T).configuration())
        if manifest_path.exists():
            if json.loads(manifest_path.read_text()) != expected:
                raise FileExistsError("AES configuration/source mismatch; existing directory preserved")
        else:
            temporary = manifest_path.with_suffix(".json.partial")
            temporary.write_text(json.dumps(expected, indent=2) + "\n")
            temporary.replace(manifest_path)
        yield cache_dir


def build_one(source: Path, cache_dir: Path, p: float, T: float):
    destination = cache_dir / source.name
    if destination.exists():
        record = torch.load(destination, map_location="cpu", weights_only=False, mmap=True)
        if not adaptive_cache_matches(record, source, p, T):
            raise FileExistsError(f"Stale or different cache preserved: {destination}; use a new directory")
        status = "cached"
    else:
        before = graph_fingerprint(source)
        digest = source_sha256(source)
        graph = torch.load(source, map_location="cpu", weights_only=False, mmap=True)
        record = build_adaptive_cache_record(graph, source, p, T)
        if (record["source"] != before or graph_fingerprint(source) != before
                or record["source_sha256"] != digest):
            raise RuntimeError(f"Source changed while loading/building: {source}")
        save_cache_record(record, destination)
        status = "built"
    summary = {}
    for branch in ("topology", "feature"):
        counts = record[branch]["neighbor_counts"]
        summary[branch] = dict(min=int(counts.min()) if counts.numel() else 0,
                               mean=float(counts.double().mean()) if counts.numel() else 0.0,
                               max=int(counts.max()) if counts.numel() else 0)
    return status, summary


def main(argv=None):
    args = parse_args(argv)
    graph_dir = args.graph_dir.resolve()
    sources = sorted(graph_dir.glob("*.pt"))
    if not sources:
        raise FileNotFoundError(f"No source graphs in {graph_dir}")
    # Execution setting, not a model hyperparameter. Avoid competing with the
    # concurrently running experiments for all host CPU threads.
    torch.set_num_threads(min(4, torch.get_num_threads()))
    counts = dict(built=0, cached=0)
    with cache_directory(graph_dir, args.cache_dir, args.p, args.T) as output:
        for index, source in enumerate(sources, 1):
            print(f"[{index}/{len(sources)}] selecting {source.name}", flush=True)
            status, summary = build_one(source, output, args.p, args.T)
            counts[status] += 1
            print(json.dumps(dict(slide=source.name, status=status, neighbors=summary)), flush=True)
    print("[complete] " + json.dumps(counts), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
