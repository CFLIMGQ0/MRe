#!/usr/bin/env python3
"""Build a separate public BLCA WSI/RNA/DSS cohort without touching old splits.

prepare freezes public sources and patient membership; download retrieves only
missing raw slides; preprocess encodes those slides; audit validates every selected
feature/graph/cache. No model
training, split generation, deletion, or modification of historical inputs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / 'data/tcga_blca/public_dss_20260914'
OLD_DATA = ROOT / 'data/tcga_blca/clam_20x_resnet50_paper_k9'
OLD_RAW = Path('/xmlg/Lim/MRePath_GDC/raw_svs/tcga_blca')
RNA_SOURCE = ROOT / 'third_party/DIMAF_20260913/src/data/data_files/tcga_blca/rna/HiSeqV2_PANCAN_BLCA'
CDR_URL = 'https://api.gdc.cancer.gov/data/1b5f413e-a8d1-4d10-92eb-7c4ae739ed81'
RNA_URL = 'https://tcga-xena-hub.s3.us-east-1.amazonaws.com/download/TCGA.BLCA.sampleMap%2FHiSeqV2_PANCAN.gz'


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def frozen(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f'Refusing to overwrite frozen artifact: {path}')
        return
    part = path.with_name(path.name + '.partial')
    part.write_bytes(payload)
    part.replace(path)


def freeze_json(path, value):
    frozen(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def report(path, value):
    part = path.with_name(path.name + f'.{os.getpid()}.partial')
    part.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    part.replace(path)


def link(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() != source.resolve():
            raise RuntimeError(f'Conflicting symlink: {destination}')
    elif destination.exists():
        raise RuntimeError(f'Refusing to replace existing path: {destination}')
    else:
        destination.symlink_to(source.resolve())


def space_guard(output, extra=0):
    from run_hnsc_blca_bernoulli_kan import remaining_download_bytes
    manifest = ROOT / 'gdc_download/manifests/brca_split_20260913/host204_data/tcga_brca_fixed_folds_dx.tsv'
    remaining = remaining_download_bytes(manifest, Path('/xmlg/Lim/MRePath_GDC/raw_svs/tcga_brca'))
    if shutil.disk_usage(output).free - remaining - extra < 70 * 2**30:
        raise RuntimeError('Disk guard: preserve remaining BRCA download plus 70 GiB')


def request(url):
    # Bypass both environment and desktop proxies, including for redirect hops.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(urllib.request.Request(url, headers={'User-Agent': 'BLCA-cohort-audit/1.0'}), timeout=45)


def protected_files():
    paths = [ROOT / 'model.yaml', ROOT / 'datasets_csv/metadata/tcga_blca.csv',
             ROOT / 'datasets_csv/clinical_data/tcga_blca_clinical.csv',
             ROOT / 'datasets_csv/raw_rna_data/combine/blca/rna_clean.csv',
             *sorted((ROOT / 'splits/5folds/tcga_blca').glob('splits_*.csv'))]
    return {str(p): digest(p) for p in paths}


def select_patients(slides, primary_samples, clinical):
    """Return membership independently of any pre-existing split or metadata."""
    import pandas as pd
    by_patient = {}
    for sample in primary_samples:
        if len(sample) >= 15 and sample[13:15] == '01':
            by_patient.setdefault(sample[:12], []).append(sample)
    if any(len(v) != 1 for v in by_patient.values()):
        raise RuntimeError('Ambiguous primary RNA samples: explicit selection policy required')
    b = clinical.loc[clinical['type'] == 'BLCA'].copy()
    if b.bcr_patient_barcode.duplicated().any():
        raise RuntimeError('Duplicate BLCA clinical patients')
    b = b.set_index('bcr_patient_barcode')
    rows = []
    for patient in sorted({x['case_id'] for x in slides}):
        reasons = []
        sample = by_patient.get(patient, [''])[0]
        if not sample:
            reasons.append('no_primary_tumor_RNA')
        if patient not in b.index:
            reasons.append('no_CDR_BLCA_record')
        else:
            c = b.loc[patient]
            event = pd.to_numeric(c['DSS'], errors='coerce')
            days = pd.to_numeric(c['DSS.time'], errors='coerce')
            if event not in (0, 1) or not pd.notna(days) or not 0 < days < float('inf'):
                reasons.append('invalid_DSS_or_nonpositive_followup')
            if pd.notna(c['Redaction']) and str(c['Redaction']).strip():
                reasons.append('CDR_redacted')
        rows.append(dict(case_id=patient, selected=not reasons, reason=';'.join(reasons), rna_sample_id=sample))
    return rows, b


def prepare(output):
    import numpy as np
    import pandas as pd
    space_guard(output, 512 * 1024**2)
    source = output / 'sources'
    source.mkdir(exist_ok=True)
    freeze_json(source / 'historical_inputs_sha256.json', protected_files())
    api_file = source / 'gdc_open_slide_files.json'
    if not api_file.exists():
        filters = {'op': 'and', 'content': [
            {'op': 'in', 'content': {'field': f, 'value': v}} for f, v in [
                ('cases.project.project_id', ['TCGA-BLCA']), ('data_type', ['Slide Image']), ('access', ['open'])]]}
        query = urllib.parse.urlencode(dict(filters=json.dumps(filters), size=10000,
            fields='file_id,file_name,file_size,md5sum,state,access,cases.submitter_id'))
        with request('https://api.gdc.cancer.gov/files?' + query) as response:
            payload = json.load(response)
        if len(payload['data']['hits']) != payload['data']['pagination']['total']:
            raise RuntimeError('Truncated GDC response')
        freeze_json(api_file, payload)
    cdr = source / 'TCGA-CDR-SupplementalTableS1.xlsx'
    if not cdr.exists():
        with request(CDR_URL) as response:
            frozen(cdr, response.read())
    clinical = pd.read_excel(cdr, sheet_name='TCGA-CDR')
    raw = pd.read_csv(RNA_SOURCE, sep='\t', index_col=0)
    if raw.index.duplicated().any():
        raise RuntimeError('Duplicate RNA gene symbols')
    slides = []
    for h in json.loads(api_file.read_text())['data']['hits']:
        if not re.search(r'-DX[0-9A-Z]?(?:\.|-)', h['file_name'], re.I):
            continue
        patient = '-'.join(h['file_name'].split('-')[:3])
        if patient not in {c['submitter_id'] for c in h['cases']}:
            raise RuntimeError('Slide filename and GDC patient disagree')
        if h['state'] != 'released' or h['access'] != 'open':
            raise RuntimeError('Non-released/non-open diagnostic slide')
        slides.append(dict(case_id=patient, id=h['file_id'], filename=h['file_name'],
                           size=int(h['file_size']), md5=h['md5sum'], state=h['state']))
    slides.sort(key=lambda x: (x['case_id'], x['filename']))
    membership, b = select_patients(slides, raw.columns, clinical)
    selected = {r['case_id']: r['rna_sample_id'] for r in membership if r['selected']}
    if not selected:
        raise RuntimeError('Empty cohort')
    frozen(output / 'membership.csv', pd.DataFrame(membership).to_csv(index=False).encode())
    matrix = raw.loc[:, list(selected.values())].T.copy()
    matrix.index = list(selected)
    matrix.index.name = None
    if not np.isfinite(matrix.to_numpy(dtype=float)).all():
        raise RuntimeError('Missing/non-finite RNA; no imputation permitted')
    frozen(output / 'rna/rna_clean.csv', matrix.to_csv().encode())
    old = pd.read_csv(ROOT / 'datasets_csv/metadata/tcga_blca.csv', index_col=0)
    old_cases = set(old.case_id)
    old_split_cases = set()
    for path in (ROOT / 'splits/5folds/tcga_blca').glob('splits_*.csv'):
        s = pd.read_csv(path)
        old_split_cases.update(s['train'].dropna())
        old_split_cases.update(s['val'].dropna())
    missing = []
    metadata = []
    patient_rows = []
    selected_slides = [s for s in slides if s['case_id'] in selected]
    for s in selected_slides:
        patient = s['case_id']
        c = b.loc[patient]
        row = dict(case_id=patient, slide_id=s['filename'], age=c.age_at_initial_pathologic_diagnosis,
                   site=patient.split('-')[1], is_female=1 if str(c.gender).upper() == 'FEMALE' else
                   0 if str(c.gender).upper() == 'MALE' else np.nan, oncotree_code='BLCA', train=np.nan)
        for endpoint, suffix in [('OS', ''), ('DSS', '_dss'), ('PFI', '_pfi')]:
            row['survival_months' + suffix] = pd.to_numeric(c[endpoint + '.time'], errors='coerce') / 30.0
            row['censorship' + suffix] = 1.0 - pd.to_numeric(c[endpoint], errors='coerce')
        metadata.append(row)
        raw_path = OLD_RAW / s['id'] / s['filename']
        if not raw_path.is_file() or raw_path.stat().st_size != s['size']:
            s['raw_path'] = str(output / 'raw_new' / s['id'] / s['filename'])
            missing.append(s)
        else:
            s['raw_path'] = str(raw_path)
        for sub, suffix in [('patches', '.h5'), ('h5_files', '.h5'), ('graph_files', '.pt'),
                            ('hypergraph_cache', '.pt'), ('masks', '.jpg')]:
            name = Path(s['filename']).stem + suffix
            prior = OLD_DATA / sub / name
            if prior.is_file():
                link(prior, output / 'features' / sub / name)
    for patient, sample in selected.items():
        c = b.loc[patient]
        patient_rows.append(dict(case_id=patient, rna_sample_id=sample,
            dss_event=int(c.DSS), dss_days=float(c['DSS.time']),
            wsi_count=sum(s['case_id'] == patient for s in selected_slides),
            in_old_metadata=patient in old_cases, in_old_splits=patient in old_split_cases))
    clinical_rows = [dict(case_id=p, stage=str(b.loc[p, 'ajcc_pathologic_tumor_stage']).removeprefix('Stage ')
                          if pd.notna(b.loc[p, 'ajcc_pathologic_tumor_stage']) else 'N/A',
                          grade=b.loc[p, 'histological_grade'], subtype='BLCA') for p in selected]
    frozen(output / 'clinical/tcga_blca_clinical.csv', pd.DataFrame(clinical_rows).to_csv().encode())
    frame = pd.DataFrame(metadata).reindex(columns=old.columns)
    frozen(output / 'metadata/tcga_blca.csv', frame.to_csv().encode())
    frozen(output / 'patients.csv', pd.DataFrame(patient_rows).to_csv(index=False).encode())
    freeze_json(output / 'slides.json', selected_slides)
    freeze_json(output / 'missing_raw_slides.json', missing)
    frozen(output / 'missing_raw_manifest.tsv', pd.DataFrame(missing).reindex(
        columns=['id', 'filename', 'md5', 'size', 'state']).to_csv(index=False, sep='\t').encode())
    old_rna = pd.read_csv(ROOT / 'datasets_csv/raw_rna_data/combine/blca/rna_clean.csv', index_col=0)
    shared_genes = sorted(set(old_rna.columns) & set(matrix.columns))
    shared_cases = sorted(set(old_rna.index) & set(matrix.index))
    delta = old_rna.loc[shared_cases, shared_genes].to_numpy() - matrix.loc[shared_cases, shared_genes].to_numpy()
    manifest = dict(cohort='BLCA public diagnostic WSI + primary RNA + DSS',
        candidates=len(selected), selected_slides=len(selected_slides), public_dx_patients=len(membership),
        missing_raw_slides=len(missing), missing_raw_bytes=sum(s['size'] for s in missing),
        redacted_excluded=[r['case_id'] for r in membership if 'CDR_redacted' in r['reason']],
        added_vs_old_metadata=sorted(set(selected) - old_cases),
        excluded_old_metadata=sorted(old_cases - set(selected)),
        old_metadata_missing_from_old_splits=sorted((old_cases & set(selected)) - old_split_cases),
        rna=dict(source=str(RNA_SOURCE), url=RNA_URL, sha256=digest(RNA_SOURCE), genes=len(matrix.columns),
                 transform='Transpose only; primary tumor -01; unchanged Xena HiSeqV2_PANCAN values; no imputation, gene selection, log transform or cohort scaler',
                 historical_matrix_genes=len(old_rna.columns), shared_genes=len(shared_genes),
                 historical_mean_absolute_difference=float(np.abs(delta).mean())),
        cdr=dict(url=CDR_URL, sha256=digest(cdr), endpoint='DSS', followup_rule='finite days > 0',
                 censorship='1 - DSS event', days_to_months_divisor=30),
        features=dict(root=str(output / 'features'), encoder='ImageNet truncated ResNet50',
                      magnification='20x', target_patch_size=256, dimension=1024, dtype='float32', k=9),
        splits='NOT GENERATED. Old splits remain unchanged and must not be reused as a complete new-cohort split.',
        original_models_unchanged=True)
    freeze_json(output / 'cohort_manifest.json', manifest)
    report(output / 'status.json', dict(state='prepared_not_yet_verified', at=time.time(), **manifest))
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


def download(output):
    slides = json.loads((output / 'missing_raw_slides.json').read_text())
    space_guard(output, sum(x['size'] for x in slides))
    def one(s):
        target = Path(s['raw_path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.stat().st_size == s['size'] and digest(target, 'md5') == s['md5']:
                return dict(id=s['id'], path=str(target), state='already_md5_verified')
            raise RuntimeError(f'Existing target differs; preserved: {target}')
        part = target.with_name(target.name + '.part')
        # Each file is small here. Retain failed partials and use a new attempt file.
        for attempt in range(3):
            attempt_path = part.with_name(part.name + f'.attempt_{time.time_ns()}')
            try:
                with request('https://api.gdc.cancer.gov/data/' + s['id']) as src, attempt_path.open('xb') as dst:
                    total = 0
                    while block := src.read(4 * 1024**2):
                        total += len(block)
                        if total > s['size']:
                            raise RuntimeError('Download exceeds manifest size')
                        dst.write(block)
                if total != s['size'] or digest(attempt_path, 'md5') != s['md5']:
                    raise RuntimeError('Download size/MD5 mismatch')
                attempt_path.replace(target)
                return dict(id=s['id'], path=str(target), state='downloaded_md5_verified', bytes=total)
            except Exception:
                if attempt == 2:
                    raise
        raise AssertionError('unreachable')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(one, slides))
    report(output / 'download_audit.json', dict(at=time.time(), direct_connection=True, files=results))
    print(json.dumps(results, indent=2), flush=True)


def preprocess(output):
    """Encode only new raw files; never write through historical cache symlinks."""
    space_guard(output, 1024**3)
    slides = json.loads((output / 'missing_raw_slides.json').read_text())
    if not slides:
        print('No new raw slides to encode', flush=True)
        return
    for s in slides:
        raw = Path(s['raw_path'])
        if not raw.is_relative_to(output / 'raw_new') or digest(raw, 'md5') != s['md5']:
            raise RuntimeError(f'New raw input failed path/MD5 validation: {raw}')
        for sub, extension in [('patches', '.h5'), ('h5_files', '.h5'), ('masks', '.jpg'),
                               ('graph_files', '.pt'), ('hypergraph_cache', '.pt')]:
            target = output / 'features' / sub / (raw.stem + extension)
            if target.is_symlink():
                raise RuntimeError(f'Refusing to process a historical symlink: {target}')
    log_dir = output / 'logs'
    log_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', OMP_NUM_THREADS='4',
               MKL_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4', NUMEXPR_NUM_THREADS='4',
               TORCH_HOME=str(OLD_DATA / 'torch_cache'))
    for key in list(env):
        if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
            env.pop(key)
    base = [sys.executable, str(ROOT / 'scripts/preprocess_wsi_clam.py'),
            '--source', str(output / 'raw_new'), '--output', str(output / 'features'),
            '--patch-mode', 'true-20x']
    with (log_dir / 'inventory.log').open('a') as log:
        subprocess.run(base + ['--inventory-only'], cwd=ROOT, env=env,
                       stdout=log, stderr=subprocess.STDOUT, check=True)

    def encode(item):
        index, slide = item
        worker_env = dict(env, CUDA_VISIBLE_DEVICES=str(index % 2))
        command = base + ['--skip-inventory', '--slide-id', slide['filename'],
                          '--status-file', f'new_slide_{index}.csv', '--batch-size', '256',
                          '--workers', '4', '--device', 'cuda', '--fail-fast']
        print(f"[encode] GPU {index % 2}: {slide['case_id']}", flush=True)
        with (log_dir / f'encode_{index}.log').open('a') as log:
            subprocess.run(command, cwd=ROOT, env=worker_env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        print(f"[encode] complete: {slide['case_id']}", flush=True)
    report(output / 'status.json', dict(state='encoding_new_slides', at=time.time(), slides=len(slides)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(encode, enumerate(slides)))
    # The original graph builder has one shared status CSV, so serialize it.
    for index, slide in enumerate(slides):
        with (log_dir / f'graph_{index}.log').open('a') as log:
            subprocess.run([sys.executable, str(ROOT / 'scripts/build_wsi_graphs.py'),
                '--h5-dir', str(output / 'features/h5_files'),
                '--output-dir', str(output / 'features/graph_files'),
                '--metadata-csv', str(output / 'metadata/tcga_blca.csv'),
                '--slide-id', Path(slide['filename']).stem, '--radius', '9', '--feature-dim', '1024',
                '--spatial-space', 'l2', '--feature-space', 'cosinesimil',
                '--verify-existing', '--fail-fast'], cwd=ROOT, env=env,
                stdout=log, stderr=subprocess.STDOUT, check=True)
    from build_hypergraph_cache import build_one
    results = [build_one(output / 'features/graph_files' / (Path(s['filename']).stem + '.pt'),
                         output / 'features/hypergraph_cache') for s in slides]
    report(output / 'preprocessing_audit.json', dict(at=time.time(), slides=results,
                                                   historical_caches_written=False))
    print(json.dumps(results, indent=2), flush=True)


def loader_smoke(output, patients, rna):
    """Check original loader I/O in an isolated working directory, without training."""
    import torch
    from datasets.dataset_survival import SurvivalDatasetFactory, SurvivalDataset
    runtime = output / 'runtime'
    link(ROOT / 'datasets_csv/metadata/signatures.csv', runtime / 'datasets_csv/metadata/signatures.csv')
    link(output / 'clinical/tcga_blca_clinical.csv',
         runtime / 'datasets_csv/clinical_data/tcga_blca_clinical.csv')
    previous_cwd = Path.cwd()
    try:
        os.chdir(runtime)
        factory = SurvivalDatasetFactory(study='tcga_blca',
            label_file=str(output / 'metadata/tcga_blca.csv'), omics_dir=str(output / 'rna'),
            seed=1, print_info=False, n_bins=4, label_col='survival_months_dss',
            is_mcat=True, is_survpath=False)
    finally:
        os.chdir(previous_cwd)
    assert len(factory) == len(patients) == len(factory.all_modalities['rna'])
    assert set(factory.patient_dict) == set(patients.case_id)
    assert len(factory.omic_sizes) == 6 and min(factory.omic_sizes) > 0
    raw_omics = rna.assign(temp_index=rna.index).reset_index(drop=True)
    dataset = SurvivalDataset(split_key='audit_only', fold=-1, study_name='tcga_blca',
        modality='hgnn', patient_dict=factory.patient_dict, metadata=factory.label_data,
        omics_data_dict={'rna': raw_omics}, data_dir=str(output / 'features'),
        num_classes=factory.num_classes, label_col='survival_months_dss', censorship_var='censorship_dss',
        is_training=False, clinical_data=factory.clinical_data.set_index('case_id'),
        num_patches=4096, omic_names=factory.omic_names, sample=False,
        hypergraph_cache_dir=str(output / 'features/hypergraph_cache'))
    targets = sorted(set(patients.loc[~patients.in_old_splits | ~patients.in_old_metadata, 'case_id']) |
                     set(patients.loc[patients.wsi_count > 1, 'case_id'].head(1)))
    records = []
    for patient in targets:
        index = factory.label_data.index[factory.label_data.case_id == patient].item()
        item = dataset[index]
        assert item[0].shape[1] == 1024 and item[0].shape[0] > 0 and torch.isfinite(item[0]).all()
        assert all(t.ndim == 1 and t.numel() == size and torch.isfinite(t).all()
                   for t, size in zip(item[2:8], factory.omic_sizes))
        records.append(dict(case_id=patient, sampled_patch_shape=list(item[0].shape),
                            slides=len(factory.patient_dict[patient])))
    result = dict(patients_loaded=len(factory), six_group_sizes=factory.omic_sizes,
        tested_patients=records, training_run=False, split_created=False,
        note='I/O smoke only: raw source RNA; no fold scaler fit, no optimizer, no model forward; '
             'factory temporary bins are not saved or used for training.')
    report(output / 'loader_smoke.json', result)
    return result


def verify_sources(output):
    """Round-trip the new RNA and DSS labels against the frozen public sources."""
    import numpy as np
    import pandas as pd
    manifest = json.loads((output / 'cohort_manifest.json').read_text())
    cdr_path = output / 'sources/TCGA-CDR-SupplementalTableS1.xlsx'
    assert digest(RNA_SOURCE) == manifest['rna']['sha256'], 'RNA source changed'
    assert digest(cdr_path) == manifest['cdr']['sha256'], 'CDR source changed'
    patients = pd.read_csv(output / 'patients.csv')
    matrix = pd.read_csv(output / 'rna/rna_clean.csv', index_col=0)
    raw = pd.read_csv(RNA_SOURCE, sep='\t', index_col=0)
    reference = raw.loc[matrix.columns, patients.rna_sample_id].T.to_numpy()
    delta = np.abs(matrix.loc[patients.case_id].to_numpy() - reference)
    assert float(delta.max()) < 1e-12, 'RNA output and public source values differ'
    clinical = pd.read_excel(cdr_path, sheet_name='TCGA-CDR').set_index('bcr_patient_barcode')
    selected = clinical.loc[patients.case_id]
    assert selected.type.eq('BLCA').all() and selected.Redaction.isna().all()
    assert np.array_equal(patients.dss_event.to_numpy(), selected.DSS.to_numpy())
    assert np.array_equal(patients.dss_days.to_numpy(), selected['DSS.time'].to_numpy())
    metadata = pd.read_csv(output / 'metadata/tcga_blca.csv')
    for patient, rows in metadata.groupby('case_id'):
        assert np.allclose(rows.survival_months_dss, clinical.loc[patient, 'DSS.time'] / 30,
                           rtol=0, atol=1e-12)
        assert rows.censorship_dss.eq(1 - clinical.loc[patient, 'DSS']).all()
        assert all(slide.startswith(patient + '-') for slide in rows.slide_id)
    result = dict(patients=len(patients), genes=len(matrix.columns),
                  maximum_rna_roundtrip_absolute_error=float(delta.max()),
                  source_hashes_match=True, dss_labels_match=True, all_nonredacted=True)
    report(output / 'source_alignment_audit.json', result)
    return result


def audit(output):
    import numpy as np
    import pandas as pd
    import torch
    import h5py
    sys.path.insert(0, str(ROOT))
    from utils.hypergraph_cache import cache_matches, load_cache_record
    from build_wsi_graphs import validate_graph
    verify_sources(output)
    patients = pd.read_csv(output / 'patients.csv')
    metadata = pd.read_csv(output / 'metadata/tcga_blca.csv', index_col=0)
    rna = pd.read_csv(output / 'rna/rna_clean.csv', index_col=0)
    clinical = pd.read_csv(output / 'clinical/tcga_blca_clinical.csv', index_col=0)
    ids = set(patients.case_id)
    assert ids == set(metadata.case_id) == set(rna.index) == set(clinical.case_id)
    assert not patients.case_id.duplicated().any() and not rna.index.duplicated().any()
    assert np.isfinite(rna.to_numpy()).all()
    assert np.isfinite(metadata.survival_months_dss).all() and (metadata.survival_months_dss > 0).all()
    assert metadata.censorship_dss.isin([0, 1]).all()
    frozen_hashes = json.loads((output / 'sources/historical_inputs_sha256.json').read_text())
    assert frozen_hashes == protected_files(), 'Historical inputs changed'
    slides = json.loads((output / 'slides.json').read_text())
    assert ids == {s['case_id'] for s in slides}, 'Manifest patient coverage mismatch'
    assert len(slides) == len({s['filename'] for s in slides}) == len(metadata)
    assert set(metadata.slide_id) == {s['filename'] for s in slides}
    report(output / 'status.json', dict(state='auditing', at=time.time(),
                                       candidate_patients=len(ids), selected_slides=len(slides)))
    verified, failures = [], []
    for s in slides:
        stem = Path(s['filename']).stem
        try:
            source = Path(s['raw_path'])
            assert source.is_file() and source.stat().st_size == s['size'], 'Raw slide missing/size mismatch'
            graph_path = output / 'features/graph_files' / (stem + '.pt')
            with h5py.File(output / 'features/h5_files' / (stem + '.h5'), 'r') as h:
                x, coords = h['features'], h['coords']
                n = x.shape[0]
                assert n >= 9 and x.shape == (n, 1024) and x.dtype == np.float32
                assert coords.shape == (n, 2)
                graph = torch.load(graph_path, map_location='cpu', weights_only=False, mmap=True)
                assert tuple(graph.x.shape) == (n, 1024)
                assert np.array_equal(coords[:], graph.centroid.numpy()), 'Graph/HDF5 coordinate mismatch'
                with h5py.File(output / 'features/patches' / (stem + '.h5'), 'r') as patches:
                    assert np.array_equal(patches['coords'][:], coords[:]), 'Patch/HDF5 coordinate mismatch'
                for start in range(0, n, 8192):
                    block = x[start:start + 8192]
                    assert np.isfinite(block).all(), 'Nonfinite patch feature'
                    assert np.array_equal(block, graph.x[start:start + 8192].numpy()), 'Graph/HDF5 feature mismatch'
            validate_graph(graph_path, n, 1024, 9, 'l2', 'cosinesimil')
            cache = load_cache_record(graph_path, output / 'features/hypergraph_cache')
            assert cache['num_nodes'] == n and cache_matches(cache, graph_path)
            assert cache['hyperedge_size'] == 9
            for name in ('topology', 'feature'):
                centers, incidence = cache[name]['centers'], cache[name]['incidence']
                assert centers.shape == (n,) and torch.equal(centers, torch.arange(n))
                assert incidence.ndim == 2 and incidence.shape[0] == 2 and incidence.shape[1] > 0
                assert int(incidence.min()) >= 0 and int(incidence.max()) < n
            verified.append(dict(case_id=s['case_id'], slide_id=stem, patches=n,
                                 reused=(output / 'features/h5_files' / (stem + '.h5')).is_symlink()))
        except Exception as exc:
            failures.append(dict(case_id=s['case_id'], slide_id=stem, error=repr(exc)))
        if (len(verified) + len(failures)) % 50 == 0:
            print(f'[audit] {len(verified)} slides passed, {len(failures)} failed', flush=True)
    failed_ids = {x['case_id'] for x in failures}
    valid_ids = ids - failed_ids
    smoke = loader_smoke(output, patients, rna) if not failures else None
    assert frozen_hashes == protected_files(), 'Historical inputs changed during audit'
    result = dict(at=time.time(), candidate_patients=len(ids), verified_patients=len(valid_ids),
        verified_slides=len(verified), total_cached_patches=sum(x['patches'] for x in verified),
        reused_slides=sum(x['reused'] for x in verified), newly_encoded_slides=sum(not x['reused'] for x in verified),
        rna_shape=list(rna.shape), old_inputs_unchanged=True, split_created=False, failures=failures,
        loader_patients=None if smoke is None else smoke['patients_loaded'],
        raw_validation='All selected files: presence and GDC size; newly downloaded files: size and MD5',
        quality_scope='Automated nonempty tissue/finite feature, graph and hypergraph validation; not pathologist review',
        slides=verified)
    report(output / 'final_audit.json', result)
    report(output / 'status.json', dict(state='complete' if not failures else 'incomplete',
        at=time.time(), candidate_patients=len(ids), final_patients=len(valid_ids), failed_slides=len(failures)))
    print(json.dumps({k: v for k, v in result.items() if k != 'slides'}, ensure_ascii=False, indent=2), flush=True)
    if failures:
        raise RuntimeError('Cohort incomplete; failed patients not silently removed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'download', 'preprocess', 'audit'])
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'preparation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        {'prepare': prepare, 'download': download, 'preprocess': preprocess, 'audit': audit}[args.stage](output)


if __name__ == '__main__':
    main()
