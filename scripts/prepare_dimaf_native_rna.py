#!/usr/bin/env python3
"""Download official DIMAF Xena RNA files and run its unchanged preprocessor.

Preserves compressed sources, resumes .part downloads, refuses to overwrite
prepared RNA, and does not change splits or fill missing genes/patients.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "third_party/DIMAF_20260913"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(cohort):
    pin = json.loads((ROOT / "configs/repository_baselines_20260913.json").read_text())["models"]["dimaf"]["commit"]
    head = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    if head != pin:
        raise RuntimeError("Unreviewed DIMAF commit")
    data_dir = REPO / "src/data/data_files" / f"tcga_{cohort}" / "rna"
    prepared = data_dir / "rna_data.csv"
    if prepared.exists():
        raise FileExistsError(f"Prepared RNA already exists; preserved without overwrite: {prepared}")
    data_dir.mkdir(parents=True, exist_ok=True)
    source = data_dir / f"HiSeqV2_PANCAN_{cohort.upper()}.gz"
    url = f"https://tcga-xena-hub.s3.us-east-1.amazonaws.com/download/TCGA.{cohort.upper()}.sampleMap%2FHiSeqV2_PANCAN.gz"
    if not source.exists():
        partial = source.with_suffix(".gz.part")
        env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
        env["NO_PROXY"] = "*"
        # System curl must not load Conda's incompatible libffi/libstdc++.
        env.pop("LD_LIBRARY_PATH", None)
        subprocess.run(["curl", "--fail", "--location", "--continue-at", "-", "--connect-timeout", "10",
                        "--max-time", "300", "--retry", "1", "--output", str(partial), url], env=env, check=True)
        partial.rename(source)
    raw = source.with_suffix("")
    if not raw.exists():
        partial_raw = raw.with_suffix(".unpacking")
        with gzip.open(source, "rb") as src, partial_raw.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        partial_raw.rename(raw)
    command = [sys.executable, "preprocess_TCGA_rna.py", "--data", cohort, "--name", "rna_data"]
    subprocess.run(command, cwd=REPO / "src/data", check=True)
    import pandas as pd
    rna = pd.read_csv(prepared, index_col=0)
    patient_ids = set(rna["Unnamed: 0"].astype(str))
    expected = set()
    for fold in range(5):
        for part in ("train", "test"):
            frame = pd.read_csv(data_dir.parent / f"splits/{fold}/{part}.csv", usecols=["case_id"])
            expected.update(frame.case_id.astype(str))
    audit = dict(cohort=cohort, source_url=url, repository_commit=head, source_sha256=sha256(source),
                 prepared_sha256=sha256(prepared), shape=list(rna.shape), native_command=command,
                 expected_patients=len(expected), prepared_unique_patients=len(patient_ids),
                 missing_patients=sorted(expected - patient_ids), duplicate_patients=int(rna["Unnamed: 0"].duplicated().sum()))
    (data_dir / "preparation_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2), flush=True)
    if audit["missing_patients"] or audit["duplicate_patients"]:
        raise RuntimeError("Native RNA output fails patient coverage audit; no rows fabricated or dropped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", nargs="+", choices=["blca", "brca", "luad", "kirc"], default=["blca", "brca"])
    args = parser.parse_args()
    for cohort in args.cohort:
        prepare(cohort)
