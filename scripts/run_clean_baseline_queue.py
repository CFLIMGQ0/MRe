#!/usr/bin/env python3
"""Patient-disjoint MRePath/PIBD/SurvPath rerun, one project job per GPU."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

from run_hnsc_blca_bernoulli_kan import (
    ROOT, audit, completed_fold, ensure_split_audit_matches, gpu_queue, assert_output_mount,
    save_json, train_command,
)
from run_pibd_survpath_5fold import (
    REPOS, baseline_command, completed, prepare_repo, validate_prepared,
)
from validate_survival_predictions import validate_predictions

MODELS = ('mrepath', 'pibd', 'survpath')
COHORTS = ('blca', 'brca')


def parse_job(value):
    model, cohort, fold = value.split(':')
    fold = int(fold)
    if model not in MODELS or cohort not in COHORTS or fold not in range(5):
        raise ValueError(f'Invalid job: {value}')
    return model, cohort, fold


def check_splits(cohort):
    canonical = ROOT / 'splits/author_patient_disjoint_20260914'
    manifest = json.loads((canonical / 'manifest.json').read_text())['cohorts'][cohort]
    for record in manifest['folds']:
        path = ROOT / f'splits/5folds/tcga_{cohort}/splits_{record["fold"]}.csv'
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise RuntimeError(f'Source split changed: {path}')


def record_for(model, cohort, fold, result_root):
    output = result_root / model / cohort
    record = completed_fold(output, fold) if model == 'mrepath' else completed(model, output, fold)
    if record is None:
        return None
    parent = Path(record['source_summary']).parent
    predictions = parent / f'split_{fold}_results.pkl'
    score = float(record['val_cindex'])
    checked = validate_predictions(predictions, score, cohort, fold, ROOT)
    return dict(model=model, cohort=cohort, fold=fold, val_cindex=score,
                source_summary=record['source_summary'], predictions=str(predictions),
                prediction_audit=checked)


def summarize(model, cohort, result_root):
    records = [r for f in range(5) if (r := record_for(model, cohort, f, result_root))]
    output = result_root / model / cohort
    values = [r['val_cindex'] for r in records]
    save_json(output / 'verified_results.json', dict(
        model=model, cohort=cohort, completed_folds=len(records), folds=records,
        mean=statistics.mean(values) if len(records) == 5 else None,
        std_ddof0=statistics.pstdev(values) if len(records) == 5 else None,
        protocol='author_patient_disjoint_20260914; existing ResNet50; DSS'))


def execute_job(job, result_root):
    model, cohort, fold = parse_job(job)
    check_splits(cohort)
    output = result_root / model / cohort
    fold_root = output / 'folds' / f'fold_{fold}'
    fold_root.mkdir(parents=True, exist_ok=True)
    claim = (fold_root / 'execution.lock').open('a')
    fcntl.flock(claim, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if record_for(model, cohort, fold, result_root):
        return
    training = fold_root / 'training'
    if training.exists() and any(training.iterdir()):
        raise RuntimeError(f'Incomplete prior output retained; inspect before retry: {training}')
    training.mkdir(exist_ok=True)
    data = ROOT / f'data/tcga_{cohort}/clam_20x_resnet50_paper_k9'
    if model == 'mrepath':
        command = train_command(SimpleNamespace(cohort=cohort, data=data, output=output,
                                                original_model=True), fold)
        cwd = ROOT
    else:
        command = baseline_command(model, cohort, fold, training)
        cwd = REPOS[model]
        for f in range(5):
            source = ROOT / f'splits/5folds/tcga_{cohort}/splits_{f}.csv'
            if source.read_bytes() != (cwd / f'splits/5foldcv/tcga_{cohort}/splits_{f}.csv').read_bytes():
                raise RuntimeError('Baseline split differs from project')
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'scripts'), PYTHONDONTWRITEBYTECODE='1',
               MREPATH_NUM_WORKERS='0', PYTHONWARNINGS='ignore')
    save_json(fold_root / 'invocation.json', dict(command=command, cwd=str(cwd),
              gpu=env.get('CUDA_VISIBLE_DEVICES'), at=time.time(),
              protocol='author_patient_disjoint_20260914'))
    os.set_inheritable(claim.fileno(), True)
    os.chdir(cwd)
    os.execve(sys.executable, command, env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-root', type=Path, required=True)
    parser.add_argument('--queue-name', required=True)
    parser.add_argument('--gpus', nargs='+', required=True)
    parser.add_argument('--jobs', nargs='+')
    parser.add_argument('--execute-one')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--allow-gpu-sharing', action='store_true')
    parser.add_argument('--min-gpu-free-mib', type=int, default=18000)
    parser.add_argument('--min-free-gib', type=float, default=60)
    parser.add_argument('--gpu-poll-seconds', type=int, default=15)
    parser.add_argument('--reserve-manifest', type=Path)
    parser.add_argument('--reserve-raw', type=Path)
    parser.add_argument('--storage-mount', type=Path,
                        help='Require this mounted filesystem; never write to a local fallback')
    parser.add_argument('--reserve-gib', type=float, default=0,
                        help='Additional remote-disk reservation, on top of min-free-gib')
    args = parser.parse_args()
    args.results_root = args.results_root.resolve()
    if args.reserve_gib < 0 or args.min_free_gib <= 0:
        parser.error('Disk reservations must be nonnegative and minimum free space positive')
    assert_output_mount(args.results_root, args.storage_mount)
    if args.execute_one:
        execute_job(args.execute_one, args.results_root)
        return
    if not args.jobs or len(args.jobs) != len(set(args.jobs)):
        parser.error('Supply unique jobs')
    if len(args.gpus) != len(set(args.gpus)) or any(not g.isdigit() for g in args.gpus):
        parser.error('Supply unique numeric GPUs')
    if bool(args.reserve_manifest) != bool(args.reserve_raw):
        parser.error('Both reserve arguments are required together')
    parsed = [parse_job(job) for job in args.jobs]
    args.output = args.results_root / args.queue_name
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / 'queue.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # A host-wide project queue lock prevents two queues claiming the same GPU.
    host_lock = (ROOT / 'results/.author_clean_gpu_queue.lock').open('a')
    fcntl.flock(host_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    args.max_jobs_per_gpu = 1
    args.shared_queue_status = []
    args.data = ROOT / f'data/tcga_{parsed[0][1]}/clam_20x_resnet50_paper_k9'
    for model, cohort in sorted({(m, c) for m, c, _ in parsed}):
        check_splits(cohort)
        output = args.results_root / model / cohort
        data = ROOT / f'data/tcga_{cohort}/clam_20x_resnet50_paper_k9'
        report = audit(cohort, data=data) if model == 'mrepath' else validate_prepared(cohort)
        ensure_split_audit_matches(output, report)
        output.mkdir(parents=True, exist_ok=True)
        save_json(output / 'split_audit.json', report)
        if model != 'mrepath':
            save_json(output / 'source_manifest.json', prepare_repo(model, cohort))
        summarize(model, cohort, args.results_root)
    pending = []
    for job in args.jobs:
        model, cohort, fold = parse_job(job)
        if record_for(model, cohort, fold, args.results_root):
            continue
        command = [sys.executable, '-u', str(Path(__file__).resolve()),
            '--results-root', str(args.results_root), '--queue-name', args.queue_name,
            '--gpus', *args.gpus, '--execute-one', job]
        if args.storage_mount:
            command += ['--storage-mount', str(args.storage_mount)]
        pending.append((job.replace(':', '_'), command))
    save_json(args.output / 'run_manifest.json', dict(
        at=time.time(), jobs=args.jobs, gpu_candidates=args.gpus, max_jobs_per_gpu=1,
        allow_gpu_sharing=args.allow_gpu_sharing, pending_commands=pending,
        storage_mount=str(args.storage_mount) if args.storage_mount else None,
        min_free_gib=args.min_free_gib, reserve_gib=args.reserve_gib,
        protocol='Original model structures, existing ResNet50, DSS, seed=1, 30 epochs; no AES/KAN'))
    if args.prepare_only:
        return

    def on_success(label):
        model, cohort, fold = parse_job(label.replace('_', ':'))
        record = record_for(model, cohort, fold, args.results_root)
        if record is None:
            raise RuntimeError(f'Missing verified result: {label}')
        save_json(args.results_root / model / cohort / 'folds' / f'fold_{fold}' / 'prediction_audit.json',
                  record['prediction_audit'])
        summarize(model, cohort, args.results_root)

    try:
        gpu_queue(args, 'training', pending, args.gpus, on_success)
        save_json(args.output / 'pipeline_status.json', dict(state='completed', at=time.time()))
    except BaseException as exc:
        save_json(args.output / 'pipeline_status.json', dict(state='stopped', error=repr(exc), at=time.time()))
        raise


if __name__ == '__main__':
    main()
