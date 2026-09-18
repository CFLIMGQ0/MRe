#!/usr/bin/env python3
"""Build and verify one full-cohort AES cache without touching source graphs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_adaptive_hypergraph_cache import build_one, cache_directory


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=("blca", "brca", "coadread", "stad", "hnsc"), required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--p", type=float, required=True)
    parser.add_argument("--T", type=float, required=True)
    parser.add_argument("--min-free-gib", type=float, default=12.0)
    args = parser.parse_args()
    graph_dir = (ROOT / f"data/tcga_{args.cohort}/clam_20x_resnet50_paper_k9/graph_files").resolve()
    cache_dir = args.cache_dir.resolve()
    sources = sorted(graph_dir.glob("*.pt"))
    if not sources:
        raise FileNotFoundError(f"No source graphs: {graph_dir}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    complete = cache_dir / "complete.json"
    if complete.is_file():
        value = json.loads(complete.read_text())
        if value.get("source_files") != len(sources) or value.get("p") != args.p or value.get("T") != args.T:
            raise RuntimeError("Existing AES completion marker disagrees with requested source/config")
        print(complete.read_text(), flush=True)
        return 0
    torch.set_num_threads(min(4, torch.get_num_threads()))
    counts = dict(built=0, cached=0)
    summaries = []
    with cache_directory(graph_dir, cache_dir, args.p, args.T) as output:
        for index, source in enumerate(sources, 1):
            free = shutil.disk_usage(output).free / 2**30
            if free < args.min_free_gib:
                raise RuntimeError(f"AES disk guard: only {free:.1f} GiB free; existing partial cache preserved")
            print(f"[{index}/{len(sources)}] {source.name} free={free:.1f}GiB", flush=True)
            status, summary = build_one(source, output, args.p, args.T)
            counts[status] += 1
            summaries.append(summary)
            print(json.dumps(dict(status=status, neighbors=summary)), flush=True)
    cache_files = [path for path in cache_dir.glob("*.pt") if not path.name.endswith(".tmp")]
    if len(cache_files) != len(sources):
        raise RuntimeError(f"AES cache coverage mismatch: {len(cache_files)}/{len(sources)}")
    atomic_json(complete, dict(
        cohort=args.cohort, p=args.p, T=args.T, source_graph_dir=str(graph_dir),
        source_files=len(sources), cache_files=len(cache_files), counts=counts,
        source_files_modified=False, completed_at=time.time(),
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
