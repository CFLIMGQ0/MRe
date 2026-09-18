#!/usr/bin/env python3
"""Dynamically dispatch requested model/cohort tasks across host204 + host202."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/new_data/Lim/MRePath_experiments/Project1")
SSH = [
    "ssh", "-i", "/home/Lim/.ssh/id_ed25519_project4_pool",
    "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
    "Lim@172.16.170.202",
]
COHORTS = ("blca", "brca", "coadread", "stad", "hnsc")
MODELS = ("ld_cvae", "dimaf", "slotspe")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--local-results", type=Path, required=True)
    parser.add_argument("--remote-results", type=Path, required=True)
    parser.add_argument("--min-free-mib", type=int, default=18000)
    parser.add_argument("--min-disk-free-gib", type=float, default=60.0)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--max-attempts", type=int, default=12)
    parser.add_argument("--retry-base-seconds", type=int, default=60)
    parser.add_argument("--retry-max-seconds", type=int, default=21600)
    return parser.parse_args()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def task_plan():
    tasks = [
        dict(label="m3_blca", kind="m3", cohort="blca", hosts=["204"]),
        dict(label="m3_hnsc", kind="m3", cohort="hnsc", hosts=["202"]),
    ]
    # Start GPU-compatible models first while DIMAF's per-fold CPU prototype
    # stage remains later in the queue.
    for model in ("slotspe", "ld_cvae", "dimaf"):
        for cohort in COHORTS:
            hosts = ["204", "202"] if cohort in {"blca", "brca", "hnsc"} else ["204"]
            tasks.append(dict(label=f"{model}_{cohort}", kind="external", model=model,
                              cohort=cohort, hosts=hosts))
    for cohort in COHORTS:
        tasks.append(dict(label=f"aes_{cohort}", kind="aes", cohort=cohort,
                          hosts=["202"] if cohort == "hnsc" else ["204"]))
    return tasks


def host_root(host):
    return ROOT if host == "204" else REMOTE_ROOT


def result_root(host, args):
    return args.local_results if host == "204" else args.remote_results


def task_output(task, host, args):
    root = result_root(host, args)
    if task["kind"] == "external":
        return root / "external" / task["model"] / task["cohort"]
    return root / task["kind"] / task["cohort"]


def aes_cache(task, host):
    if task["kind"] != "aes":
        return None
    if host == "202":
        return Path("/home/Lim/MRePath_aes_cache_20260916") / f"{task['cohort']}_p0.8_T0.001"
    return ROOT / f"data/tcga_{task['cohort']}/clam_20x_resnet50_paper_k9/hypergraph_cache_aes_p0.8_T0.001"


def remote_capture(command):
    return subprocess.check_output(SSH + [command], text=True, timeout=20)


def exists(path: Path, host: str):
    if host == "204":
        return path.is_file()
    result = subprocess.run(SSH + [f"test -f {shlex.quote(str(path))}"], timeout=20)
    return result.returncode == 0


def task_complete(task, args):
    for host in task["hosts"]:
        if exists(task_output(task, host, args) / "complete.json", host):
            return host
    return None


def _local_task_processes():
    """Find wrapper processes, including CPU-only phases invisible to nvidia-smi."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = [part.decode(errors="replace") for part in
                    (entry / "cmdline").read_bytes().split(b"\0") if part]
            if not any(value.endswith("run_requested_model_task.py") for value in argv):
                continue
            if "--output" not in argv or "requested_full_20260916" not in argv[argv.index("--output") + 1]:
                continue
            environment = {}
            for value in (entry / "environ").read_bytes().split(b"\0"):
                if b"=" in value:
                    key, item = value.split(b"=", 1)
                    environment[key.decode(errors="replace")] = item.decode(errors="replace")
            gpu = environment.get("CUDA_VISIBLE_DEVICES")
            if gpu is None or "," in gpu:
                continue
            kind = argv[argv.index("--kind") + 1]
            cohort = argv[argv.index("--cohort") + 1]
            model = argv[argv.index("--model") + 1] if "--model" in argv else None
            label = f"{model}_{cohort}" if kind == "external" else f"{kind}_{cohort}"
            found.append(dict(pid=int(entry.name), gpu=gpu, label=label,
                              cmdline=" ".join(argv)[:1000]))
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            continue
    return found


def task_processes(host):
    if host == "204":
        return _local_task_processes()
    code = r'''
import json
from pathlib import Path
out = []
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        argv = [x.decode(errors='replace') for x in (entry/'cmdline').read_bytes().split(b'\0') if x]
        if not any(x.endswith('run_requested_model_task.py') for x in argv):
            continue
        if '--output' not in argv or 'requested_full_20260916' not in argv[argv.index('--output') + 1]:
            continue
        env = {}
        for value in (entry/'environ').read_bytes().split(b'\0'):
            if b'=' in value:
                key, item = value.split(b'=', 1)
                env[key.decode(errors='replace')] = item.decode(errors='replace')
        gpu = env.get('CUDA_VISIBLE_DEVICES')
        if gpu is None or ',' in gpu:
            continue
        kind = argv[argv.index('--kind') + 1]
        cohort = argv[argv.index('--cohort') + 1]
        model = argv[argv.index('--model') + 1] if '--model' in argv else None
        label = f'{model}_{cohort}' if kind == 'external' else f'{kind}_{cohort}'
        out.append(dict(pid=int(entry.name), gpu=gpu, label=label, cmdline=' '.join(argv)[:1000]))
    except (FileNotFoundError, PermissionError, ValueError, IndexError):
        pass
print(json.dumps(out))
'''
    return json.loads(remote_capture("python3 -c " + shlex.quote(code)))


def task_ready(task, host):
    if task["kind"] != "aes":
        return True
    return exists(aes_cache(task, host) / "complete.json", host)


def gpu_rows(host, observed_tasks=()):
    command = "nvidia-smi --query-gpu=index,uuid,memory.free,memory.used --format=csv,noheader,nounits"
    text = subprocess.check_output(command.split(), text=True, timeout=20) if host == "204" else remote_capture(command)
    rows = {}
    for row in csv.reader(text.splitlines()):
        if len(row) >= 4:
            index, uuid, free, used = (item.strip() for item in row[:4])
            rows[index] = dict(uuid=uuid, free=int(free), used=int(used), own_processes=[])
    app_command = "nvidia-smi --query-compute-apps=gpu_uuid,pid --format=csv,noheader,nounits"
    apps = subprocess.check_output(app_command.split(), text=True, timeout=20) if host == "204" else remote_capture(app_command)
    uuid_to_index = {value["uuid"]: index for index, value in rows.items()}
    for row in csv.reader(apps.splitlines()):
        if len(row) < 2 or row[0].strip() not in uuid_to_index:
            continue
        uuid, pid = row[0].strip(), row[1].strip()
        try:
            if host == "204":
                cmdline = (Path("/proc") / pid / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            else:
                cmdline = remote_capture(f"tr '\\0' ' ' < /proc/{pid}/cmdline")
        except Exception:
            continue
        if ("requested_full_20260916" in cmdline
                or "run_resnet50_repository_model.py" in cmdline
                or "BK_I03_mask2spline_hyperkan" in cmdline):
            rows[uuid_to_index[uuid]]["own_processes"].append(dict(pid=int(pid), cmdline=cmdline[:500]))
    for process in observed_tasks:
        if process["gpu"] in rows and not any(
                item["pid"] == process["pid"] for item in rows[process["gpu"]]["own_processes"]):
            rows[process["gpu"]]["own_processes"].append(process)
    return rows


def disk_free_gib(host, path):
    if host == "204":
        return shutil.disk_usage(path).free / 2**30
    value = remote_capture(f"df --output=avail -B1 {shlex.quote(str(path))} | tail -1").strip()
    return int(value) / 2**30


def task_command(task, host, args):
    root = host_root(host)
    python = root / ".venvs/repository_baselines_20260913/bin/python"
    values = [str(python), "-u", str(root / "scripts/run_requested_model_task.py"),
              "--kind", task["kind"], "--cohort", task["cohort"],
              "--output", str(task_output(task, host, args)), "--epochs", "30",
              "--num-workers", "2"]
    if task["kind"] == "external":
        values += ["--model", task["model"]]
    if task["kind"] == "aes":
        values += ["--aes-cache", str(aes_cache(task, host))]
    return values


def launch(task, host, gpu, args):
    command = task_command(task, host, args)
    output = task_output(task, host, args)
    if host == "204":
        output.mkdir(parents=True, exist_ok=True)
    else:
        remote_capture(f"mkdir -p {shlex.quote(str(output))}")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu, OMP_NUM_THREADS="4", MKL_NUM_THREADS="4",
               OPENBLAS_NUM_THREADS="4", PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="1")
    if host == "204":
        env["LD_LIBRARY_PATH"] = "/xmlg/Lim/conda/envs/myenv/lib:" + env.get("LD_LIBRARY_PATH", "")
        log_path = output / "controller_task.log"
        handle = log_path.open("a")
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    else:
        log_path = output / "controller_task.log"
        exports = (
            f"CUDA_VISIBLE_DEVICES={shlex.quote(gpu)} OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 "
            "OPENBLAS_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1 "
            "LD_LIBRARY_PATH=/home/Lim/conda/envs/myenv/lib"
        )
        shell = (f"cd {shlex.quote(str(REMOTE_ROOT))} && {exports} {shlex.join(command)} "
                 f">> {shlex.quote(str(log_path))} 2>&1")
        handle = None
        child = subprocess.Popen(SSH + [shell], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
    return child, handle, command, str(log_path)


def main():
    args = parse_args()
    args.state_dir = args.state_dir.resolve()
    args.local_results = args.local_results.resolve()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    args.local_results.mkdir(parents=True, exist_ok=True)
    remote_capture(f"mkdir -p {shlex.quote(str(args.remote_results))}")
    lock = (args.state_dir / "scheduler.lock").open("a")
    import fcntl
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    tasks = task_plan()
    active = {}
    completed, terminal_failed = {}, {}
    events = args.state_dir / "events.jsonl"
    retry_path = args.state_dir / "retry_state.json"
    try:
        retry_state = json.loads(retry_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        retry_state = {}
    terminal_failed.update({label: value for label, value in retry_state.items()
                            if int(value.get("attempts", 0)) >= args.max_attempts})

    def event(kind, **values):
        with events.open("a") as handle:
            handle.write(json.dumps(dict(at=time.time(), event=kind, **values)) + "\n")

    def save_retries():
        atomic_json(retry_path, retry_state)

    def record_failure(task, host, gpu, exit_code, log, reason=None):
        label = task["label"]
        previous = retry_state.get(label, {})
        attempts = int(previous.get("attempts", 0)) + 1
        delay = min(args.retry_base_seconds * (2 ** max(0, attempts - 1)),
                    args.retry_max_seconds)
        value = dict(attempts=attempts, last_failure_at=time.time(), retry_after=time.time() + delay,
                     host=host, gpu=gpu, exit_code=exit_code, log=log, reason=reason)
        retry_state[label] = value
        save_retries()
        event("attempt_failed", job=label, **value)
        if attempts >= args.max_attempts:
            terminal_failed[label] = value
            event("terminal_failure", job=label, **value)

    try:
        while True:
            for key, value in list(active.items()):
                code = value["process"].poll()
                if code is None:
                    continue
                if value["handle"] is not None:
                    value["handle"].close()
                del active[key]
                task = value["task"]
                complete_host = task_complete(task, args) if code == 0 else None
                if code == 0 and complete_host:
                    completed[task["label"]] = complete_host
                    retry_state.pop(task["label"], None)
                    save_retries()
                    event("completed", job=task["label"], host=complete_host, gpu=key[1])
                else:
                    record_failure(task, key[0], key[1], code, value["log"])

            for task in tasks:
                try:
                    found = task_complete(task, args)
                except Exception as exc:
                    event("completion_query_failed", job=task["label"], error=repr(exc))
                    continue
                if found:
                    completed.setdefault(task["label"], found)
                    if task["label"] in retry_state:
                        retry_state.pop(task["label"], None)
                        save_retries()

            observed_by_host = {}
            for host in ("204", "202"):
                try:
                    observed_by_host[host] = task_processes(host)
                except Exception as exc:
                    observed_by_host[host] = []
                    event("process_query_failed", host=host, error=repr(exc))
            managed_pids = {value["process"].pid for value in active.values()}
            managed_labels = {value["task"]["label"] for value in active.values()}
            observed = [dict(item, host=host) for host, values in observed_by_host.items()
                        for item in values if item["label"] not in managed_labels
                        and not (host == "204" and item["pid"] in managed_pids)]
            running_labels = {value["task"]["label"] for value in active.values()}
            running_labels.update(item["label"] for item in observed)

            now = time.time()
            unfinished = [task for task in tasks if task["label"] not in completed
                          and task["label"] not in terminal_failed
                          and task["label"] not in running_labels]
            pending = [task for task in unfinished
                       if float(retry_state.get(task["label"], {}).get("retry_after", 0)) <= now]
            retry_wait = [task for task in unfinished if task not in pending]
            if not pending and not active and not retry_wait and not observed:
                break

            for host in ("204", "202"):
                try:
                    gpus = gpu_rows(host, observed_by_host[host])
                    free_disk = disk_free_gib(host, result_root(host, args))
                except Exception as exc:
                    event("host_query_failed", host=host, error=repr(exc))
                    continue
                if free_disk < args.min_disk_free_gib:
                    event("disk_guard", host=host, free_gib=free_disk)
                    continue
                for gpu, memory in sorted(gpus.items(), key=lambda pair: int(pair[0])):
                    key = (host, gpu)
                    if key in active or memory["own_processes"] or memory["free"] < args.min_free_mib:
                        continue
                    task = None
                    for item in pending:
                        if host not in item["hosts"]:
                            continue
                        try:
                            ready = task_ready(item, host)
                        except Exception as exc:
                            event("readiness_query_failed", job=item["label"], host=host, error=repr(exc))
                            continue
                        if ready:
                            task = item
                            break
                    if task is None:
                        continue
                    try:
                        child, handle, command, log = launch(task, host, gpu, args)
                    except Exception as exc:
                        record_failure(task, host, gpu, -1, None, reason=repr(exc))
                        pending.remove(task)
                        continue
                    active[key] = dict(task=task, process=child, handle=handle, command=command, log=log)
                    pending.remove(task)
                    event("started", job=task["label"], host=host, gpu=gpu, pid=child.pid,
                          command=command, log=log, free_mib=memory["free"])

            state = dict(
                state="running" if active or pending or retry_wait or observed else "completed", at=time.time(),
                min_free_mib=args.min_free_mib, min_disk_free_gib=args.min_disk_free_gib,
                max_own_tasks_per_gpu=1, max_attempts=args.max_attempts,
                planned=len(tasks), completed=completed, failed=terminal_failed,
                pending=[task["label"] for task in pending],
                retry_wait={task["label"]: retry_state[task["label"]] for task in retry_wait},
                active=[dict(host=host, gpu=gpu, job=value["task"]["label"],
                             pid=value["process"].pid, log=value["log"])
                        for (host, gpu), value in active.items()],
                observed=observed,
            )
            atomic_json(args.state_dir / "pipeline_status.json", state)
            time.sleep(args.poll_seconds)
        final_state = "completed" if not terminal_failed else "completed_with_failures"
        atomic_json(args.state_dir / "pipeline_status.json", dict(
            state=final_state, at=time.time(), planned=len(tasks), completed=completed,
            failed=terminal_failed, pending=[], retry_wait={}, active=[], observed=[],
            max_own_tasks_per_gpu=1, max_attempts=args.max_attempts,
        ))
        # Terminal task failures are a completed scheduler state, not a
        # controller crash.  Keep systemd restart-on-failure for real crashes.
        return 0
    finally:
        for value in active.values():
            if value["process"].poll() is None:
                value["process"].terminate()
            if value["handle"] is not None:
                value["handle"].close()


if __name__ == "__main__":
    raise SystemExit(main())
