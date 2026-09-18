#!/usr/bin/env python3
"""Wait for our finite BLCA copy, validate coverage, then launch the 202 queue."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

from run_hnsc_blca_bernoulli_kan import ROOT, save_json

SSH = ['ssh', '-i', '/home/Lim/.ssh/id_ed25519_project4_pool', '-o', 'IdentitiesOnly=yes',
       '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'Lim@172.16.170.202']
REMOTE = '/new_data/Lim/MRePath_experiments/Project1'
PYTHON = '/new_data/Lim/MRePath_experiments/venvs/mrepath_20260913/bin/python'
OUT = ROOT / 'results/results_author_patient_disjoint_20260914'


def main():
    status = OUT / 'host202_bootstrap.json'
    try:
        while True:
            text = subprocess.check_output(['systemctl', '--user', 'show',
                'mrepath-blca-feature-mirror-stream-20260914.service',
                '--property=ActiveState', '--property=ExecMainStatus', '--property=Result'], text=True)
            state = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
            if state.get('ActiveState') not in ('active', 'activating', 'deactivating'):
                if state.get('ExecMainStatus', '0') != '0' or state.get('ActiveState') == 'failed':
                    raise RuntimeError(f'Copy failed; no training started on 202: {state}')
                break
            save_json(status, dict(state='waiting_for_feature_copy', at=time.time(), copy=state))
            time.sleep(15)
        relative = (ROOT / 'configs/blca_clean_transfer_20260914.txt').read_text().splitlines()
        expected = {name: (ROOT / name).stat().st_size for name in relative}
        code = ('import json; from pathlib import Path; '
                f'root=Path({REMOTE!r}); expected=json.loads({json.dumps(expected)!r}); '
                'bad=[p for p,n in expected.items() if not (root/p).is_file() or (root/p).stat().st_size!=n]; '
                'assert not bad, bad[:8]; '
                'print(json.dumps({"files":len(expected),"bytes":sum(expected.values()),"missing":bad}))')
        result = subprocess.check_output(SSH + [shlex.join([PYTHON, '-c', code])], text=True, timeout=45)
        save_json(OUT / 'host202_copy_audit.json', json.loads(result))
        jobs = [f'{model}:blca:{fold}' for fold in range(5) for model in ('survpath', 'pibd')]
        command = ['systemd-run', '--user', '--unit=mrepath-clean-baselines-202-20260914',
            '--description=Author-disjoint BLCA baselines; one project job per GPU',
            f'--property=WorkingDirectory={REMOTE}', '--property=Restart=no',
            '--setenv=LD_LIBRARY_PATH=/home/Lim/conda/envs/myenv/lib',
            '--setenv=PYTHONDONTWRITEBYTECODE=1', '--setenv=OMP_NUM_THREADS=4', '--setenv=MKL_NUM_THREADS=4',
            PYTHON, '-u', 'scripts/run_clean_baseline_queue.py',
            '--results-root', f'{REMOTE}/results/results_author_patient_disjoint_20260914',
            '--queue-name', 'queue_202', '--gpus', '0', '1', '--allow-gpu-sharing',
            '--min-gpu-free-mib', '18000', '--min-free-gib', '60',
            '--reserve-manifest', '/new_data/Lim/MRePath_GDC/manifests/brca_split_20260913/host202_data.tsv',
            '--reserve-raw', '/new_data/Lim/MRePath_GDC/raw_svs/tcga_brca', '--jobs', *jobs]
        subprocess.run(SSH + [shlex.join(command)], check=True, timeout=45)
        save_json(status, dict(state='queue_launched', at=time.time(), jobs=jobs, command=command))
    except BaseException as exc:
        save_json(status, dict(state='stopped', error=repr(exc), at=time.time()))
        raise


if __name__ == '__main__':
    main()
