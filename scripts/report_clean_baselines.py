#!/usr/bin/env python3
"""Report this 130-fold request without counting blocked jobs as launched."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import statistics
import time

from run_hnsc_blca_bernoulli_kan import ROOT, save_json

RELATIVE = 'results/results_author_patient_disjoint_20260914'
OUTPUT = ROOT / RELATIVE


def merge_results(*snapshots):
    """Merge disjoint fold ownership across hosts, never duplicate a fold."""
    combined = {}
    for snapshot in snapshots:
        for key, value in snapshot['data'].items():
            if key not in combined:
                combined[key] = dict(value, folds=list(value['folds']))
                continue
            old = combined[key]
            if old.get('protocol') != value.get('protocol'):
                raise RuntimeError(f'Cross-host protocol mismatch: {key}')
            owned = {r['fold'] for r in old['folds']}
            if owned & {r['fold'] for r in value['folds']}:
                raise RuntimeError(f'Duplicate cross-host fold ownership: {key}')
            old['folds'].extend(value['folds'])
    for value in combined.values():
        value['folds'].sort(key=lambda r: r['fold'])
        folds = [r['fold'] for r in value['folds']]
        if len(set(folds)) != len(folds) or not set(folds) <= set(range(5)):
            raise RuntimeError('Invalid fold IDs in verified results')
        scores = [r['val_cindex'] for r in value['folds']]
        value.update(completed_folds=len(folds),
                     mean=statistics.mean(scores) if len(folds) == 5 else None,
                     std_ddof0=statistics.pstdev(scores) if len(folds) == 5 else None)
    return combined


def snapshot():
    data = {}
    for model in ('mrepath', 'pibd', 'survpath'):
        for cohort in ('blca', 'brca'):
            path = OUTPUT / model / cohort / 'verified_results.json'
            if path.is_file():
                data[f'{model}:{cohort}'] = json.loads(path.read_text())
    queues = {}
    for path in OUTPUT.glob('queue_*/pipeline_status.json'):
        queues[path.parent.name] = json.loads(path.read_text())
    return dict(at=time.time(), data=data, queues=queues)


def update():
    local = snapshot()
    remote_error = None
    try:
        cmd = ['ssh', '-i', '/home/Lim/.ssh/id_ed25519_project4_pool', '-o', 'IdentitiesOnly=yes',
               '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'Lim@172.16.170.202',
               'PYTHONDONTWRITEBYTECODE=1 /new_data/Lim/MRePath_experiments/venvs/mrepath_20260913/bin/python '
               '/new_data/Lim/MRePath_experiments/Project1/scripts/report_clean_baselines.py --snapshot']
        remote = json.loads(subprocess.check_output(cmd, text=True, timeout=30))
    except Exception as exc:
        remote_error = repr(exc)
        remote = dict(data={}, queues={})
    combined = merge_results(local, remote)
    completed = sum(v['completed_folds'] for v in combined.values())
    stamp = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    lines = ['# 新划分基线与新增模型请求', '', f'更新时间：{stamp}', '',
        f'总请求 130 折；前三模型已安排 30 折，已核验完成 {completed}/30 折。',
        '后四模型共 100 折尚待输入协议确认和依赖准备，**未进入训练队列**。', '',
        '## 原始模型重跑', '', '| 模型 | 数据集 | 已核验完成 | C-index（五折 Mean ± SD） |',
        '|---|---|---:|---|']
    for model in ('mrepath', 'pibd', 'survpath'):
        for cohort in ('blca', 'brca'):
            r = combined.get(f'{model}:{cohort}', {})
            n = r.get('completed_folds', 0)
            score = f'{r["mean"]:.4f} ± {r["std_ddof0"]:.4f}' if n == 5 else '尚无完整五折成绩'
            lines.append(f'| {model} | {cohort.upper()} | {n}/5 | {score} |')
    lines += ['', '## 当前 GPU 队列', '', '| 主机 | GPU | 本项目任务 |', '|---|---|---|']
    for host, state in [('204', local), ('202', remote)]:
        for queue in state['queues'].values():
            for job in queue.get('active', []):
                lines.append(f'| {host} | {job["gpu"]} | {job["job"]}（PID {job["pid"]}） |')
    lines += ['', '## 队列状态（停止不等于完成）', '']
    for host, state in [('204', local), ('202', remote)]:
        for name, queue in state['queues'].items():
            message = f'- {host} / {name}：{queue.get("state", "unknown")}'
            if queue.get('error'):
                message += f'；原因：{queue["error"]}'
            if queue.get('failed'):
                message += f'；失败任务：{queue["failed"]}'
            lines.append(message)
    for filename, label in [('host202_bootstrap.json', '202 首批 BLCA 队列启动记录'),
                            ('host202_brca_recovery_bootstrap.json', '202 剩余 BRCA 折恢复状态')]:
        bootstrap = OUTPUT / filename
        if bootstrap.is_file():
            record = json.loads(bootstrap.read_text())
            lines += ['', label + '：`' + record['state'] + '`。']
            if record.get('error'):
                lines += ['', '原因：`' + record['error'] + '`。']
    if remote_error:
        lines += ['', '202 本次读取失败；不能据此断言任务停止：`' + remote_error + '`。']
    lines += ['', '## 新增四个模型（每个模型五队列、25 折）', '',
        '| 模型 | 当前状态 |', '|---|---|',
        '| MMP | 官方代码已获取；缺官方配方图像特征、训练折原型，HNSC 还需队列/RNA适配 |',
        '| LD-CVAE | 缺官方配方图像特征；COREAD/STAD/HNSC 需队列适配 |',
        '| DIMAF | 缺 UNI 特征、每折训练集原型；COREAD/STAD/HNSC 需队列/RNA适配 |',
        '| SlotSPE | 缺 UNI 特征和作者外链 RNA；统一队列需要另做输入适配 |', '',
        '待确认：是否统一使用项目现有 ResNet/RNA/DSS/五折，并保留官方核心模型结构。',
        '这与各模型官方原生 Encoder/队列协议不同，不应混称。', '',
        '## 边界', '',
        '- BLCA 357 人，BRCA 868 人；使用 2026-09-14 作者衍生划分，每折患者互斥。',
        '- 每 GPU 最多一个本项目任务；不终止其他项目进程，显存不足时等待。',
        '- 原始 MRePath 不使用 AES、Bernoulli、KAN 或 Quality + Conflict。',
        '- 旧结果不复用或覆盖。当前仅完整五折汇总；SD 为总体标准差 ddof=0。',
        '- 三模型保留各自既有 batch/损失/抽样/时间分箱差异，不能声称训练协议完全一致。', '']
    save_json(OUTPUT / 'results.json', dict(at=time.time(), requested_folds=130,
        scheduled_baseline_folds=30, additional_model_folds_not_launched=100,
        verified_completed_folds=completed, models=combined, snapshots={'204':local,'202':remote},
        remote_error=remote_error))
    (OUTPUT / 'LIVE_RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(completed=completed, remote_error=remote_error)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', action='store_true')
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if args.snapshot:
        print(json.dumps(snapshot()))
    else:
        while True:
            try:
                update()
            except Exception as exc:
                print(repr(exc), flush=True)
                if not args.watch:
                    raise
            if not args.watch:
                break
            time.sleep(60)
