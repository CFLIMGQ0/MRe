#!/usr/bin/env python3
"""Build five AES caches in background CPU slots; HNSC runs on host202."""
from __future__ import annotations

import argparse
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
SSH = ["ssh", "-i", "/home/Lim/.ssh/id_ed25519_project4_pool", "-o", "IdentitiesOnly=yes",
       "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "Lim@172.16.170.202"]


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def remote_file(path):
    return subprocess.run(SSH + [f"test -f {shlex.quote(str(path))}"], timeout=20).returncode == 0


def cache_path(cohort, host):
    if host == "202":
        return Path("/home/Lim/MRePath_aes_cache_20260916") / f"{cohort}_p0.8_T0.001"
    return ROOT / f"data/tcga_{cohort}/clam_20x_resnet50_paper_k9/hypergraph_cache_aes_p0.8_T0.001"


def complete(cohort, host):
    path = cache_path(cohort, host) / "complete.json"
    return path.is_file() if host == "204" else remote_file(path)


def launch(cohort, host, state_dir, min_free_gib):
    root = ROOT if host == "204" else REMOTE_ROOT
    python = root / ".venvs/repository_baselines_20260913/bin/python"
    # Cache construction is background preprocessing.  Idle I/O priority keeps
    # large graph reads from starving active GPU training on the same disk.
    values = ["ionice", "-c", "3", "nice", "-n", "10",
              str(python), "-u", str(root / "scripts/run_aes_cache_task.py"),
              "--cohort", cohort, "--cache-dir", str(cache_path(cohort, host)),
              "--p", "0.8", "--T", "0.001", "--min-free-gib", str(min_free_gib)]
    log = state_dir / f"aes_cache_{host}_{cohort}.log"
    handle = log.open("a")
    if host == "204":
        env = dict(os.environ, OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4",
                   PYTHONDONTWRITEBYTECODE="1", LD_LIBRARY_PATH="/xmlg/Lim/conda/envs/myenv/lib")
        child = subprocess.Popen(values, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    else:
        shell = (f"cd {shlex.quote(str(REMOTE_ROOT))} && OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 "
                 "OPENBLAS_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 "
                 f"LD_LIBRARY_PATH=/home/Lim/conda/envs/myenv/lib {shlex.join(values)}")
        child = subprocess.Popen(SSH + [shell], stdout=handle, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    return child, handle, str(log)


def local_cache_processes():
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = [part.decode(errors="replace") for part in
                    (entry / "cmdline").read_bytes().split(b"\0") if part]
            if not any(value.endswith("run_aes_cache_task.py") for value in argv):
                continue
            cohort = argv[argv.index("--cohort") + 1]
            found.append(dict(pid=int(entry.name), cohort=cohort, host="204"))
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            continue
    return found


def remote_cache_processes():
    code = r'''
import json
from pathlib import Path
out = []
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        argv = [x.decode(errors='replace') for x in (entry/'cmdline').read_bytes().split(b'\0') if x]
        if not any(x.endswith('run_aes_cache_task.py') for x in argv):
            continue
        out.append(dict(pid=int(entry.name), cohort=argv[argv.index('--cohort') + 1], host='202'))
    except (FileNotFoundError, PermissionError, ValueError, IndexError):
        pass
print(json.dumps(out))
'''
    result = subprocess.check_output(SSH + ["python3 -c " + shlex.quote(code)], text=True, timeout=20)
    return json.loads(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--local-slots", type=int, default=1)
    parser.add_argument("--local-min-free-gib", type=float, default=80.0)
    parser.add_argument("--remote-min-free-gib", type=float, default=60.0)
    parser.add_argument("--max-attempts", type=int, default=12)
    parser.add_argument("--retry-base-seconds", type=int, default=60)
    parser.add_argument("--retry-max-seconds", type=int, default=21600)
    args = parser.parse_args()
    args.state_dir = args.state_dir.resolve()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    import fcntl
    lock = (args.state_dir / "cache_scheduler.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    tasks = [(cohort, "204") for cohort in ("blca", "brca", "coadread", "stad")] + [("hnsc", "202")]
    active, terminal_failed = {}, {}
    retry_path = args.state_dir / "cache_retry_state.json"
    try:
        retry_state = json.loads(retry_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        retry_state = {}
    terminal_failed.update({label: value for label, value in retry_state.items()
                            if int(value.get("attempts", 0)) >= args.max_attempts})

    def save_retries():
        atomic_json(retry_path, retry_state)

    def record_failure(key, exit_code, log, reason=None):
        cohort, host = key
        label = f"{host}:{cohort}"
        prior = retry_state.get(label, {})
        attempts = int(prior.get("attempts", 0)) + 1
        delay = min(args.retry_base_seconds * (2 ** max(0, attempts - 1)), args.retry_max_seconds)
        value = dict(attempts=attempts, last_failure_at=time.time(), retry_after=time.time() + delay,
                     exit_code=exit_code, log=log, reason=reason)
        retry_state[label] = value
        save_retries()
        if attempts >= args.max_attempts:
            terminal_failed[label] = value
    try:
        while True:
            for key, value in list(active.items()):
                code = value[0].poll()
                if code is None:
                    continue
                value[1].close()
                del active[key]
                try:
                    finished = code == 0 and complete(*key)
                except Exception:
                    finished = False
                if finished:
                    retry_state.pop(f"{key[1]}:{key[0]}", None)
                    save_retries()
                else:
                    record_failure(key, code, value[2])

            try:
                observed = local_cache_processes() + remote_cache_processes()
            except Exception:
                observed = local_cache_processes()
            observed = [item for item in observed
                        if (item["cohort"], item["host"]) not in active]
            observed_keys = {(item["cohort"], item["host"]) for item in observed}
            completed = []
            for task in tasks:
                try:
                    if complete(*task):
                        completed.append(task)
                        retry_state.pop(f"{task[1]}:{task[0]}", None)
                except Exception:
                    pass
            save_retries()
            now = time.time()
            unfinished = [task for task in tasks if task not in completed and task not in active
                          and task not in observed_keys
                          and f"{task[1]}:{task[0]}" not in terminal_failed]
            pending = [task for task in unfinished if float(retry_state.get(
                f"{task[1]}:{task[0]}", {}).get("retry_after", 0)) <= now]
            retry_wait = [task for task in unfinished if task not in pending]
            local_count = sum(host == "204" for _, host in active)
            remote_count = sum(host == "202" for _, host in active)
            local_count += sum(item["host"] == "204" for item in observed)
            remote_count += sum(item["host"] == "202" for item in observed)
            for task in list(pending):
                cohort, host = task
                if (host == "204" and local_count >= args.local_slots) or (host == "202" and remote_count >= 1):
                    continue
                path = cache_path(cohort, host)
                try:
                    free = (shutil.disk_usage(path.parent).free / 2**30 if host == "204" else
                            int(subprocess.check_output(
                                SSH + [f"df --output=avail -B1 {shlex.quote(str(path.parent))} | tail -1"],
                                text=True, timeout=20).strip()) / 2**30)
                except Exception as exc:
                    record_failure(task, -1, None, reason=f"disk query failed: {exc!r}")
                    pending.remove(task)
                    continue
                minimum = args.local_min_free_gib if host == "204" else args.remote_min_free_gib
                if free < minimum:
                    continue
                try:
                    active[task] = launch(cohort, host, args.state_dir, minimum)
                except Exception as exc:
                    record_failure(task, -1, None, reason=repr(exc))
                    pending.remove(task)
                    continue
                pending.remove(task)
                local_count += host == "204"
                remote_count += host == "202"
            atomic_json(args.state_dir / "cache_pipeline_status.json", dict(
                state="running" if active or pending or retry_wait or observed else
                      ("completed_with_failures" if terminal_failed else "completed"),
                at=time.time(), p=0.8, T=0.001,
                min_free_gib=dict(local=args.local_min_free_gib, remote=args.remote_min_free_gib),
                max_attempts=args.max_attempts,
                completed=[f"{host}:{cohort}" for cohort, host in completed],
                pending=[f"{host}:{cohort}" for cohort, host in pending],
                retry_wait={f"{host}:{cohort}": retry_state[f"{host}:{cohort}"]
                            for cohort, host in retry_wait},
                active=[dict(host=host, cohort=cohort, pid=value[0].pid, log=value[2])
                        for (cohort, host), value in active.items()],
                observed=observed, failed=terminal_failed,
            ))
            if not active and not pending and not retry_wait and not observed:
                break
            time.sleep(args.poll_seconds)
        return 0
    finally:
        for process, handle, _ in active.values():
            if process.poll() is None:
                process.terminate()
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
