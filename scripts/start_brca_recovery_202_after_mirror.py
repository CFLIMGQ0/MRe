"""Stage existing BRCA features; start only SurvPath folds 3/4 on host 202."""
import argparse
import csv
import json
from pathlib import Path
import shlex
import subprocess
import time

from run_hnsc_blca_bernoulli_kan import ROOT, save_json

SSH = ['ssh', '-i', '/home/Lim/.ssh/id_ed25519_project4_pool', '-o', 'IdentitiesOnly=yes',
       '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'Lim@172.16.170.202']
REMOTE = '/new_data/Lim/MRePath_experiments/Project1'
PYTHON = '/new_data/Lim/MRePath_experiments/venvs/mrepath_20260913/bin/python'
OUTPUT = ROOT / 'results/results_author_patient_disjoint_20260914'
FILES = ROOT / 'configs/brca_recovery_transfer_20260914.txt'
MANIFEST = ROOT / 'configs/brca_recovery_transfer_20260914.json'
UNIT = 'mrepath-brca-recovery-feature-mirror-20260914.service'


def prepare():
    ids = set()
    for fold in range(5):
        with (ROOT / f'splits/5folds/tcga_brca/splits_{fold}.csv').open() as handle:
            for row in csv.DictReader(handle):
                ids.update(row[k] for k in ('train', 'val') if row[k])
    with (ROOT / 'datasets_csv/metadata/tcga_brca.csv').open() as handle:
        slides = {Path(r['slide_id']).stem for r in csv.DictReader(handle) if r['case_id'] in ids}
    assert len(ids) == 868 and len(slides) == 926
    names = [f'data/tcga_brca/clam_20x_resnet50_paper_k9/pt_files/{s}.pt' for s in sorted(slides)]
    names += ['datasets_csv/metadata/tcga_brca.csv',
              'datasets_csv/raw_rna_data/combine/brca/rna_clean.csv',
              'datasets_csv/clinical_data/tcga_brca_clinical.csv']
    sizes = {p: (ROOT / p).stat().st_size for p in names}
    FILES.write_text('\n'.join(names) + '\n')
    save_json(MANIFEST, dict(files=sizes, bytes=sum(sizes.values()), slides=len(slides),
                            at=time.time(), jobs=['survpath:brca:3', 'survpath:brca:4']))
    print(json.dumps(dict(files=len(sizes), GiB=sum(sizes.values())/2**30)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return
    status = OUTPUT / 'host202_brca_recovery_bootstrap.json'
    try:
        while True:
            result = subprocess.check_output(['systemctl', '--user', 'show', UNIT,
                '--property=ActiveState', '--property=ExecMainStatus', '--property=Result'], text=True)
            state = dict(line.split('=', 1) for line in result.splitlines() if '=' in line)
            if state.get('ActiveState') not in ('active', 'activating', 'deactivating'):
                if state.get('ExecMainStatus', '0') != '0' or state.get('ActiveState') == 'failed':
                    raise RuntimeError(f'Feature copy failed; no training launched: {state}')
                break
            free = int(subprocess.check_output(SSH + [shlex.join([PYTHON, '-c',
                "import shutil; print(shutil.disk_usage('/new_data/Lim').free)"])],
                text=True, timeout=30))
            if free < 24 * 2**30:
                subprocess.run(['systemctl', '--user', 'stop', UNIT], check=True, timeout=45)
                raise RuntimeError('202 feature disk below 24 GiB reserve; our copy stopped, partial files retained')
            save_json(status, dict(state='waiting_for_feature_copy', at=time.time(), copy=state))
            time.sleep(15)
        expected = json.loads(MANIFEST.read_text())['files']
        code = ('import json; from pathlib import Path; '
                f'root=Path({REMOTE!r}); expected=json.loads({json.dumps(expected)!r}); '
                'bad=[p for p,n in expected.items() if not (root/p).is_file() or (root/p).stat().st_size!=n]; '
                'assert not bad, bad[:8]; '
                'print(json.dumps({"files":len(expected),"bytes":sum(expected.values()),"missing":bad}))')
        checked = subprocess.run(SSH + [shlex.join([PYTHON, '-'])], input=code,
                                 text=True, capture_output=True, check=True, timeout=60).stdout
        save_json(OUTPUT / 'host202_brca_copy_audit.json', json.loads(checked))
        command = ['systemd-run', '--user', '--unit=mrepath-clean-baselines-202-storage-recovery-20260914',
            '--description=BRCA SurvPath remaining folds; system-disk output; one job per GPU',
            f'--property=WorkingDirectory={REMOTE}', '--property=Restart=no',
            '--setenv=LD_LIBRARY_PATH=/home/Lim/conda/envs/myenv/lib',
            '--setenv=PYTHONDONTWRITEBYTECODE=1', '--setenv=OMP_NUM_THREADS=4', '--setenv=MKL_NUM_THREADS=4',
            PYTHON, '-u', 'scripts/run_clean_baseline_queue.py',
            '--results-root', f'{REMOTE}/results/results_author_patient_disjoint_20260914',
            '--queue-name', 'queue_202_recovery', '--gpus', '0', '1', '--allow-gpu-sharing',
            '--min-gpu-free-mib', '6000', '--min-free-gib', '32', '--reserve-gib', '22',
            '--jobs', 'survpath:brca:3', 'survpath:brca:4']
        subprocess.run(SSH + [shlex.join(command)], check=True, timeout=45)
        save_json(status, dict(state='queue_launched', at=time.time(), command=command))
    except BaseException as exc:
        save_json(status, dict(state='stopped', error=repr(exc), at=time.time()))
        raise


if __name__ == '__main__':
    main()
