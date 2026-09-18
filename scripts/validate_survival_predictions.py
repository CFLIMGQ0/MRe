"""Audit trusted local predictions against repository patients, DSS labels and C-index."""
import csv
import hashlib
from pathlib import Path
import pickle

import numpy as np
from sksurv.metrics import concordance_index_censored


def read_rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def scalar(value):
    return float(np.asarray(value).item())


def validate_predictions(predictions, expected_cindex, cohort, fold, root, split_path=None):
    """No model execution or writes; reject missing patients, labels or nonfinite risk."""
    root = Path(root)
    metadata = read_rows(root / f'datasets_csv/metadata/tcga_{cohort}.csv')
    rna = read_rows(root / f'datasets_csv/raw_rna_data/combine/{cohort}/rna_clean.csv')
    eligible = {r['case_id'] for r in metadata} & {r[next(iter(r))] for r in rna}
    split_path = Path(split_path) if split_path is not None else root / f'splits/5folds/tcga_{cohort}/splits_{fold}.csv'
    expected = {r['val'] for r in read_rows(split_path)
                if r['val']} & eligible
    labels = {}
    for row in metadata:
        if row['case_id'] not in expected:
            continue
        label = (float(row['survival_months_dss']), float(row['censorship_dss']))
        if row['case_id'] in labels and labels[row['case_id']] != label:
            raise ValueError(f'Conflicting metadata labels: {row["case_id"]}')
        labels[row['case_id']] = label
    # Only use for this project's trusted experiment output, never uploaded pickle files.
    with Path(predictions).open('rb') as stream:
        data = pickle.load(stream)
    if set(data) != expected:
        raise ValueError(f'Validation patient mismatch: missing={len(expected - set(data))}, '
                         f'extra={len(set(data) - expected)}')
    times, risks, censored = [], [], []
    for patient, value in data.items():
        t, c, risk = scalar(value['time']), scalar(value['censorship']), scalar(value['risk'])
        if not np.isfinite([t, c, risk]).all() or c not in (0., 1.):
            raise ValueError(f'Invalid survival prediction: {patient}')
        if not np.isclose(t, labels[patient][0], rtol=1e-6, atol=1e-5) or c != labels[patient][1]:
            raise ValueError(f'DSS label mismatch: {patient}')
        times.append(t)
        censored.append(c)
        risks.append(risk)
    value = float(concordance_index_censored(
        (1 - np.asarray(censored)).astype(bool), np.asarray(times), np.asarray(risks),
        tied_tol=1e-8)[0])
    if not np.isfinite(expected_cindex) or abs(value - expected_cindex) > 1e-10:
        raise ValueError(f'Summary/prediction C-index mismatch: {expected_cindex} vs {value}')
    return dict(patients=len(data), patient_ids_match=True, dss_labels_match=True,
                all_risks_finite=True, recomputed_cindex=value, split_path=str(split_path),
                split_sha256=hashlib.sha256(split_path.read_bytes()).hexdigest())
