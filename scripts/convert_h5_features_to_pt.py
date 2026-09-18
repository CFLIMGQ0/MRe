#!/usr/bin/env python3
"""Convert CLAM HDF5 feature bags to baseline-compatible Torch tensors."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h5-dir", type=Path, required=True)
    parser.add_argument("--pt-dir", type=Path, required=True)
    parser.add_argument("--feature-dim", type=int, default=1024)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = sorted(args.h5_dir.glob("*.h5"))
    if not sources:
        raise FileNotFoundError(f"no HDF5 feature bags under {args.h5_dir}")
    args.pt_dir.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(sources, start=1):
        target = args.pt_dir / f"{source.stem}.pt"
        if target.is_file():
            existing = torch.load(target, map_location="cpu", weights_only=True)
            if existing.ndim == 2 and existing.shape[1] == args.feature_dim:
                continue
        with h5py.File(source, "r") as handle:
            features = torch.from_numpy(handle["features"][:]).float()
        if features.ndim != 2 or features.shape[1] != args.feature_dim:
            raise ValueError(f"invalid features in {source}: {tuple(features.shape)}")
        torch.save(features, target)
        if index % 50 == 0 or index == len(sources):
            print(f"[convert] {index}/{len(sources)}", flush=True)
    print(f"[done] pt feature bags={len(sources)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
