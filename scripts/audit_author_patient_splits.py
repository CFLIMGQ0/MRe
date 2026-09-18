"""Read-only audit of the author-derived BLCA/BRCA patient split migration."""
import argparse
from collections import Counter
import csv
import hashlib
import io
from itertools import zip_longest
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'author_patient_disjoint_20260914'
ARCHIVE = 'archive/pre_author_patient_disjoint_20260914'
SOURCES = {
    'survpath': ('third_party/SurvPath_20260913', '3f73ddd6705ec67d643020c5bb04fb13f9f382cc'),
    'pibd': ('third_party/PIBD_20260913', 'bd5bd94e6f8d48e7679c6e68209a3a65c9e56a78'),
}


def rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def read_split(content):
    records = list(csv.DictReader(io.StringIO(content)))
    return {key: [r[key] for r in records if r[key]] for key in ('train', 'val')}


def filtered_split(content, cohort):
    """Only remove non-cohort patients; preserve authors' fold and list order."""
    source = read_split(content)
    for key, ids in source.items():
        if len(ids) != len(set(ids)):
            raise ValueError(f'Duplicate {key} patient')
        if any(len(p) != 12 or not p.startswith('TCGA-') for p in ids):
            raise ValueError('Expected patient IDs, not slide IDs')
    if set(source['train']) & set(source['val']):
        raise ValueError('Author source has same-fold overlap')
    if not cohort <= set(source['train']) | set(source['val']):
        raise ValueError('Author source does not cover the frozen cohort')
    selected = {k: [p for p in ids if p in cohort] for k, ids in source.items()}
    if not all(selected.values()):
        raise ValueError('Empty partition after filtering')
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['', 'train', 'val'])
    for index, (train, val) in enumerate(zip_longest(selected['train'], selected['val'], fillvalue='')):
        writer.writerow([index, train, val])
    return stream.getvalue()


def original(cohort, fold, model='survpath'):
    repo, commit = SOURCES[model]
    return subprocess.check_output([
        'git', '-C', str(ROOT / repo), 'show',
        f'{commit}:splits/5foldcv/tcga_{cohort}/splits_{fold}.csv'])


def frozen_cohort(cohort):
    old = ROOT / 'splits' / ARCHIVE / 'project' / f'tcga_{cohort}'
    union = set()
    for fold in range(5):
        split = read_split((old / f'splits_{fold}.csv').read_text())
        union.update(split['train'] + split['val'])
    meta = rows(ROOT / f'datasets_csv/metadata/tcga_{cohort}.csv')
    rna = rows(ROOT / f'datasets_csv/raw_rna_data/combine/{cohort}/rna_clean.csv')
    return union & {r['case_id'] for r in meta} & {r[next(iter(r))] for r in rna}


def audit():
    manifest = json.loads((ROOT / 'splits' / VERSION / 'manifest.json').read_text())
    for relative, digest in manifest['unchanged_sha256'].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Protected input or backup changed: {relative}')
    report = {}
    for cohort, expected in [('blca', 357), ('brca', 868)]:
        ids = frozen_cohort(cohort)
        assert len(ids) == expected
        assert sorted(ids) == manifest['cohorts'][cohort]['patient_ids']
        validation, folds = [], []
        for fold in range(5):
            raw = original(cohort, fold)
            assert read_split(raw.decode()) == read_split(original(cohort, fold, 'pibd').decode())
            clean = filtered_split(raw.decode(), ids).encode()
            paths = [ROOT / f'splits/{VERSION}/tcga_{cohort}/splits_{fold}.csv',
                     ROOT / f'splits/5folds/tcga_{cohort}/splits_{fold}.csv']
            paths += [ROOT / repo / f'splits/5foldcv/tcga_{cohort}/splits_{fold}.csv'
                      for repo, _ in SOURCES.values()]
            for path in paths:
                assert path.read_bytes() == clean, f'Author-derived split mismatch: {path}'
            split = read_split(clean.decode())
            validation.extend(split['val'])
            folds.append(dict(fold=fold, train=len(split['train']), val=len(split['val']),
                              overlapping_patients=0, sha256=hashlib.sha256(clean).hexdigest()))
        assert Counter(validation) == Counter({p: 1 for p in ids})
        meta = rows(ROOT / f'datasets_csv/metadata/tcga_{cohort}.csv')
        slides = sorted({Path(r['slide_id']).stem for r in meta if r['case_id'] in ids})
        data = ROOT / f'data/tcga_{cohort}/clam_20x_resnet50_paper_k9'
        missing = [s for s in slides if not (data / 'graph_files' / f'{s}.pt').is_file()
                   or not (data / 'hypergraph_cache' / f'{s}.pt').is_file()
                   or not any((data / sub / f'{s}{suffix}').is_file() for sub, suffix in
                              [('pt_files', '.pt'), ('h5_files', '.h5')])]
        assert not missing, f'Missing caches: {missing[:5]}'
        report[cohort] = dict(patients=len(ids), slides=len(slides), folds=folds,
                             each_patient_validated_once=True, missing_caches=missing)
    return report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
