#!/usr/bin/env python3
"""Persistent health monitor for the 2026-09-16 six-GPU experiment queue."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
SSH = [
    "ssh", "-i", "/home/Lim/.ssh/id_ed25519_project4_pool",
    "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
    "Lim@172.16.170.202",
]
FINAL_STATES = {"completed", "completed_with_failures"}
SERVICES = {
    "gpu_queue": ("mrepath-requested-six-gpu-20260916.service", "pipeline_status.json"),
    "aes_cache": ("mrepath-aes-cache-20260916.service", "cache_pipeline_status.json"),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--critical-free-gib", type=float, default=20.0)
    return parser.parse_args()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def service_active(name: str):
    result = subprocess.run(["systemctl", "--user", "is-active", name], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return result.stdout.strip() == "active"


def ensure_services(state_dir: Path):
    status, actions = {}, []
    for label, (service, state_name) in SERVICES.items():
        active = service_active(service)
        state = read_json(state_dir / state_name)
        final = bool(state and state.get("state") in FINAL_STATES)
        if not active and not final:
            result = subprocess.run(["systemctl", "--user", "restart", service], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            actions.append(dict(action="restart_service", service=service,
                                returncode=result.returncode, stderr=result.stderr[-1000:]))
            active = service_active(service)
        status[label] = dict(service=service, active=active,
                             pipeline_state=state.get("state") if state else None)
    return status, actions


def usage(path: Path):
    value = shutil.disk_usage(path)
    return dict(path=str(path), total_bytes=value.total, used_bytes=value.used,
                free_bytes=value.free, free_gib=value.free / 2**30,
                percent_used=100.0 * value.used / value.total)


def remote_filesystems():
    code = r'''
import json, shutil
out=[]
for path in ('/', '/new_data'):
    value=shutil.disk_usage(path)
    out.append(dict(path=path,total_bytes=value.total,used_bytes=value.used,free_bytes=value.free,
                    free_gib=value.free/2**30,percent_used=100.0*value.used/value.total))
print(json.dumps(out))
'''
    output = subprocess.check_output(SSH + ["python3 -c " + shlex.quote(code)], text=True, timeout=20)
    return json.loads(output)


def gpu_snapshot():
    # Import here so the monitor and the dispatcher use exactly the same
    # definition of an owned task, including CPU-only DIMAF preparation.
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_requested_six_gpu_scheduler import gpu_rows, task_processes

    result = {}
    for host in ("204", "202"):
        try:
            tasks = task_processes(host)
            rows = gpu_rows(host, tasks)
            by_gpu = {}
            for item in tasks:
                by_gpu.setdefault(item["gpu"], []).append(item["label"])
            result[host] = dict(
                reachable=True,
                gpus={gpu: dict(free_mib=value["free"], used_mib=value["used"],
                                owned_tasks=sorted(set(by_gpu.get(gpu, []))),
                                owned_process_count=len(value["own_processes"]))
                      for gpu, value in rows.items()},
            )
        except Exception as exc:
            result[host] = dict(reachable=False, error=repr(exc), gpus={})
    return result


def heartbeat_snapshot(local_results: Path):
    values = []
    for path in local_results.glob("**/heartbeat.json"):
        value = read_json(path)
        if value is not None:
            values.append(dict(path=str(path), **value))
    return values


def remote_heartbeat_snapshot():
    code = r'''
import json
from pathlib import Path
out=[]
for path in Path('/home/Lim/MRePath_runs/requested_full_20260916').glob('**/heartbeat.json'):
    try:
        value=json.loads(path.read_text())
        out.append(dict(path=str(path), **value))
    except (OSError, json.JSONDecodeError):
        pass
print(json.dumps(out))
'''
    output = subprocess.check_output(SSH + ["python3 -c " + shlex.quote(code)], text=True, timeout=20)
    return json.loads(output)


def terminate_stale(item):
    """Terminate one exact owned task after eight hours without log progress."""
    pid = int(item["wrapper_pid"])
    if item["host"] == "204":
        cmdline = (Path("/proc") / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ")
        if b"run_requested_model_task.py" not in cmdline or b"requested_full_20260916" not in cmdline:
            raise RuntimeError("stale PID no longer belongs to the requested queue")
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return
    code = f'''
import os, signal
from pathlib import Path
pid={pid}
cmd=(Path('/proc')/str(pid)/'cmdline').read_bytes().replace(b'\\0',b' ')
if b'run_requested_model_task.py' not in cmd or b'requested_full_20260916' not in cmd:
    raise SystemExit('PID ownership changed')
os.killpg(os.getpgid(pid), signal.SIGTERM)
'''
    subprocess.check_call(SSH + ["python3 -c " + shlex.quote(code)], timeout=20)


def main():
    args = parse_args()
    args.state_dir = args.state_dir.resolve()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    health_path = args.state_dir / "health_status.json"
    events_path = args.state_dir / "health_events.jsonl"
    previous_signature = None
    while True:
        checked_at = time.time()
        issues, warnings, actions = [], [], []
        try:
            services, service_actions = ensure_services(args.state_dir)
            actions.extend(service_actions)
        except Exception as exc:
            services = {}
            issues.append(dict(kind="service_monitor_error", error=repr(exc)))

        disks = {"204": [], "202": []}
        for path, role in ((Path("/"), "system_read_only_for_queue"),
                           (Path("/xmlg"), "local_results_and_aes_cache")):
            try:
                disks["204"].append(dict(role=role, **usage(path)))
            except Exception as exc:
                issues.append(dict(kind="disk_query_failed", host="204", path=str(path), error=repr(exc)))
        try:
            for value in remote_filesystems():
                value["role"] = ("remote_results_and_hnsc_aes_cache" if value["path"] == "/"
                                 else "source_data_read_only_for_queue")
                disks["202"].append(value)
        except Exception as exc:
            issues.append(dict(kind="host_unreachable", host="202", error=repr(exc)))

        for host, values in disks.items():
            for value in values:
                if value["free_gib"] < args.critical_free_gib:
                    issues.append(dict(kind="critical_disk_free", host=host, path=value["path"],
                                       free_gib=value["free_gib"], role=value["role"]))
                elif value["free_gib"] < 40:
                    warnings.append(dict(kind="low_disk_headroom", host=host, path=value["path"],
                                         free_gib=value["free_gib"], role=value["role"]))

        gpus = gpu_snapshot()
        for host, host_value in gpus.items():
            if not host_value.get("reachable"):
                issues.append(dict(kind="gpu_query_failed", host=host,
                                   error=host_value.get("error")))
                continue
            for gpu, value in host_value["gpus"].items():
                if len(value["owned_tasks"]) > 1:
                    issues.append(dict(kind="multiple_owned_tasks_on_gpu", host=host, gpu=gpu,
                                       tasks=value["owned_tasks"]))

        pipeline = read_json(args.state_dir / "pipeline_status.json") or {}
        cache_pipeline = read_json(args.state_dir / "cache_pipeline_status.json") or {}
        for name, value in (("gpu_queue", pipeline), ("aes_cache", cache_pipeline)):
            if value.get("failed"):
                issues.append(dict(kind="terminal_task_failures", pipeline=name,
                                   failures=value["failed"]))

        local_heartbeats = [dict(item, host="204") for item in
                            heartbeat_snapshot(ROOT / "results/requested_full_20260916")]
        try:
            remote_heartbeats = [dict(item, host="202") for item in remote_heartbeat_snapshot()]
        except Exception as exc:
            remote_heartbeats = []
            issues.append(dict(kind="remote_heartbeat_query_failed", error=repr(exc)))
        for heartbeat in local_heartbeats + remote_heartbeats:
            if heartbeat.get("state") != "running":
                continue
            heartbeat_age = checked_at - float(heartbeat.get("checked_at", 0))
            log_age = checked_at - float(heartbeat.get("log_mtime") or checked_at)
            if heartbeat_age > 180:
                issues.append(dict(kind="stale_task_heartbeat", host=heartbeat["host"],
                                   path=heartbeat["path"], age_seconds=heartbeat_age))
            if heartbeat_age <= 180 and log_age > 8 * 3600:
                issue = dict(kind="no_log_progress_8h", host=heartbeat["host"],
                             path=heartbeat["path"], log_age_seconds=log_age)
                issues.append(issue)
                try:
                    terminate_stale(heartbeat)
                    actions.append(dict(action="terminate_stale_task_for_retry", **issue))
                except Exception as exc:
                    actions.append(dict(action="stale_task_termination_failed", **issue,
                                        error=repr(exc)))

        snapshot = dict(
            state="healthy" if not issues else "attention",
            checked_at=checked_at,
            policy=dict(gpu_poll_seconds=20, monitor_poll_seconds=args.poll_seconds,
                        max_owned_tasks_per_gpu=1, gpu_start_free_mib=18000,
                        training_disk_launch_free_gib=60, aes_disk_free_gib=dict(local=80, remote=60),
                        critical_free_gib=args.critical_free_gib, max_attempts_per_task=12,
                        retry_backoff_seconds="60 exponential, capped at 21600"),
            services=services, disks=disks, gpus=gpus,
            pipeline_summary=dict(state=pipeline.get("state"), planned=pipeline.get("planned"),
                                  completed=len(pipeline.get("completed", {})),
                                  active=pipeline.get("active", []), observed=pipeline.get("observed", []),
                                  pending=len(pipeline.get("pending", [])),
                                  retry_wait=pipeline.get("retry_wait", {}),
                                  failed=pipeline.get("failed", {})),
            cache_summary=dict(state=cache_pipeline.get("state"),
                               completed=cache_pipeline.get("completed", []),
                               active=cache_pipeline.get("active", []),
                               observed=cache_pipeline.get("observed", []),
                               pending=cache_pipeline.get("pending", []),
                               retry_wait=cache_pipeline.get("retry_wait", {}),
                               failed=cache_pipeline.get("failed", {})),
            local_heartbeats=local_heartbeats, remote_heartbeats=remote_heartbeats,
            actions=actions, warnings=warnings, issues=issues,
        )
        atomic_json(health_path, snapshot)
        signature = json.dumps(dict(state=snapshot["state"], services=services,
                                    actions=actions, warnings=warnings, issues=issues),
                               sort_keys=True, ensure_ascii=False)
        if signature != previous_signature:
            with events_path.open("a") as handle:
                handle.write(json.dumps(dict(at=checked_at, state=snapshot["state"],
                                             actions=actions, warnings=warnings, issues=issues),
                                        ensure_ascii=False) + "\n")
            previous_signature = signature
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
