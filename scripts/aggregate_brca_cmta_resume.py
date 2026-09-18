#!/usr/bin/env python3
"""Combine completed original CMTA folds with fold-level resumed runs."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import numpy as np


CHECKPOINT_RE = re.compile(r"model_best_([0-9.]+)_([0-9]+)\.pth\.tar$")


def checkpoint_metric(fold_dir: Path) -> tuple[int, float]:
    candidates = []
    for path in fold_dir.glob("model_best_*.pth.tar"):
        match = CHECKPOINT_RE.match(path.name)
        if match:
            candidates.append((int(match.group(2)), float(match.group(1))))
    if not candidates:
        raise FileNotFoundError(f"no CMTA best checkpoint in {fold_dir}")
    return max(candidates, key=lambda item: item[1])


def resumed_metric(csv_path: Path, expected_fold: int) -> tuple[int, float]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if int(row["fold"]) == expected_fold:
            return int(float(row["best_epoch"])), float(row["best_cindex"])
    raise ValueError(f"fold {expected_fold} is absent from {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-run", type=Path, required=True)
    parser.add_argument("--resume-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = []
    for fold in range(3):
        epoch, score = checkpoint_metric(args.original_run / f"fold_{fold}")
        records.append((fold, epoch, score, "original_run"))
    for fold in (3, 4):
        epoch, score = resumed_metric(
            args.resume_root / f"fold_{fold}" / "partial_results.csv", fold
        )
        records.append((fold, epoch, score, "resumed_fold"))

    scores = np.asarray([record[2] for record in records], dtype=float)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fold", "best_epoch", "best_cindex", "source"])
        writer.writerows(records)
        writer.writerow(["mean", "", float(scores.mean()), ""])
        writer.writerow(["std", "", float(scores.std()), ""])
    print(f"CMTA mean={scores.mean():.6f}, std={scores.std():.6f}")


if __name__ == "__main__":
    main()
