#!/usr/bin/env python3
"""Run one model/cohort task (five folds), with fold-level resume and logs."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_hnsc_blca_bernoulli_kan import train_command
from run_pc_cmka_word_ablations import available, command as mrepath_command


COHORTS = ("blca", "brca", "coadread", "stad", "hnsc")
EXTERNAL = ("ld_cvae", "dimaf", "slotspe")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("external", "m3", "aes"), required=True)
    parser.add_argument("--model", choices=EXTERNAL)
    parser.add_argument("--cohort", choices=COHORTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aes-cache", type=Path)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--num-workers", type=int, default=2)
    return parser.parse_args()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def read_rows(path: Path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def mrepath_fold_result(root: Path, fold: int):
    matches = []
    for summary in root.glob(f"folds/fold_{fold}/training/**/summary.csv"):
        for row in read_rows(summary):
            if int(float(row.get("fold", -1))) != fold:
                continue
            parent = summary.parent
            checkpoint = parent / f"s_{fold}_best_checkpoint.pt"
            predictions = parent / f"split_{fold}_results.pkl"
            if checkpoint.is_file() and predictions.is_file():
                matches.append(dict(fold=fold, val_cindex=float(row["val_cindex"]),
                                    summary=str(summary), checkpoint=str(checkpoint),
                                    predictions=str(predictions)))
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous fold {fold} results under {root}")
    return matches[0] if matches else None


def external_fold_result(root: Path, fold: int):
    complete = root / f"folds/fold_{fold}/complete.json"
    if not complete.is_file():
        return None
    value = json.loads(complete.read_text())
    checkpoint = complete.parent / "best_checkpoint.pt"
    predictions = complete.parent / "predictions.pkl"
    if not checkpoint.is_file() or not predictions.is_file():
        return None
    return dict(fold=fold, val_cindex=float(value["val_cindex"]), best_epoch=int(value["best_epoch"]),
                checkpoint=str(checkpoint), predictions=str(predictions))


def run_external(args, fold):
    output = args.output / f"folds/fold_{fold}"
    return [
        sys.executable, "-u", str(ROOT / "scripts/run_resnet50_repository_model.py"),
        "--model", args.model, "--cohort", args.cohort, "--fold", str(fold),
        "--output", str(output), "--epochs", str(args.epochs),
        # Large variable-bag tensors can exhaust Unix ancillary file
        # descriptors when passed from DataLoader worker processes (observed on
        # host202).  Synchronous loading changes I/O scheduling only, not model
        # inputs or optimization, and is the reliable repository-adapter mode.
        "--max-patches", "4096", "--num-workers", "0", "--seed", "1",
    ]


def dataset(cohort):
    return dict(
        study=f"tcga_{cohort}",
        data=ROOT / f"data/tcga_{cohort}/clam_20x_resnet50_paper_k9",
        labels=ROOT / f"datasets_csv/metadata/tcga_{cohort}.csv",
        omics=ROOT / f"datasets_csv/raw_rna_data/combine/{cohort}",
    )


def run_m3(args, fold):
    config = ROOT / "configs/pc_cmka_ddkac_word.json"
    experiment = next(item for item in available(config, "all", True)
                      if item["name"] == "BK_I03_mask2spline_hyperkan")
    values = mrepath_command(
        dataset(args.cohort), config, experiment, fold,
        SimpleNamespace(num_workers=args.num_workers, max_epochs=args.epochs, num_patches=4096),
        args.output / "folds" / f"fold_{fold}" / "training",
    )
    values[0] = sys.executable
    return values


def run_aes(args, fold):
    if args.aes_cache is None:
        raise ValueError("AES training requires --aes-cache")
    cache_manifest = args.aes_cache / "complete.json"
    if not cache_manifest.is_file():
        raise RuntimeError(f"AES cache is not complete: {cache_manifest}")
    values = train_command(
        SimpleNamespace(
            cohort=args.cohort,
            data=dataset(args.cohort)["data"],
            output=args.output,
            original_model=True,
        ),
        fold,
    )
    values[0] = sys.executable
    position = values.index("--mrepath_hypergraph_cache_dir") + 1
    values[position] = str(args.aes_cache)
    epochs_at = values.index("--max_epochs") + 1
    values[epochs_at] = str(args.epochs)
    workers_at = values.index("--num_workers") + 1
    values[workers_at] = str(args.num_workers)
    return values


def run_logged(command, cwd: Path, log_path: Path, heartbeat_path: Path, fold: int):
    """Run a fold with an external heartbeat for unattended health checks."""
    with log_path.open("a") as log:
        child = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        while True:
            try:
                code = child.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                try:
                    stat = log_path.stat()
                    log_size, log_mtime = stat.st_size, stat.st_mtime
                except FileNotFoundError:
                    log_size, log_mtime = 0, None
                atomic_json(heartbeat_path, dict(
                    state="running", fold=fold, wrapper_pid=os.getpid(), child_pid=child.pid,
                    checked_at=time.time(), log=str(log_path), log_size=log_size,
                    log_mtime=log_mtime,
                ))
        atomic_json(heartbeat_path, dict(
            state="exited", fold=fold, wrapper_pid=os.getpid(), child_pid=child.pid,
            checked_at=time.time(), exit_code=code, log=str(log_path),
        ))
        return code


def main():
    args = parse_args()
    if args.kind == "external" and args.model is None:
        raise ValueError("External task requires --model")
    if args.kind != "external" and args.model is not None:
        raise ValueError("--model only belongs to external tasks")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    complete_path = args.output / "complete.json"
    if complete_path.is_file():
        print(complete_path.read_text(), flush=True)
        return 0
    atomic_json(args.output / "task_manifest.json", dict(
        kind=args.kind, model=args.model, cohort=args.cohort, epochs=args.epochs,
        num_workers=args.num_workers, aes_cache=str(args.aes_cache.resolve()) if args.aes_cache else None,
        feature_protocol="existing ResNet50 1024-D caches; originals read-only",
        folds=list(range(5)), started_at=time.time(),
    ))
    for fold in range(5):
        existing = external_fold_result(args.output, fold) if args.kind == "external" else mrepath_fold_result(args.output, fold)
        if existing:
            print(f"skip complete fold {fold}: {existing['val_cindex']}", flush=True)
            continue
        command = (run_external(args, fold) if args.kind == "external" else
                   run_m3(args, fold) if args.kind == "m3" else run_aes(args, fold))
        fold_dir = args.output / "folds" / f"fold_{fold}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(fold_dir / "invocation.json", dict(argv=command, cwd=str(ROOT), at=time.time(),
                                                         cuda_visible_devices=os.getenv("CUDA_VISIBLE_DEVICES")))
        log_path = fold_dir / "task.log"
        returncode = run_logged(command, ROOT, log_path, args.output / "heartbeat.json", fold)
        if returncode:
            raise RuntimeError(f"fold {fold} failed with exit {returncode}; see {log_path}")
        record = external_fold_result(args.output, fold) if args.kind == "external" else mrepath_fold_result(args.output, fold)
        if record is None:
            raise RuntimeError(f"fold {fold} exited without complete checkpoint/predictions/metric")
    records = [external_fold_result(args.output, fold) if args.kind == "external" else mrepath_fold_result(args.output, fold)
               for fold in range(5)]
    values = [record["val_cindex"] for record in records]
    atomic_json(complete_path, dict(
        kind=args.kind, model=args.model, cohort=args.cohort, folds=records,
        mean=statistics.mean(values), std_ddof0=statistics.pstdev(values), completed_at=time.time(),
    ))
    atomic_json(args.output / "heartbeat.json", dict(
        state="completed", checked_at=time.time(), folds=5,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
