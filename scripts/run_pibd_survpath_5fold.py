#!/usr/bin/env python3
"""Run pinned official baselines on project cohorts; isolate every fold's output."""
import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

from run_hnsc_blca_bernoulli_kan import audit, gpu_queue, rows, save_json, ensure_split_audit_matches
from validate_survival_predictions import validate_predictions

ROOT = Path(__file__).resolve().parents[1]
REPOS = {'pibd': ROOT / 'third_party/PIBD_20260913',
         'survpath': ROOT / 'third_party/SurvPath_20260913'}
COMMITS = {'pibd': 'bd5bd94e6f8d48e7679c6e68209a3a65c9e56a78',
           'survpath': '3f73ddd6705ec67d643020c5bb04fb13f9f382cc'}


def data_root(cohort):
    return ROOT / f'data/tcga_{cohort}/clam_20x_resnet50_paper_k9'


def validate_prepared(cohort):
    report = audit(cohort, allow_overlap=False)
    data = data_root(cohort)
    metadata = rows(ROOT / f'datasets_csv/metadata/tcga_{cohort}.csv')
    used = set()
    for fold in range(5):
        for row in rows(ROOT / f'splits/5folds/tcga_{cohort}/splits_{fold}.csv'):
            used.update(row.get(key, '') for key in ('train', 'val'))
    rna_ids = {row[next(iter(row))] for row in rows(ROOT / f'datasets_csv/raw_rna_data/combine/{cohort}/rna_clean.csv')}
    names = {Path(r['slide_id']).stem for r in metadata if r['case_id'] in used & rna_ids}
    missing = [name for name in sorted(names) if not any((data / sub / (name + suffix)).is_file()
               for sub, suffix in [('pt_files', '.pt'), ('h5_files', '.h5'), ('graph_files', '.pt')])]
    if missing:
        raise RuntimeError(f'{cohort}: missing {len(missing)} patch caches: {missing[:5]}')
    report['feature_storage'] = 'Existing PT, else HDF5 features, else graph.x; never edges'
    report['survival_bins'] = 'Released baseline cohort-wide bins, matching historical BRCA baselines'
    report['validation_patches'] = 'All available patches, as in released baseline loaders'
    return report


def prepare_repo(model, cohort):
    repo = REPOS[model]
    actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != COMMITS[model]:
        raise RuntimeError(f'Unexpected {model} commit: {actual}')
    subprocess.run(['git', '-C', str(repo), 'diff', '--exit-code', '--', 'models',
                    'utils/loss_func.py'], check=True, capture_output=True)
    # This checkout is dedicated to this experiment; project source splits are read-only.
    target = repo / f'splits/5foldcv/tcga_{cohort}'
    target.mkdir(parents=True, exist_ok=True)
    for fold in range(5):
        shutil.copy2(ROOT / f'splits/5folds/tcga_{cohort}/splits_{fold}.csv', target / f'splits_{fold}.csv')
    clinical = repo / 'datasets_csv/clinical_data'
    clinical.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / f'datasets_csv/clinical_data/tcga_{cohort}_clinical.csv', clinical / f'tcga_{cohort}_clinical.csv')
    definitions = ['metadata/combine_signatures.csv', 'metadata/signatures.csv']
    if model == 'survpath':
        definitions.append('pathway_compositions/combine_comps.csv')
    for relative in definitions:
        source = ROOT / 'datasets_csv' / relative
        destination = repo / 'datasets_csv' / relative
        if destination.read_bytes() != source.read_bytes():
            raise RuntimeError(f'Pathway definitions differ: {destination}; do not silently substitute')
    sources = [*repo.glob('models/**/*.py'), repo / 'utils/loss_func.py',
               repo / 'utils/core_utils.py', repo / 'datasets/dataset_survival.py', repo / 'main.py']
    return dict(commit=actual, official_models_and_loss_unchanged=True,
                sha256={str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sources})


def baseline_command(model, cohort, fold, output, epochs=30):
    data = data_root(cohort)
    values = [sys.executable, '-u', 'main.py', '--study', f'tcga_{cohort}', '--task', 'survival',
              '--which_splits', '5foldcv', '--type_of_path', 'combine',
              '--data_root_dir', str(data if model == 'pibd' else data / 'pt_files'),
              '--label_file', str(ROOT / f'datasets_csv/metadata/tcga_{cohort}.csv'),
              '--omics_dir', str(ROOT / f'datasets_csv/raw_rna_data/combine/{cohort}'),
              '--results_dir', str(output), '--batch_size', '32' if model == 'pibd' else '1',
              '--lr', '0.0001', '--opt', 'adam', '--reg', '0.00001', '--seed', '1',
              '--alpha_surv', '0.0', '--max_epochs', str(epochs), '--encoding_dim', '1024',
              '--label_col', 'survival_months_dss', '--k', '5', '--k_start', str(fold),
              '--k_end', str(fold + 1), '--bag_loss', 'nll_surv', '--n_classes', '4',
              '--num_patches', '4096', '--wsi_projection_dim', '256']
    values += (['--mode', 'resnet50', '--omics_format', 'pathways'] if model == 'pibd' else
               ['--modality', 'survpath', '--fusion', 'concat'])
    return values


def completed(model, output, fold):
    matches = []
    for summary in (output / 'folds' / f'fold_{fold}' / 'training').glob('*/summary*.csv'):
        for row in rows(summary):
            if int(row.get('fold', row.get('folds', -1))) != fold:
                continue
            checkpoint = summary.parent / (f'model_best_s{fold}.pth' if model == 'pibd' else f's_{fold}_checkpoint.pt')
            predictions = summary.parent / f'split_{fold}_results.pkl'
            if not checkpoint.is_file() or not predictions.is_file():
                continue
            value = float(row['val_cindex'])
            if not math.isfinite(value):
                raise RuntimeError(f'Non-finite C-index in {summary}')
            matches.append(dict(fold=fold, val_cindex=value, source_summary=str(summary),
                                checkpoint=str(checkpoint), predictions=str(predictions)))
    if len(matches) > 1:
        raise RuntimeError(f'Ambiguous fold results: {output}, {fold}')
    return matches[0] if matches else None


def aggregate(model, output):
    records = [r for fold in range(5) if (r := completed(model, output, fold))]
    if records:
        target = output / 'fold_metrics.csv'
        temporary = target.with_suffix(f'.csv.{os.getpid()}.{time.time_ns()}.partial')
        with temporary.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
        temporary.replace(target)
    if len(records) == 5:
        values = [r['val_cindex'] for r in records]
        save_json(output / 'aggregate.json', dict(cindex_folds=values,
                  mean=statistics.mean(values), std_ddof0=statistics.pstdev(values),
                  std_ddof1=statistics.stdev(values), model=model,
                  split_audit=json.loads((output / 'split_audit.json').read_text())))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', choices=list(REPOS), default=list(REPOS))
    parser.add_argument('--cohorts', nargs='+', choices=['blca', 'hnsc', 'coadread', 'stad'], required=True)
    parser.add_argument('--results-root', type=Path, required=True)
    parser.add_argument('--queue-name', required=True)
    parser.add_argument('--gpus', nargs='+', required=True)
    parser.add_argument('--folds', nargs='+', type=int, default=list(range(5)))
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--reserve-manifest', type=Path)
    parser.add_argument('--reserve-raw', type=Path)
    parser.add_argument('--min-free-gib', type=float, default=70)
    parser.add_argument('--min-gpu-free-mib', type=int, default=18000)
    parser.add_argument('--allow-gpu-sharing', action='store_true',
                        help='Explicit permission to share with existing GPU processes; retain free-memory guard')
    parser.add_argument('--max-jobs-per-gpu', type=int, default=1)
    parser.add_argument('--shared-queue-status', nargs='*', default=[],
                        help='Count live jobs in these peer status files against the per-GPU limit')
    parser.add_argument('--leave-existing-training', action='store_true',
                        help='Supplement a live queue: never rename or relaunch existing incomplete training dirs')
    parser.add_argument('--gpu-poll-seconds', type=float, default=15)
    parser.add_argument('--reserved-until-unit', help='Do not use reserved GPUs until this prior queue exits')
    parser.add_argument('--reserved-gpus', nargs='*', default=[])
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--execute-one', nargs=3, metavar=('MODEL', 'COHORT', 'FOLD'))
    args = parser.parse_args()
    if any(f not in range(5) for f in args.folds) or args.epochs < 1:
        parser.error('Invalid folds or epochs')
    if bool(args.reserve_manifest) != bool(args.reserve_raw):
        parser.error('Supply both download reserve arguments')
    if args.min_gpu_free_mib < 1 or args.gpu_poll_seconds < 1:
        parser.error('GPU free-memory threshold and poll interval must be positive')
    if args.max_jobs_per_gpu < 1 or (args.max_jobs_per_gpu > 1 and not args.allow_gpu_sharing):
        parser.error('Multiple GPU jobs require --allow-gpu-sharing and a positive slot count')
    args.results_root = args.results_root.resolve()
    if args.execute_one:
        model, cohort, fold_text = args.execute_one
        if model not in REPOS or cohort not in args.cohorts or int(fold_text) not in range(5):
            parser.error('Invalid execute-one target')
        output = args.results_root / model / cohort / 'folds' / f'fold_{fold_text}' / 'training'
        output.parent.mkdir(parents=True, exist_ok=True)
        # Future workers launched by an already-running old controller read this
        # guard too. Keep the lock across exec; a second queue waits without CUDA
        # and rechecks validated completion before it can touch training outputs.
        claim = (output.parent / 'execution.lock').open('a')
        fcntl.flock(claim, fcntl.LOCK_EX)
        prior_record = completed(model, args.results_root / model / cohort, int(fold_text))
        if prior_record:
            validate_predictions(prior_record['predictions'], prior_record['val_cindex'],
                                 cohort, int(fold_text), ROOT)
            print(f'[already complete] {model}/{cohort}/{fold_text}', flush=True)
            claim.close()
            return
        os.set_inheritable(claim.fileno(), True)
        output.mkdir(parents=True, exist_ok=True)
        values = baseline_command(model, cohort, int(fold_text), output, args.epochs)
        env = dict(os.environ)
        env['PYTHONPATH'] = str(ROOT / 'scripts')
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['PYTHONWARNINGS'] = 'ignore'
        env['MREPATH_NUM_WORKERS'] = '0'
        save_json(output.parent / 'invocation.json', dict(command=values, cwd=str(REPOS[model]),
                  gpu=env.get('CUDA_VISIBLE_DEVICES'), at=time.time(), commit=COMMITS[model]))
        os.chdir(REPOS[model])
        os.execve(sys.executable, values, env)
    args.output = args.results_root / args.queue_name
    args.output.mkdir(parents=True, exist_ok=True)
    args.data = data_root(args.cohorts[0])
    lock = (args.output / 'queue.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    pending, destinations = [], {}
    for cohort in args.cohorts:
        report = validate_prepared(cohort)
        print(json.dumps(report), flush=True)
        for model in args.models:
            ensure_split_audit_matches(args.results_root / model / cohort, report)
            source_manifest = prepare_repo(model, cohort)
            output = args.results_root / model / cohort
            output.mkdir(parents=True, exist_ok=True)
            save_json(output / 'split_audit.json', report)
            save_json(output / 'source_manifest.json', source_manifest)
            for fold in args.folds:
                prior_record = completed(model, output, fold)
                if prior_record:
                    validate_predictions(prior_record['predictions'], prior_record['val_cindex'],
                                         cohort, fold, ROOT)
                    continue
                prior = output / 'folds' / f'fold_{fold}' / 'training'
                if prior.exists() and args.leave_existing_training:
                    print(f'[peer-owned output] {model}/{cohort}/{fold}', flush=True)
                    continue
                if prior.exists() and not args.prepare_only:
                    prior.rename(prior.with_name(f'training_interrupted_{time.time_ns()}'))
                label = f'{model}_{cohort}_{fold}'
                destinations[label] = (model, output, fold)
                pending.append((label, [sys.executable, '-u', str(Path(__file__).resolve()),
                    '--cohorts', cohort, '--models', model, '--results-root', str(args.results_root),
                    '--queue-name', args.queue_name, '--gpus', *args.gpus,
                    '--epochs', str(args.epochs), '--execute-one', model, cohort, str(fold)]))
            aggregate(model, output)
    save_json(args.output / 'run_manifest.json', dict(arguments={k: str(v) if isinstance(v, Path) else v
              for k, v in vars(args).items()}, jobs=pending,
              note='Official models/losses unchanged; same BRCA baseline CLI protocol; no AES/Bernoulli/KAN'))
    if args.prepare_only:
        lock.close()
        return
    def on_success(label):
        model, output, fold = destinations[label]
        record = completed(model, output, fold)
        if record is None:
            raise RuntimeError(f'Missing fold artifacts: {label}')
        report = validate_predictions(record['predictions'], record['val_cindex'],
                                      output.name, fold, ROOT)
        save_json(output / 'folds' / f'fold_{fold}' / 'prediction_audit.json', report)
        aggregate(model, output)
    try:
        gpu_queue(args, 'training', pending, args.gpus, on_success)
        save_json(args.output / 'pipeline_status.json', dict(state='completed', at=time.time()))
    except BaseException as exc:
        save_json(args.output / 'pipeline_status.json', dict(state='stopped', error=repr(exc), at=time.time()))
        raise
    finally:
        lock.close()


if __name__ == '__main__':
    main()
