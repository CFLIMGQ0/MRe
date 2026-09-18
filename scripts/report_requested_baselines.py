#!/usr/bin/env python3
"""Generate verified results for this request, including read-only checks on host 202.

Writes only generated reports under this run's result directory. It never starts,
stops or changes training, original splits, caches, table.md or historical results.
"""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

from run_hnsc_blca_bernoulli_kan import ROOT, completed_fold, rows, save_json
from run_pibd_survpath_5fold import completed
from validate_survival_predictions import validate_predictions

RUN = 'results/results_requested_baselines_5fold_20260913'
REMOTE_ROOT = '/new_data/Lim/MRePath_experiments/Project1'
REMOTE_PYTHON = '/new_data/Lim/MRePath_experiments/venvs/mrepath_20260913/bin/python'
COHORTS = ['blca', 'hnsc', 'coadread', 'stad', 'brca']
MODELS = ['mrepath', 'pibd', 'survpath']


def historical_split_path(cohort, fold):
    """This reporter is permanently scoped to the September 13 historical run."""
    archive = ROOT / 'splits/archive/pre_author_patient_disjoint_20260914/project'
    if cohort in ('blca', 'brca') and archive.exists():
        path = archive / f'tcga_{cohort}/splits_{fold}.csv'
        if not path.is_file():
            raise FileNotFoundError(f'Missing frozen historical split: {path}')
        return path
    return ROOT / f'splits/5folds/tcga_{cohort}/splits_{fold}.csv'


def local_snapshot(cohorts):
    records, errors = [], []
    for model in MODELS:
        for cohort in cohorts:
            if model == 'mrepath' and cohort not in ('blca', 'hnsc'):
                continue
            for fold in range(5):
                try:
                    if cohort == 'brca':
                        summaries = list((ROOT / 'results_brca_multimodal_5fold' / model).glob('*/summary.csv'))
                        if len(summaries) != 1:
                            raise ValueError(f'Expected one historical summary, got {len(summaries)}')
                        summary = summaries[0]
                        r, = [r for r in rows(summary) if int(r.get('fold', r.get('folds', -1))) == fold]
                        record = dict(fold=fold, val_cindex=float(r['val_cindex']), source_summary=str(summary))
                    else:
                        output = ROOT / RUN / model / cohort
                        record = (completed_fold(output, fold) if model == 'mrepath'
                                  else completed(model, output, fold))
                        if record is None:
                            continue
                    record = dict(record, model=model, cohort=cohort, fold=fold,
                                  val_cindex=float(record['val_cindex']), reused=(cohort == 'brca'))
                    parent = Path(record['source_summary']).parent
                    checkpoint = parent / ({'mrepath': f's_{fold}_best_checkpoint.pt',
                                            'pibd': f'model_best_s{fold}.pth',
                                            'survpath': f's_{fold}_checkpoint.pt'}[model])
                    if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
                        raise ValueError(f'Missing/noncomplete checkpoint: {checkpoint}')
                    predictions = parent / f'split_{fold}_results.pkl'
                    record.update(checkpoint=str(checkpoint), checkpoint_bytes=checkpoint.stat().st_size,
                                  predictions=str(predictions), validation=validate_predictions(
                                      predictions, record['val_cindex'], cohort, fold, ROOT,
                                      split_path=historical_split_path(cohort, fold)))
                    records.append(record)
                except Exception as exc:
                    errors.append(dict(model=model, cohort=cohort, fold=fold, error=repr(exc)))
    status = {}
    for path in [*(ROOT / RUN / 'mrepath').glob('*/pipeline_status.json'),
                 *(ROOT / RUN).glob('queue_*/pipeline_status.json')]:
        status[str(path.relative_to(ROOT / RUN))] = json.loads(path.read_text())
    return dict(at=time.time(), root=str(ROOT), records=records, errors=errors, queues=status)


def groups(records):
    result = []
    for model in MODELS:
        for cohort in COHORTS:
            if model == 'mrepath' and cohort not in ('blca', 'hnsc'):
                continue
            found = sorted([r for r in records if r['model'] == model and r['cohort'] == cohort],
                           key=lambda r: r['fold'])
            if len({r['fold'] for r in found}) != len(found):
                raise ValueError(f'Duplicate fold for {model}/{cohort}')
            values = [r['val_cindex'] for r in found]
            full = {r['fold'] for r in found} == set(range(5))
            result.append(dict(model=model, cohort=cohort, completed_folds=len(found), folds=found,
                               mean=statistics.mean(values) if full else None,
                               std_ddof0=statistics.pstdev(values) if full else None,
                               std_ddof1=statistics.stdev(values) if full else None))
    return result


def markdown(report):
    stamp = dt.datetime.fromtimestamp(report['at'], dt.timezone(dt.timedelta(hours=8)))
    lines = ['# 本轮原始 MRePath / PIBD / SurvPath 实验结果（自动更新）', '',
             f'更新时间：{stamp:%Y-%m-%d %H:%M:%S} 北京时间。', '',
             f'新增正式折已核验 {report["new_completed"]}/50；历史 BRCA 已核验 {report["reused_completed"]}/10。', '',
             '仅完整五折显示 Mean ± Std（总体标准差 ddof=0）；未完成项不以部分折均值充当五折结果。', '',
             '## 五折性能', '',
             '| 模型 | 数据集 | 已完成折 | Mean ± Std |',
             '|---|---|---:|---:|']
    for group in report['groups']:
        value = ('待完成' if group['mean'] is None else
                 f'{group["mean"]:.4f} ± {group["std_ddof0"]:.4f}')
        lines.append(f'| {group["model"]} | {group["cohort"].upper()} | {group["completed_folds"]}/5 | {value} |')
    lines += ['', '## 每折 C-index', '', '| 模型 | 数据集 | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 |',
              '|---|---|---:|---:|---:|---:|---:|']
    for group in report['groups']:
        values = {r['fold']: r['val_cindex'] for r in group['folds']}
        fields = [group['model'], group['cohort'].upper(),
                  *[f'{values[f]:.6f}' if f in values else '—' for f in range(5)]]
        lines.append('| ' + ' | '.join(fields) + ' |')
    lines += ['', '## 状态与边界', '',
              '- 本报告只核验 2026-09-13 历史实验，不是新划分成绩。BLCA 旧划分每折重叠 11、13、13、13、13 人，BRCA 为 14、11、22、21、15 人；不能解释为无同折患者泄漏的泛化性能。',
              '- 项目切换划分后，本报告按归档的旧划分核验历史预测；新划分必须使用独立结果目录重新训练。',
              '- 新结果不是论文报告值；此处不混入 Bernoulli + KAN、AES 或一轮试运行结果。',
              '- 共同使用 DSS、seed=1、30 epochs 和仓库划分；各模型保留专用结构/损失。模型原生 batch、抽样、时间分箱仍有差异，见 RUN_STATUS.md。',
              '- 验证患者集合、DSS 标签、风险有限性及病例级 C-index 均已核验；每折预测、检查点路径在 results.json。',
              f'- 202 本次读取：{"成功" if report["remote_fresh"] else "失败；下列远端结果为上次成功快照，不代表当前进度"}。']
    for host, snapshot in report['snapshots'].items():
        for name, status in snapshot.get('queues', {}).items():
            active = ', '.join(f'{r["job"]}@GPU{r["gpu"]}' for r in status.get('active', [])) or '无'
            lines.append(f'- {host} / {name}: {status.get("state", "未知")}；运行：{active}；'
                         f'待调度 {len(status.get("pending", []))}；失败 {len(status.get("failed", {}))}。')
    if report['errors']:
        lines += ['', '需检查的异常：', '', '```json', json.dumps(report['errors'], ensure_ascii=False, indent=2), '```']
    lines += ['', f'本请求全部完成：{"是" if report["complete"] else "否"}。', '']
    return '\n'.join(lines)


def update():
    output = ROOT / RUN
    local = local_snapshot(['blca', 'coadread', 'stad', 'brca', 'hnsc'])
    cache = output / 'remote_202_snapshot.json'
    remote_fresh, network_errors = False, []
    try:
        command = ['ssh', '-i', '/home/Lim/.ssh/id_ed25519_project4_pool', '-o', 'IdentitiesOnly=yes',
                   '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'Lim@172.16.170.202',
                   f'LD_LIBRARY_PATH=/home/Lim/conda/envs/myenv/lib PYTHONDONTWRITEBYTECODE=1 '
                   f'{REMOTE_PYTHON} {REMOTE_ROOT}/scripts/report_requested_baselines.py --snapshot-json --cohorts hnsc']
        remote = json.loads(subprocess.check_output(command, text=True, timeout=45))
        save_json(cache, remote)
        remote_fresh = True
    except Exception as exc:
        network_errors.append(dict(host='202', error=repr(exc)))
        remote = json.loads(cache.read_text()) if cache.is_file() else dict(records=[], errors=[], queues={})
    records = [dict(r, host=host) for host, snapshot in [('204', local), ('202', remote)]
               for r in snapshot['records']]
    grouped = groups(records)
    errors = [*local['errors'], *remote['errors'], *network_errors]
    report = dict(at=time.time(), groups=grouped, snapshots={'204': local, '202': remote},
                  new_completed=sum(not r['reused'] for r in records),
                  reused_completed=sum(r['reused'] for r in records),
                  remote_fresh=remote_fresh, errors=errors,
                  complete=remote_fresh and not errors and all(g['completed_folds'] == 5 for g in grouped))
    save_json(output / 'results.json', report)
    temporary = output / 'LIVE_RESULTS.md.partial'
    temporary.write_text(markdown(report), encoding='utf-8')
    temporary.replace(output / 'LIVE_RESULTS.md')
    print(json.dumps({k: report[k] for k in ['at', 'new_completed', 'reused_completed', 'remote_fresh', 'complete', 'errors']}), flush=True)
    return report['complete']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-json', action='store_true')
    parser.add_argument('--cohorts', nargs='+', choices=COHORTS, default=COHORTS)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if args.snapshot_json:
        print(json.dumps(local_snapshot(args.cohorts)))
        return
    lock = (ROOT / RUN / 'report.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    while True:
        try:
            done = update()
            save_json(ROOT / RUN / 'report_status.json', dict(at=time.time(), healthy=True, complete=done))
        except Exception as exc:
            save_json(ROOT / RUN / 'report_status.json', dict(at=time.time(), healthy=False, error=repr(exc)))
            print(f'Report update failed; previous reports retained: {exc!r}', flush=True)
            if not args.watch:
                raise
            done = False
        if done or not args.watch:
            return
        time.sleep(60)


if __name__ == '__main__':
    main()
