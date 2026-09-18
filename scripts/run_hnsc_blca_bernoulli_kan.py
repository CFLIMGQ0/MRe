#!/usr/bin/env python3
"""Run the existing C4 encoder + external KAN on unchanged repository folds.

Orchestrates existing preprocessing/training code; does not alter model.yaml,
source SVS files, patient lists, model mathematics, or fold CSVs.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

from run_pc_cmka_word_ablations import command

ROOT = Path(__file__).resolve().parents[1]
GIB = 2**30


def rows(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream, delimiter="\t" if Path(path).suffix == ".tsv" else ","))


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.{time.time_ns()}.partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def ensure_split_audit_matches(output, report):
    """Refuse to reuse historical outputs after the source fold CSVs change."""
    previous = Path(output) / 'split_audit.json'
    if previous.is_file():
        old = json.loads(previous.read_text())
        old_hashes = {f['fold']: f.get('split_sha256') for f in old.get('folds', [])}
        new_hashes = {f['fold']: f.get('split_sha256') for f in report['folds']}
        if old_hashes != new_hashes:
            raise RuntimeError('Split protocol changed: use a NEW output directory; '
                               f'historical results preserved at {output}')


def audit(cohort, allow_overlap=False, data=None):
    metadata = rows(ROOT / f"datasets_csv/metadata/tcga_{cohort}.csv")
    rna = rows(ROOT / f"datasets_csv/raw_rna_data/combine/{cohort}/rna_clean.csv")
    rna_ids = {row[next(iter(row))] for row in rna}
    eligible = {row["case_id"] for row in metadata} & rna_ids
    validation = []
    used = set()
    folds = []
    for fold in range(5):
        path = ROOT / f"splits/5folds/tcga_{cohort}/splits_{fold}.csv"
        split = rows(path)
        train = {row["train"] for row in split if row["train"]} & eligible
        val = {row["val"] for row in split if row["val"]} & eligible
        overlap = sorted(train & val)
        if not train or not val:
            raise RuntimeError(f"Empty eligible split in fold {fold}")
        if overlap and not allow_overlap:
            raise RuntimeError(f"Fold {fold}: {len(overlap)} overlapping patients")
        validation.extend(val)
        used.update(train | val)
        folds.append(dict(fold=fold, train=len(train), val=len(val),
                          overlapping_patients=overlap,
                          split_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    invalid = [row["case_id"] for row in metadata if row["case_id"] in eligible
               and (not row["survival_months_dss"] or not row["censorship_dss"])]
    if invalid:
        raise RuntimeError(f"Missing DSS labels: {sorted(set(invalid))}")
    required_slides = sorted({Path(row["slide_id"]).stem for row in metadata
                              if row["case_id"] in used})
    if data is not None:
        missing = [name for name in required_slides
                   if not (data / "graph_files" / f"{name}.pt").is_file()
                   or not (data / "hypergraph_cache" / f"{name}.pt").is_file()]
        if missing:
            raise RuntimeError(f"{len(missing)} required graphs/caches missing: {missing[:5]}")
    return dict(cohort=cohort, eligible_metadata_rna_patients=len(eligible),
                patients_used_by_repository_splits=len(used),
                required_slides=len(required_slides), folds=folds,
                validation_entries=len(validation), unique_validation=len(set(validation)),
                overlap_explicitly_accepted=allow_overlap,
                interpretation=f"repository-split reproduction; {cohort.upper()} has patient leakage"
                if any(f["overlapping_patients"] for f in folds)
                else "patient-disjoint repository folds")


def remaining_download_bytes(manifest, raw_root):
    if manifest is None:
        return 0
    remaining = 0
    for row in rows(manifest):
        path = raw_root / row["id"] / row["filename"]
        # gdc-client writes directly to the final filename while downloading.
        present = path.stat().st_size if path.is_file() else 0
        remaining += max(0, int(row["size"]) - present)
    return remaining


def reusable_inventory(source, data):
    """Reuse completed slide geometry if file identity/size and mode agree."""
    path = data / "wsi_inventory.csv"
    if not path.is_file():
        return False
    inventory = rows(path)
    actual = {str(p.resolve()): p.stat().st_size for p in source.rglob("*.svs")}
    if not actual or len(inventory) != len(actual):
        return False
    if len({row.get("path") for row in inventory}) != len(actual):
        return False
    return all(not row.get("inventory_error") and row.get("patch_mode") == "true-20x"
               and row.get("path") in actual
               and str(actual[row["path"]]) == row.get("size_bytes") for row in inventory)


def assert_output_mount(output, mount=None):
    """Never fall back to the local mountpoint when external storage is absent."""
    if mount is None:
        return
    mount = Path(mount).resolve()
    if not os.path.ismount(mount) or not Path(output).resolve().is_relative_to(mount):
        raise RuntimeError(f'Required result storage is not mounted or output is outside it: {mount}')


def space_check(args):
    assert_output_mount(args.output, getattr(args, 'storage_mount', None))
    remaining = remaining_download_bytes(args.reserve_manifest, args.reserve_raw)
    remaining += getattr(args, 'reserve_gib', 0) * GIB
    free = shutil.disk_usage(args.output).free
    if free - remaining < args.min_free_gib * GIB:
        raise RuntimeError(
            f"Disk guard: free={free/GIB:.1f} GiB, reserved download={remaining/GIB:.1f} "
            f"GiB; need {args.min_free_gib} GiB unreserved. Outputs preserved.")


def child_environment(args, extra=None):
    env = dict(os.environ, **(extra or {}))
    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(key, None)
    env.update(NO_PROXY="*", no_proxy="*", OMP_NUM_THREADS="4", MKL_NUM_THREADS="4",
               OPENBLAS_NUM_THREADS="4", NUMEXPR_NUM_THREADS="4", PYTHONHASHSEED="1",
               TORCH_HOME=str(args.data / "torch_cache"),
               LD_LIBRARY_PATH=str(Path(sys.base_prefix) / "lib") + ":" + env.get("LD_LIBRARY_PATH", ""),
               MPLCONFIGDIR=str(args.output / "matplotlib_cache"))
    return env


def terminate_children(children):
    for child in children:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for child in children:
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def idle_gpus(candidates, min_free_mib, allow_sharing=False):
    """Admit idle GPUs by default; sharing requires an explicit opt-in.

    Shared admission still requires the same free-memory budget. This function
    never stops existing processes and makes no guarantee about later allocations.
    """
    gpu_text = subprocess.check_output([
        "nvidia-smi", "--query-gpu=index,uuid,memory.free,memory.used",
        "--format=csv,noheader,nounits"], text=True, timeout=15)
    app_text = subprocess.check_output([
        "nvidia-smi", "--query-compute-apps=gpu_uuid,pid",
        "--format=csv,noheader,nounits"], text=True, timeout=15)
    busy = {row[0].strip() for row in csv.reader(app_text.splitlines()) if len(row) >= 2}
    idle = set()
    for row in csv.reader(gpu_text.splitlines()):
        index, uuid, free, used = [value.strip() for value in row]
        exclusive = uuid not in busy and float(used) <= 1024
        if float(free) >= min_free_mib and (allow_sharing or exclusive):
            idle.add(index)
    return [gpu for gpu in candidates if gpu in idle]


def external_gpu_jobs(status_paths):
    """Count live jobs owned by explicitly named peer queues, never unrelated users.

    A dead/reused PID does not reserve a slot: check its project working directory
    and that its process start predates the status snapshot. Missing status fails
    closed, because it cannot establish that the peer has released its GPUs.
    """
    counts = {}
    seen = set()
    boot = next(float(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines()
                if line.startswith('btime '))
    hz = os.sysconf('SC_CLK_TCK')
    for path in status_paths:
        state = json.loads(Path(path).read_text())
        for job in state.get('active', []):
            pid = int(job['pid'])
            if pid in seen:
                continue
            try:
                proc = Path('/proc') / str(pid)
                fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
                if fields[0] == 'Z' or boot + int(fields[19]) / hz > state['at'] + 1:
                    continue
                (proc / 'cwd').resolve(strict=True).relative_to(ROOT)
            except (FileNotFoundError, ProcessLookupError, ValueError):
                continue
            seen.add(pid)
            gpu = str(job['gpu'])
            counts[gpu] = counts.get(gpu, 0) + 1
    return counts


def gpu_queue(args, name, jobs, candidates, on_success=None):
    """Refill admitted GPU slots, counting explicitly configured peer queues.

    Independent output directories are mandatory for training jobs. Two clean
    admission polls avoid treating a just-exited process as released too early.
    Resource queries failing are fatal (fail closed), not permission to use GPUs.
    """
    pending = list(jobs)
    active = {}
    idle_counts = dict.fromkeys(candidates, 0)
    completed, failed = [], {}
    events = args.output / "gpu_dispatch.jsonl"
    allow_sharing = bool(getattr(args, "allow_gpu_sharing", False))
    max_jobs = getattr(args, 'max_jobs_per_gpu', 1)
    peer_paths = getattr(args, 'shared_queue_status', [])
    if max_jobs < 1 or (max_jobs > 1 and not allow_sharing):
        raise ValueError('Multiple GPU slots require explicit sharing permission')

    def admitted_gpus(pool):
        if allow_sharing:
            return idle_gpus(pool, args.min_gpu_free_mib, allow_sharing=True)
        return idle_gpus(pool, args.min_gpu_free_mib)

    def event(kind, **values):
        with events.open("a") as handle:
            handle.write(json.dumps(dict(at=time.time(), stage=name, event=kind, **values)) + "\n")

    def update():
        save_json(args.output / "pipeline_status.json", dict(
            stage=name, state="running", at=time.time(), gpu_candidates=candidates,
            allow_gpu_sharing=allow_sharing, min_gpu_free_mib=args.min_gpu_free_mib,
            max_jobs_per_gpu=max_jobs, shared_queue_status=[str(p) for p in peer_paths],
            pending=[label for label, _ in pending], completed=completed, failed=failed,
            active=[dict(gpu=key[0], slot=key[1], job=job[0], pid=job[1].pid)
                    for key, job in active.items()]))

    try:
        while pending or active:
            space_check(args)
            for key, (label, child, handle) in list(active.items()):
                gpu = key[0]
                code = child.poll()
                if code is None:
                    continue
                handle.close()
                del active[key]
                idle_counts[gpu] = 0
                error = None if code == 0 else f"exit code {code}"
                if error is None and on_success:
                    try:
                        on_success(label)
                    except Exception as exc:
                        error = repr(exc)
                if error:
                    failed[label] = error
                    event("failed", job=label, gpu=gpu, error=error)
                else:
                    completed.append(label)
                    event("completed", job=label, gpu=gpu)
            if pending:
                admitted_candidates = candidates
                reserved_unit = getattr(args, "reserved_until_unit", None)
                if reserved_unit:
                    check = subprocess.run(["systemctl", "--user", "show", reserved_unit,
                                            "--property=ActiveState", "--value"],
                                           capture_output=True, text=True, timeout=15, check=True)
                    state = check.stdout.strip()
                    if state not in {"inactive", "failed"}:
                        admitted_candidates = [g for g in candidates
                                               if g not in getattr(args, "reserved_gpus", [])]
                idle = set(admitted_gpus(admitted_candidates))
                peers = external_gpu_jobs(peer_paths) if peer_paths else {}
                for gpu in candidates:
                    owned = sum(key[0] == gpu for key in active)
                    available = owned + peers.get(gpu, 0) < max_jobs
                    idle_counts[gpu] = idle_counts[gpu] + 1 if gpu in idle and available else 0
                    if not pending or idle_counts[gpu] < 2:
                        continue
                    # Recheck just before launch. No claim can prevent unrelated
                    # tools starting later; only this queue's jobs are controlled.
                    if gpu not in admitted_gpus([gpu]):
                        idle_counts[gpu] = 0
                        continue
                    peers_now = external_gpu_jobs(peer_paths) if peer_paths else {}
                    if owned + peers_now.get(gpu, 0) >= max_jobs:
                        idle_counts[gpu] = 0
                        continue
                    label, values = pending.pop(0)
                    log = args.output / f"{name}_{label}_gpu{gpu}_{time.time_ns()}.log"
                    handle = log.open("w")
                    try:
                        child = subprocess.Popen(values, cwd=ROOT,
                            env=child_environment(args, {"CUDA_VISIBLE_DEVICES": gpu}),
                            stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
                    except BaseException:
                        handle.close()
                        raise
                    slot = next(i for i in range(max_jobs) if (gpu, i) not in active)
                    active[(gpu, slot)] = (label, child, handle)
                    idle_counts[gpu] = 0
                    event("started", job=label, gpu=gpu, pid=child.pid, command=values, log=str(log),
                          allow_gpu_sharing=allow_sharing, min_gpu_free_mib=args.min_gpu_free_mib)
                    print(f"[{name}] {label} -> GPU {gpu}: {shlex.join(values)}", flush=True)
            update()
            if pending or active:
                time.sleep(args.gpu_poll_seconds)
        if failed:
            raise RuntimeError(f"{name}: {failed}; other completed jobs preserved")
    finally:
        terminate_children([job[1] for job in active.values()])
        for _, _, handle in active.values():
            handle.close()


def stage(args, name, jobs):
    """Run child process groups, terminating only our groups if a guard fails."""
    space_check(args)
    save_json(args.output / "pipeline_status.json", dict(stage=name, state="running", at=time.time()))
    running = []
    handles = []
    try:
        for index, (values, extra_env) in enumerate(jobs):
            env = child_environment(args, extra_env)
            print(f"[{name}/{index}] {shlex.join(values)}", flush=True)
            handle = (args.output / f"{name}_{index}_{time.time_ns()}.log").open("w")
            handles.append(handle)
            running.append(subprocess.Popen(values, cwd=ROOT, env=env, stdout=handle,
                                             stderr=subprocess.STDOUT, start_new_session=True))
        while True:
            space_check(args)
            codes = [child.poll() for child in running]
            if any(code is not None and code != 0 for code in codes):
                raise RuntimeError(f"Stage {name} failed: exit codes {codes}; see stage logs")
            if all(code == 0 for code in codes):
                break
            time.sleep(15)
    finally:
        terminate_children(running)
        for handle in handles:
            handle.close()


def train_command(args, fold):
    dataset = dict(study=f"tcga_{args.cohort}", data=args.data,
                   labels=ROOT / f"datasets_csv/metadata/tcga_{args.cohort}.csv",
                   omics=ROOT / f"datasets_csv/raw_rna_data/combine/{args.cohort}")
    original = getattr(args, "original_model", False)
    experiment = ({"name": "paper_original", "encoder": "original"} if original else
                  {"name": "C4_bernoulli_views", "encoder": "pc_cmka_ddkac"})
    values = command(dataset, ROOT / "configs/pc_cmka_ddkac_word.json",
                     experiment, fold,
                     SimpleNamespace(num_workers=4, max_epochs=30, num_patches=4096),
                     args.output / "folds" / f"fold_{fold}" / "training")
    values[0] = sys.executable
    if not original:
        values[values.index("--mrepath_gene_aggregation") + 1] = "kan"
    return values


def completed_fold(output, fold):
    paths = list((output / "folds" / f"fold_{fold}" / "training").glob("*/summary.csv"))
    # Read-only compatibility with the earlier sequential launcher.
    paths += list((output / "training").glob("*/summary.csv"))
    matches = []
    for path in paths:
        for row in rows(path):
            if int(row["fold"]) != fold:
                continue
            if not (path.parent / f"split_{fold}_results.pkl").is_file():
                continue
            if not (path.parent / f"s_{fold}_best_checkpoint.pt").is_file():
                continue
            if not math.isfinite(float(row["val_cindex"])):
                raise RuntimeError(f"Invalid C-index in {path}")
            matches.append(dict(row, source_summary=str(path)))
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous complete outputs for fold {fold}; do not silently pick one")
    return matches[0] if matches else None


def merge_fold_metrics(output):
    metrics = [row for fold in range(5) if (row := completed_fold(output, fold))]
    if metrics:
        destination = output / "fold_metrics.csv"
        temporary = destination.with_suffix(".csv.partial")
        with temporary.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(metrics[0]))
            writer.writeheader()
            writer.writerows(metrics)
        temporary.replace(destination)
    return metrics


def record_completed_job(output, label):
    fold = int(label.removeprefix("fold_"))
    if completed_fold(output, fold) is None:
        raise RuntimeError(f"Fold {fold} exited without complete metrics/predictions/checkpoint")
    merge_fold_metrics(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=["hnsc", "blca"], required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gpus", nargs="+", default=["0", "1"])
    parser.add_argument("--train-gpus", nargs="+", help="Idle GPU pool for independent folds; defaults to --gpus")
    parser.add_argument("--feature-workers", type=int, default=8)
    parser.add_argument("--gpu-poll-seconds", type=float, default=15)
    parser.add_argument("--min-gpu-free-mib", type=int, default=18000)
    parser.add_argument("--allow-gpu-sharing", action="store_true",
                        help="Explicit permission to coexist with existing GPU processes; free-memory guard remains")
    parser.add_argument("--allow-repository-overlap", action="store_true")
    parser.add_argument("--reserve-manifest", type=Path)
    parser.add_argument("--reserve-raw", type=Path)
    parser.add_argument("--min-free-gib", type=float, default=70)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--preprocess-only", action="store_true")
    parser.add_argument("--train-only", action="store_true")
    parser.add_argument("--original-model", action="store_true",
                        help="Original MRePath: original genomic encoder and default aggregation; no C4/KAN/AES")
    parser.add_argument("--refresh-inventory", action="store_true")
    args = parser.parse_args()
    if bool(args.reserve_manifest) != bool(args.reserve_raw):
        parser.error("reserve-manifest and reserve-raw must be supplied together")
    if args.preprocess_only and args.train_only:
        parser.error("preprocess-only and train-only are mutually exclusive")
    args.train_gpus = args.train_gpus or args.gpus
    if any(len(pool) != len(set(pool)) or any(not gpu.isdigit() for gpu in pool)
           for pool in (args.gpus, args.train_gpus)):
        parser.error("GPU pools must contain unique numeric GPU indices")
    if args.feature_workers < 1 or args.gpu_poll_seconds < 1:
        parser.error("feature-workers and gpu-poll-seconds must be positive")
    if args.min_gpu_free_mib < 1:
        parser.error("min-gpu-free-mib must be positive")
    args.data = args.data.resolve()
    args.output = args.output.resolve()
    report = audit(args.cohort, args.allow_repository_overlap)
    ensure_split_audit_matches(args.output, report)
    args.output.mkdir(parents=True, exist_ok=True)
    args.data.mkdir(parents=True, exist_ok=True)
    # Prevent two revised launchers owning the same cohort outputs.
    lock = (args.output / "pipeline.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for filename in ("run_manifest.json", "split_audit.json", "pipeline_status.json"):
        previous = args.output / filename
        if previous.exists():
            shutil.copy2(previous, args.output / f"{previous.stem}_previous_{time.time_ns()}.json")
    save_json(args.output / "split_audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    commands = [train_command(args, fold) for fold in range(5)]
    save_json(args.output / "run_manifest.json", dict(
        arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        training_commands=commands, model=("MRePath paper original" if args.original_model else
                                          "C4_bernoulli_views + external KAN"),
        notes="Original dynamic weighting + IFA, no Quality + Conflict, no BK_Ixx.",
        config_sha256=hashlib.sha256((ROOT / "configs/pc_cmka_ddkac_word.json").read_bytes()).hexdigest()))
    if args.audit_only:
        return
    with (args.output / f"environment_{time.time_ns()}.txt").open("w") as stream:
        subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=stream, check=True)
    try:
        base = [sys.executable, "-u", "scripts/preprocess_wsi_clam.py", "--source", str(args.source),
                "--output", str(args.data), "--patch-mode", "true-20x"]
        if not args.train_only:
            if not args.refresh_inventory and reusable_inventory(args.source, args.data):
                print("[resume] reuse complete inventory: slide paths, sizes and patch mode unchanged", flush=True)
            else:
                stage(args, "inventory", [(base + ["--inventory-only"], {"CUDA_VISIBLE_DEVICES": ""})])
            gpu_queue(args, "features", [(f"shard_{index}", base + ["--stages", "segment,features", "--skip-inventory",
              "--num-shards", str(len(args.gpus)), "--shard-index", str(index), "--status-file",
              f"preprocess_status_{len(args.gpus)}shards_w{args.feature_workers}_{index}.csv",
              "--batch-size", "256", "--workers", str(args.feature_workers),
              "--device", "cuda", "--fail-fast"])
              for index in range(len(args.gpus))], args.gpus)
            stage(args, "graphs", [([sys.executable, "-u", "scripts/build_wsi_graphs.py", "--h5-dir",
              str(args.data / "h5_files"), "--output-dir", str(args.data / "graph_files"),
              "--metadata-csv", str(ROOT / f"datasets_csv/metadata/tcga_{args.cohort}.csv"),
              "--radius", "9", "--feature-dim", "1024", "--spatial-space", "l2",
              "--feature-space", "cosinesimil", "--verify-existing", "--fail-fast"],
              {"CUDA_VISIBLE_DEVICES": ""})])
            stage(args, "hypergraphs", [([sys.executable, "-u", "scripts/build_hypergraph_cache.py",
              "--graph-dir", str(args.data / "graph_files"), "--cache-dir",
              str(args.data / "hypergraph_cache"), "--workers", "4"],
              {"CUDA_VISIBLE_DEVICES": ""})])
        save_json(args.output / "ready_audit.json", audit(args.cohort, args.allow_repository_overlap, args.data))
        if args.preprocess_only:
            save_json(args.output / "pipeline_status.json", dict(stage="preprocessed", state="completed", at=time.time()))
            return
        pending = []
        for fold, values in enumerate(commands):
            if completed_fold(args.output, fold):
                print(f"[resume] fold {fold} already complete", flush=True)
            else:
                old = args.output / "folds" / f"fold_{fold}" / "training"
                if old.exists():
                    old.rename(old.with_name(f"training_interrupted_{time.time_ns()}"))
                pending.append((f"fold_{fold}", values))
        merge_fold_metrics(args.output)
        gpu_queue(args, "training", pending, args.train_gpus,
                  lambda label: record_completed_job(args.output, label))
        records = merge_fold_metrics(args.output)
        if len(records) != 5:
            raise RuntimeError("Missing unique, complete five-fold metrics")
        import statistics
        metrics = [float(row["val_cindex"]) for row in records]
        save_json(args.output / "aggregate.json", dict(cindex_folds=metrics,
                  mean=statistics.mean(metrics), std_ddof0=statistics.pstdev(metrics),
                  std_ddof1=statistics.stdev(metrics), split_audit=report,
                  summary=str(args.output / "fold_metrics.csv")))
        save_json(args.output / "pipeline_status.json", dict(stage="complete", state="completed", at=time.time()))
    except BaseException as exc:
        save_json(args.output / "pipeline_status.json", dict(state="stopped", error=repr(exc), at=time.time()))
        raise


if __name__ == "__main__":
    main()
