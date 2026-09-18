#!/usr/bin/env python3
"""Preflight and launch the PINNED OFFICIAL entrypoints, not rewritten models.

Default is read-only planning. --execute requires complete native data, an
explicit feature-provenance manifest, an idle GPU and a new output directory.
No missing slide is filled, no patient/fold is dropped, no split is generated.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/repository_baselines_20260913.json"


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", choices=["ld_cvae", "dimaf", "slotspe"], required=True)
    p.add_argument("--cohort", default="brca")
    p.add_argument("--data-root", type=Path, help="SlotSPE metadata root / DIMAF native cohort root")
    p.add_argument("--wsi-root", type=Path, help="LD-CVAE: parent of pt_files; SlotSPE: pt_files directory")
    p.add_argument("--feature-manifest", type=Path, help="JSON: encoder, feature_dim, feature_dir, provenance")
    p.add_argument("--evaluation", choices=["full", "missing"], default="full")
    p.add_argument("--ld-backbone", choices=["mcat", "survpath"], default="mcat")
    p.add_argument("--stage", choices=["train", "prototypes"], default="train")
    p.add_argument("--output", type=Path, help="NEW run directory, required with --execute")
    p.add_argument("--gpu", help="Single physical GPU index; no implicit sharing")
    p.add_argument("--execute", action="store_true")
    return p


def build_plan(args):
    import pandas as pd
    cfg = json.loads(CONFIG.read_text())["models"][args.model]
    repo = ROOT / cfg["directory"]
    problems, required = [], []
    cohort = args.cohort.lower()
    if cohort not in cfg["packaged_cohorts"]:
        problems.append(f"{cohort} has no packaged native cohort/splits in this repository; no new split will be invented")
    if args.stage == "prototypes" and args.model != "dimaf":
        problems.append("Prototype stage belongs to DIMAF only")
    if args.model == "dimaf" and args.evaluation != "full":
        problems.append("DIMAF entrypoint has no missing-modality evaluation flag")
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if revision != cfg["commit"]:
        problems.append(f"Repository revision changed: {revision}")
    diff = subprocess.check_output(["git", "-C", str(repo), "diff", "--no-ext-diff"], text=True)
    output = args.output.resolve() if args.output else ROOT / "results/NEW_OFFICIAL_RUN_REQUIRED"
    if args.output and output.exists():
        problems.append(f"Output already exists; overwriting is forbidden: {output}")
    entry = repo / cfg["entrypoint"]
    cwd = entry.parent
    command = [sys.executable, str(entry)]
    gpu = args.gpu if args.gpu is not None else "GPU_REQUIRED"
    slides = set()

    if args.model == "ld_cvae":
        if args.data_root:
            problems.append("LD-CVAE uses packaged metadata; --data-root is not an upstream argument")
        data = repo / "dataset_csv" / f"tcga_{cohort}_all_clean.csv.zip"
        folds = [repo / "splits/5foldcv" / f"tcga_{cohort}" / f"splits_{i}.csv" for i in range(5)]
        required.extend([data, repo / "datasets_csv_sig/signatures.csv", *folds])
        wsi = args.wsi_root.resolve() if args.wsi_root else ROOT / "MISSING_CTRANS_PATH_FEATURES"
        feature_dir = wsi / "pt_files"
        if data.is_file() and all(f.is_file() for f in folds):
            # Read metadata only; leave the native RNA preprocessing to the repository.
            df = pd.read_csv(data, usecols=["case_id", "slide_id"])
            # Reuse the repository's own fixed slide exclusion list verbatim.
            # Without it the guard would require slides the official loader never uses.
            source_tree = ast.parse((repo / "dataset/dataset_survival.py").read_text())
            for node in ast.walk(source_tree):
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "missing_slides_ls" for t in node.targets):
                    excluded = ast.literal_eval(node.value)
                    df = df[~df.slide_id.isin(excluded)]
                    break
            else:
                problems.append("Upstream fixed slide exclusion list could not be audited")
            patients = set()
            for fold in folds:
                split = pd.read_csv(fold)
                patients.update(split[["train", "val"]].stack().dropna().astype(str))
            slides = {str(s).rstrip(".svs") + ".pt" for s in df.loc[df.case_id.isin(patients), "slide_id"]}
        command += ["--split_dir", f"tcga_{cohort}", "--data_root_dir", str(wsi),
                    "--feature_extractor", "CTransPath", "--wsi_encoding_dim", "768",
                    "--model_type", args.ld_backbone, "--generator", "--g_condition",
                    "--missing_rate", "0.0" if args.evaluation == "full" else "1.0",
                    "--results_dir", str(output / "native_results")]
        expected_encoder, expected_dim = "CTransPath", 768
    elif args.model == "slotspe":
        data = args.data_root.resolve() if args.data_root else repo / "dataset_csv"
        clinical = data / "clinical/all" / f"{cohort}.csv"
        rna = data / "raw_rna_data_inter" / f"{cohort}_rna_inter.csv"
        folds = [data / "splits/5fold" / cohort / f"fold_{i}.csv" for i in range(5)]
        required.extend([clinical, rna, data / "signatures/combine_signatures.csv", *folds])
        feature_dir = args.wsi_root.resolve() if args.wsi_root else ROOT / "MISSING_UNI_FEATURES"
        if clinical.is_file() and all(f.is_file() for f in folds):
            df = pd.read_csv(clinical, usecols=["case id", "wsi", "survival_months_dss", "censorship_dss"]).dropna()
            patients = set()
            for fold in folds:
                split = pd.read_csv(fold)
                patients.update(split[["train", "val"]].stack().dropna().astype(str))
            df = df[df["case id"].isin(patients)]
            slides = {s.rstrip(".svs") + ".pt" for cell in df.wsi for s in cell.split(", ")}
            if rna.is_file():
                rna_patients = set(pd.read_csv(rna, nrows=0).columns[1:])
                missing_rna = set(df["case id"]) - rna_patients
                if missing_rna:
                    problems.append(f"RNA table lacks {len(missing_rna)} eligible split patients")
        command += ["--study", cohort, "--data_root_dir", str(feature_dir), "--data_path", str(data),
                    "--gpu", gpu, "--results_dir", str(output / "native_results")]
        if args.evaluation == "missing":
            command += ["--omic_missing"]
        expected_encoder, expected_dim = "UNI", 1024
    else:
        data = args.data_root.resolve() if args.data_root else repo / "src/data/data_files" / f"tcga_{cohort}"
        feature_dir = data / "wsi/extracted_res0_5_patch256_uni/feats_h5"
        if args.wsi_root and args.wsi_root.resolve() != feature_dir.resolve():
            problems.append("DIMAF uses a fixed native wsi subdirectory; prepare its native layout, do not pass another feature root")
        folds = [data / f"splits/{i}/{part}.csv" for i in range(5) for part in ("train", "test")]
        required.extend(folds)
        if args.stage == "train":
            proto = "prototypes_DIMAF/prototypes_16_type_faiss_init_3_nr_100000.pkl"
            required.extend([data / "rna/rna_data.csv", data.parent / "hallmarks_signatures.csv"])
            required.extend(data / f"splits/{i}" / proto for i in range(5))
            command += ["--data_source", str(data) + "/", "--proto_file", proto,
                        "--task", f"dss_survival_{cohort}", "--exp_code", "DIMAF",
                        "--loss_fn", "cox_distcor", "--w_dis", "7", "--w_surv", "1",
                        "--mode", "train_test", "--result_dir", str(output / "native_results"),
                        "--log_dir", str(output / "native_logs")]
        else:
            command = [sys.executable, str(repo / "src/main_prototype.py"), "--data_source", str(data) + "/",
                       "--mode", "faiss", "--n_proto", "16"]
            try:
                import faiss
                if not hasattr(faiss, "StandardGpuResources"):
                    problems.append("Native FAISS-GPU clustering needs a GPU FAISS build; CPU import/smoke build is insufficient")
            except ImportError:
                problems.append("FAISS not installed")
            for i in range(5):
                if (data / f"splits/{i}/prototypes_DIMAF").exists():
                    problems.append(f"Fold {i} already has a prototype directory; no overwrite")
        for fold in folds:
            if fold.is_file():
                slides.update(str(s) + ".h5" for s in pd.read_csv(fold, usecols=["slide_id"]).slide_id)
        expected_encoder, expected_dim = "UNI", 1024

    for path in required:
        if not path.is_file():
            problems.append(f"Missing native file: {path}")
    if not feature_dir.is_dir():
        problems.append(f"Missing native feature directory: {feature_dir}")
    missing_slides = sorted(s for s in slides if not (feature_dir / s).is_file())
    if missing_slides:
        problems.append(f"Missing {len(missing_slides)}/{len(slides)} required slide features; missing slides will NOT be replaced with zeros")
    if not slides:
        problems.append("No slide list resolved; data coverage not verified")
    provenance = None
    if args.feature_manifest and args.feature_manifest.is_file():
        provenance = json.loads(args.feature_manifest.read_text())
        if provenance.get("encoder") != expected_encoder or provenance.get("feature_dim") != expected_dim:
            problems.append(f"This native launch recipe requires {expected_encoder} / {expected_dim}; no silent encoder substitution")
        if not provenance.get("provenance") or Path(provenance.get("feature_dir", "")).resolve() != feature_dir.resolve():
            problems.append("Feature manifest needs a provenance description and matching absolute feature_dir")
    else:
        problems.append("Missing feature-provenance manifest (encoder, feature_dim, feature_dir, provenance)")
    return {"model": args.model, "cohort": cohort, "stage": args.stage,
            "repository": cfg["url"], "commit": revision, "local_diff": diff,
            "protocol": "official-native", "evaluation": args.evaluation,
            "cwd": str(cwd), "argv": command, "shell_command": shlex.join(command),
            "output": str(output), "feature_dir": str(feature_dir), "feature_dim": expected_dim,
            "feature_provenance": provenance, "required_slides": len(slides),
            "missing_slide_count": len(missing_slides), "missing_slide_examples": missing_slides[:5],
            "ready": not problems, "blockers": problems}


def execute(plan, args):
    if not plan["ready"]:
        raise RuntimeError("Native data preflight failed; see blockers")
    if args.output is None or args.gpu is None or not args.gpu.isdigit():
        raise RuntimeError("Execution requires an explicit NEW --output and a single numeric --gpu")
    # Read-only guard. Do not stop another process or share an occupied GPU.
    pids = subprocess.check_output(["nvidia-smi", f"--id={args.gpu}", "--query-compute-apps=pid",
                                    "--format=csv,noheader,nounits"], text=True).strip()
    used = int(subprocess.check_output(["nvidia-smi", f"--id={args.gpu}", "--query-gpu=memory.used",
                                       "--format=csv,noheader,nounits"], text=True).strip())
    if pids or used > 1024:
        raise RuntimeError(f"GPU {args.gpu} is occupied; no sharing or interruption")
    # Check actual tensor shape, in addition to caller-declared provenance.
    feature_dir = Path(plan["feature_dir"])
    if args.model == "dimaf":
        import h5py
        with h5py.File(next(feature_dir.glob("*.h5")), "r") as f:
            shape = f["features"].shape
    else:
        import torch
        shape = torch.load(next(feature_dir.glob("*.pt")), map_location="cpu", weights_only=True).shape
    if len(shape) != 2 or shape[0] < 1 or shape[1] != plan["feature_dim"]:
        raise RuntimeError(f"First feature shape disagrees with manifest: {shape}")
    output = Path(plan["output"])
    output.mkdir(parents=True, exist_ok=False)
    (output / "launch_manifest.json").write_text(json.dumps(plan, indent=2) + "\n")
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=args.gpu, OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
    with (output / "native_train.log").open("x") as log:
        result = subprocess.run(plan["argv"], cwd=plan["cwd"], env=env, stdout=log, stderr=subprocess.STDOUT)
    (output / "exit_status.json").write_text(json.dumps({"returncode": result.returncode}) + "\n")
    return result.returncode


def main():
    args = parser().parse_args()
    plan = build_plan(args)
    print(json.dumps(plan, indent=2, ensure_ascii=False), flush=True)
    if args.execute:
        return execute(plan, args)
    return 0 if plan["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
