#!/usr/bin/env python3
"""Run one official repository model/fold on the project's unified inputs.

The model classes and losses are imported from the pinned LD-CVAE, DIMAF and
SlotSPE checkouts.  This adapter only replaces their dataset layer so all three
models consume the same patient split, DSS endpoint and existing ResNet50
1024-D patch caches (PT, HDF5, or graph.x) without rewriting those caches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import random
import sys
import time
from types import SimpleNamespace

import h5py
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from sksurv.metrics import concordance_index_censored
from torch.utils.data import DataLoader, Dataset


ROOT = Path(__file__).resolve().parents[1]
REPOS = {
    "ld_cvae": ROOT / "third_party/LD_CVAE_20260913",
    "dimaf": ROOT / "third_party/DIMAF_20260913/src",
    "slotspe": ROOT / "third_party/SlotSPE_20260913",
}
COMMITS = {
    "ld_cvae": "df8c50d94179a63edf3d9017641295a268ce9148",
    "dimaf": "286dae63fcdc65de38224981cf345845d25c57be",
    "slotspe": "02051a2083add7b427727e0200e4263516903561",
}
COHORTS = ("blca", "brca", "coadread", "stad", "hnsc")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=tuple(REPOS), required=True)
    parser.add_argument("--cohort", choices=COHORTS, required=True)
    parser.add_argument("--fold", type=int, choices=range(5), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--max-patches", type=int, default=4096)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--smoke", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def seed_all(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def git_revision(repo: Path) -> str:
    import subprocess
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


def load_feature(path: Path) -> torch.Tensor:
    """Read one existing ResNet cache; never writes or converts it."""
    root = path.parent.parent
    if path.is_file():
        value = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    elif (root / "h5_files" / f"{path.stem}.h5").is_file():
        with h5py.File(root / "h5_files" / f"{path.stem}.h5", "r") as handle:
            value = torch.from_numpy(handle["features"][:])
    elif (root / "graph_files" / path.name).is_file():
        graph = torch.load(
            root / "graph_files" / path.name,
            map_location="cpu",
            weights_only=False,
            mmap=True,
        )
        value = graph.x
    else:
        raise FileNotFoundError(f"No PT/HDF5/graph.x cache for {path.stem}")
    value = torch.as_tensor(value)
    if value.ndim != 2 or value.shape[1] != 1024 or value.shape[0] == 0:
        raise ValueError(f"Invalid ResNet50 tensor {path}: {tuple(value.shape)}")
    if value.dtype != torch.float32:
        value = value.float()
    if not torch.isfinite(value).all():
        raise ValueError(f"Non-finite ResNet50 tensor: {path}")
    return value


def signature_groups(filename: str, genes: list[str]) -> list[list[str]]:
    frame = pd.read_csv(ROOT / "datasets_csv/metadata" / filename)
    available = set(genes)
    groups = []
    for column in frame:
        group = sorted(available.intersection(frame[column].dropna().astype(str)))
        if group:
            groups.append(group)
    if not groups:
        raise RuntimeError(f"No usable groups from {filename}")
    return groups


def training_bins(metadata: pd.DataFrame, train_ids: set[str]) -> np.ndarray:
    train = metadata[metadata.case_id.isin(train_ids)].drop_duplicates("case_id")
    events = train.loc[train.censorship_dss < 1, "survival_months_dss"].astype(float)
    if len(events) < 4:
        raise RuntimeError("Too few DSS events for four training-fold bins")
    bins = np.quantile(events, [0.0, 0.25, 0.5, 0.75, 1.0])
    bins[0] = min(float(train.survival_months_dss.min()), bins[0]) - 1e-6
    bins[-1] = max(float(train.survival_months_dss.max()), bins[-1]) + 1e-6
    for index in range(1, len(bins)):
        if bins[index] <= bins[index - 1]:
            bins[index] = np.nextafter(bins[index - 1], np.inf)
    return bins


def prepare_records(model: str, cohort: str, fold: int):
    metadata_path = ROOT / f"datasets_csv/metadata/tcga_{cohort}.csv"
    rna_path = ROOT / f"datasets_csv/raw_rna_data/combine/{cohort}/rna_clean.csv"
    split_path = ROOT / f"splits/5folds/tcga_{cohort}/splits_{fold}.csv"
    metadata = pd.read_csv(metadata_path, index_col=0)
    rna = pd.read_csv(rna_path, index_col=0)
    rna.index = rna.index.astype(str)
    rna = rna[~rna.index.duplicated(keep="first")]
    split = pd.read_csv(split_path)
    train_ids = set(split.train.dropna().astype(str))
    val_ids = set(split.val.dropna().astype(str))
    if train_ids & val_ids:
        raise RuntimeError(f"Patient overlap in active split: {len(train_ids & val_ids)}")
    usable = set(metadata.case_id.astype(str)) & set(rna.index)
    missing = (train_ids | val_ids) - usable
    # Match the project dataset factory: a split entry without both metadata
    # and RNA is ineligible for every multimodal model, and is recorded rather
    # than replaced with zeros.
    train_ids &= usable
    val_ids &= usable
    if not train_ids or not val_ids:
        raise RuntimeError("No usable train/validation patients after multimodal intersection")
    bins = training_bins(metadata, train_ids)

    if model == "ld_cvae":
        groups = signature_groups("signatures.csv", list(rna.columns))
        scaler_kind = "per_gene_standard"
    elif model == "dimaf":
        groups = signature_groups("hallmarks_signatures.csv", list(rna.columns))
        scaler_kind = "per_gene_standard"
    else:
        groups = signature_groups("combine_signatures.csv", list(rna.columns))
        scaler_kind = "none_repository_slotspe"

    selected_genes = sorted({gene for group in groups for gene in group})
    matrix = rna.loc[:, selected_genes].astype(np.float32)
    if scaler_kind == "per_gene_standard":
        scaler = StandardScaler().fit(matrix.loc[sorted(train_ids)].to_numpy())
        matrix.loc[:, :] = scaler.transform(matrix.to_numpy()).astype(np.float32)
    gene_index = {gene: idx for idx, gene in enumerate(selected_genes)}
    group_indices = [[gene_index[gene] for gene in group] for group in groups]

    base = metadata.dropna(subset=["survival_months_dss", "censorship_dss"])
    grouped = {str(case): rows for case, rows in base.groupby("case_id", sort=False)}

    def make(ids):
        records = []
        for case in sorted(ids):
            rows = grouped[case]
            first = rows.iloc[0]
            time_value = float(first.survival_months_dss)
            label = int(np.searchsorted(bins[1:-1], time_value, side="right"))
            slides = [str(value) for value in rows.slide_id if isinstance(value, str)]
            if not slides:
                raise RuntimeError(f"No slide IDs for {case}")
            vector = matrix.loc[case].to_numpy(dtype=np.float32, copy=True)
            records.append(
                dict(
                    case_id=case,
                    slides=slides,
                    label=label,
                    time=time_value,
                    censorship=float(first.censorship_dss),
                    omics=[torch.from_numpy(vector[idx]) for idx in group_indices],
                )
            )
        return records

    provenance = dict(
        metadata=str(metadata_path),
        metadata_sha256=sha256(metadata_path),
        rna=str(rna_path),
        rna_sha256=sha256(rna_path),
        split=str(split_path),
        split_sha256=sha256(split_path),
        train_patients=len(train_ids),
        val_patients=len(val_ids),
        excluded_split_patients_missing_metadata_or_rna=sorted(missing),
        signature_groups=len(groups),
        omic_sizes=[len(item) for item in groups],
        rna_scaling=scaler_kind,
        survival_bins=bins.tolist(),
        survival_bin_scope="training-fold uncensored DSS",
    )
    return make(train_ids), make(val_ids), provenance


class PatientDataset(Dataset):
    def __init__(self, records, cohort, max_patches, training, pad):
        self.records = records
        self.root = ROOT / f"data/tcga_{cohort}/clam_20x_resnet50_paper_k9"
        self.max_patches = max_patches
        self.training = training
        self.pad = pad

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        row = self.records[index]
        features = torch.cat(
            [load_feature(self.root / "pt_files" / f"{Path(slide).stem}.pt") for slide in row["slides"]],
            dim=0,
        )
        if len(features) > self.max_patches:
            chosen = torch.randperm(len(features))[: self.max_patches] if self.training else torch.arange(self.max_patches)
            features = features[chosen]
        valid_patches = len(features)
        if self.pad and len(features) < self.max_patches:
            features = torch.cat(
                [features, torch.zeros((self.max_patches - len(features), 1024), dtype=features.dtype)]
            )
        return dict(
            case_id=row["case_id"],
            features=features,
            valid_patches=valid_patches,
            omics=row["omics"],
            label=torch.tensor(row["label"], dtype=torch.long),
            time=torch.tensor(row["time"], dtype=torch.float32),
            censorship=torch.tensor(row["censorship"], dtype=torch.float32),
        )


def collate_slot(batch):
    return dict(
        case_id=[item["case_id"] for item in batch],
        features=torch.stack([item["features"] for item in batch]),
        omics=[torch.stack([item["omics"][i] for item in batch]) for i in range(len(batch[0]["omics"]))],
        label=torch.stack([item["label"] for item in batch]),
        time=torch.stack([item["time"] for item in batch]),
        censorship=torch.stack([item["censorship"] for item in batch]),
    )


def cindex(times, censorships, risks):
    value = concordance_index_censored(
        (1 - np.asarray(censorships)).astype(bool),
        np.asarray(times, dtype=float),
        np.asarray(risks, dtype=float),
        tied_tol=1e-8,
    )[0]
    if not math.isfinite(value):
        raise RuntimeError("Non-finite C-index")
    return float(value)


def evaluate_discrete(model, loader, device, kind):
    model.eval()
    cases, risks, times, censorships, labels = [], [], [], [], []
    with torch.no_grad():
        for batch in loader:
            if kind == "ld_cvae":
                item = batch
                kwargs = {f"x_omic{i + 1}": value.to(device) for i, value in enumerate(item["omics"])}
                hazards, survival, _, _, _ = model(
                    train=False, stage="jointly", label=item["label"].view(1).to(device),
                    c=item["censorship"].view(1).to(device),
                    x_path=item["features"].to(device), **kwargs
                )
                risk = -survival.sum(dim=1).detach().cpu().numpy()
                batch_cases = [item["case_id"]]
            else:
                item = batch
                kwargs = {f"x_omic{i + 1}": value.to(device) for i, value in enumerate(item["omics"])}
                logits, _ = model(x_wsi=item["features"].to(device), omic_missing=False,
                                  y=None, c=None, **kwargs)
                survival = torch.cumprod(1 - torch.sigmoid(logits), dim=1)
                risk = -survival.sum(dim=1).detach().cpu().numpy()
                batch_cases = item["case_id"]
            cases.extend(batch_cases)
            risks.extend(np.asarray(risk).reshape(-1).tolist())
            times.extend(item["time"].detach().cpu().reshape(-1).tolist())
            censorships.extend(item["censorship"].detach().cpu().reshape(-1).tolist())
            labels.extend(item["label"].detach().cpu().reshape(-1).tolist())
    score = cindex(times, censorships, risks)
    predictions = {
        case: dict(risk=float(risk), time=float(t), censorship=float(c), label=int(y))
        for case, risk, t, c, y in zip(cases, risks, times, censorships, labels)
    }
    return score, predictions


def run_ld_cvae(train_records, val_records, provenance, args, device):
    sys.path.insert(0, str(REPOS["ld_cvae"]))
    from models.model_coattn import Robust_MCAT
    from utils.annealing import Annealer
    from utils.utils import NLLSurvLoss

    train_ds = PatientDataset(train_records, args.cohort, args.max_patches, True, False)
    val_ds = PatientDataset(val_records, args.cohort, args.max_patches, False, False)
    generator = torch.Generator().manual_seed(args.seed)
    train_loader = DataLoader(train_ds, batch_size=None, shuffle=True, generator=generator,
                              num_workers=args.num_workers)
    val_loader = DataLoader(val_ds, batch_size=None, shuffle=False, num_workers=args.num_workers)
    model = Robust_MCAT(
        use_condition=True, generator=True, g_model_type="ldvae", decoder_mode="specific",
        alpha_surv=0.0, wsi_encoding_dim=1024, fusion="concat",
        omic_sizes=provenance["omic_sizes"], n_classes=4,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=2e-4, weight_decay=1e-5)
    loss_fn = NLLSurvLoss(alpha=0.0)
    annealer = Annealer(max(1, args.epochs * len(train_loader)), shape="cosine")
    best = (-1.0, -1, None)
    history = []
    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        for item in train_loader:
            optimizer.zero_grad(set_to_none=True)
            y = item["label"].view(1).to(device)
            c = item["censorship"].view(1).to(device)
            kwargs = {f"x_omic{i + 1}": value.to(device) for i, value in enumerate(item["omics"])}
            hazards, survival, _, _, extra = model(
                stage="warmup" if epoch < 5 else "jointly", train=True,
                label=y, c=c, x_path=item["features"].to(device), **kwargs
            )
            loss = loss_fn(hazards=hazards, S=survival, Y=y, c=c)
            loss = loss + extra["recon_loss"] + extra["encode_wsi_loss"]
            loss = loss + 0.1 * extra["align_loss"]
            loss = loss + 0.1 * annealer() * (
                extra["kl_wsi"] + extra["kl_omic"] + extra["kl_joint"] + extra["kl_omic_componet"]
            )
            loss.backward()
            optimizer.step()
            annealer.step()
            epoch_loss += float(loss.detach())
        score, predictions = evaluate_discrete(model, val_loader, device, "ld_cvae")
        history.append(dict(epoch=epoch, train_loss=epoch_loss / len(train_ds), val_cindex=score))
        print(json.dumps(history[-1]), flush=True)
        if score > best[0]:
            best = (score, epoch, predictions)
            torch.save(model.state_dict(), args.output / "best_checkpoint.pt")
    return best, history


def run_slotspe(train_records, val_records, provenance, args, device):
    sys.path.insert(0, str(REPOS["slotspe"]))
    from models.SlotSPE import SlotSPE
    from utils.loss_func import NLLSurvLoss

    model_args = SimpleNamespace(
        omic_sizes=provenance["omic_sizes"], n_classes=4, encoding_dim=1024,
        wsi_projection_dim=256, rna_format="Pathways", slot_num_wsi=8,
        slot_num_omics=8, slot_iters=10, temperature=0.01, topk_ratio=0.25,
        top_k_method="parallel_topk_st", bag_loss="nll_surv", alpha_surv=0.5,
        lambda_recon_loss=0.01,
    )
    model = SlotSPE(model_args).to(device)
    train_ds = PatientDataset(train_records, args.cohort, args.max_patches, True, True)
    val_ds = PatientDataset(val_records, args.cohort, args.max_patches, False, False)
    generator = torch.Generator().manual_seed(args.seed)
    train_loader = DataLoader(train_ds, batch_size=8, shuffle=True, generator=generator,
                              num_workers=args.num_workers, collate_fn=collate_slot)
    val_loader = DataLoader(val_ds, batch_size=1, shuffle=False, num_workers=args.num_workers,
                            collate_fn=collate_slot)
    loss_fn = NLLSurvLoss(alpha=0.5)
    optimizer = torch.optim.Adam(model.parameters(), lr=5e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-6)
    best = (-1.0, -1, None)
    history = []
    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        for item in train_loader:
            optimizer.zero_grad(set_to_none=True)
            y = item["label"].to(device)
            c = item["censorship"].to(device)
            kwargs = {f"x_omic{i + 1}": value.to(device) for i, value in enumerate(item["omics"])}
            logits, auxiliary = model(x_wsi=item["features"].to(device), omic_missing=False,
                                      y=y, c=c, **kwargs)
            loss = loss_fn(logits, y=y, t=item["time"].to(device), c=c) / len(y) + auxiliary
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach()) * len(y)
        scheduler.step()
        score, predictions = evaluate_discrete(model, val_loader, device, "slotspe")
        history.append(dict(epoch=epoch, train_loss=epoch_loss / len(train_ds), val_cindex=score))
        print(json.dumps(history[-1]), flush=True)
        if score > best[0]:
            best = (score, epoch, predictions)
            torch.save(model.state_dict(), args.output / "best_checkpoint.pt")
    return best, history


def dimaf_embeddings(records, cohort, max_patches, prototypes, args, device, training):
    from models.PANTHER.main_model import PANTHER

    panther_args = SimpleNamespace(
        in_dim=1024, n_proto=16, em_iter=1, tau=0.001, ot_eps=0.1, fix_proto=True
    )
    model = PANTHER(panther_args, prototypes, device).to(device).eval()
    dataset = PatientDataset(records, cohort, max_patches, training, False)
    embeddings = []
    with torch.no_grad():
        for item in DataLoader(dataset, batch_size=None, shuffle=False, num_workers=args.num_workers):
            representation = model.representation(item["features"].unsqueeze(0).to(device))["repr"].cpu()
            p = 16
            d = (representation.shape[1] - p) // (2 * p)
            probability = representation[:, :p]
            means = representation[:, p:p * (1 + d)].reshape(-1, p, d)
            token = torch.cat([probability.unsqueeze(-1), means], dim=-1).squeeze(0)
            embeddings.append(dict(item, features=token))
    return embeddings


class EmbeddedDataset(Dataset):
    def __init__(self, records):
        self.records = records
    def __len__(self):
        return len(self.records)
    def __getitem__(self, index):
        return self.records[index]


def collate_dimaf(batch):
    return dict(
        case_id=[item["case_id"] for item in batch],
        features=torch.stack([item["features"] for item in batch]),
        omics=[torch.stack([item["omics"][i] for item in batch]) for i in range(len(batch[0]["omics"]))],
        label=torch.stack([item["label"] for item in batch]),
        time=torch.stack([item["time"] for item in batch]),
        censorship=torch.stack([item["censorship"] for item in batch]),
    )


def evaluate_dimaf(model, loader, device):
    model.eval()
    cases, risks, times, censorships = [], [], [], []
    with torch.no_grad():
        for item in loader:
            out = model.forward_mm_no_loss(
                item["features"].to(device), [value.to(device) for value in item["omics"]], False
            )
            risk = torch.exp(out["logits"]).cpu().reshape(-1).tolist()
            cases.extend(item["case_id"])
            risks.extend(risk)
            times.extend(item["time"].reshape(-1).tolist())
            censorships.extend(item["censorship"].reshape(-1).tolist())
    score = cindex(times, censorships, risks)
    return score, {
        case: dict(risk=float(risk), time=float(t), censorship=float(c))
        for case, risk, t, c in zip(cases, risks, times, censorships)
    }


def run_dimaf(train_records, val_records, provenance, args, device):
    sys.path.insert(0, str(REPOS["dimaf"]))
    import faiss
    from models.DIMAF.main_model import DIMAF
    from survival.losses import DisentangledSurvLoss

    proto_path = args.output / "prototypes.npy"
    if proto_path.is_file():
        prototypes = np.load(proto_path)
    else:
        dataset = PatientDataset(train_records, args.cohort, args.max_patches, True, False)
        per_patient = max(1, math.ceil(1_600_000 / len(dataset)))
        patches = []
        for item in DataLoader(dataset, batch_size=None, shuffle=False, num_workers=args.num_workers):
            value = item["features"]
            if len(value) > per_patient:
                value = value[torch.randperm(len(value))[:per_patient]]
            patches.append(value)
        patch_matrix = torch.cat(patches)[:1_600_000].numpy()
        print(json.dumps(dict(stage="dimaf_prototypes", patches=len(patch_matrix))), flush=True)
        kmeans = faiss.Kmeans(1024, 16, niter=50, nredo=3, verbose=True,
                             max_points_per_centroid=100000, gpu=False, seed=args.seed)
        kmeans.train(np.ascontiguousarray(patch_matrix, dtype=np.float32))
        prototypes = np.asarray(kmeans.centroids, dtype=np.float32)
        np.save(proto_path, prototypes)
    train_emb = dimaf_embeddings(train_records, args.cohort, args.max_patches, prototypes, args, device, True)
    val_emb = dimaf_embeddings(val_records, args.cohort, args.max_patches, prototypes, args, device, False)
    train_loader = DataLoader(EmbeddedDataset(train_emb), batch_size=64, shuffle=True,
                              generator=torch.Generator().manual_seed(args.seed), collate_fn=collate_dimaf)
    val_loader = DataLoader(EmbeddedDataset(val_emb), batch_size=64, shuffle=False, collate_fn=collate_dimaf)
    loss_fn = DisentangledSurvLoss("cox", "distcor", weight_surv=1.0, weight_disentanglement=7.0)
    model = DIMAF(
        rna_dims=provenance["omic_sizes"], histo_dim=1025, device=device,
        single_out_dim=256, num_classes=1, loss_fn=loss_fn, num_proto_wsi=16,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4, weight_decay=1e-5)
    total_steps = max(1, args.epochs * len(train_loader))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_steps)
    best = (-1.0, -1, None)
    history = []
    for epoch in range(args.epochs):
        model.train()
        epoch_loss = 0.0
        for item in train_loader:
            optimizer.zero_grad(set_to_none=True)
            out, _ = model(
                wsi=item["features"].to(device),
                rna=[value.to(device) for value in item["omics"]],
                label=item["time"].unsqueeze(1).to(device),
                censorship=item["censorship"].unsqueeze(1).to(device),
            )
            out["loss"].backward()
            optimizer.step()
            scheduler.step()
            epoch_loss += float(out["loss"].detach()) * len(item["case_id"])
        score, predictions = evaluate_dimaf(model, val_loader, device)
        history.append(dict(epoch=epoch, train_loss=epoch_loss / len(train_records), val_cindex=score))
        print(json.dumps(history[-1]), flush=True)
        if score > best[0]:
            best = (score, epoch, predictions)
            torch.save(model.state_dict(), args.output / "best_checkpoint.pt")
    return best, history


def atomic_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def main():
    args = parse_args()
    if args.smoke:
        args.epochs = 1
        args.max_patches = min(args.max_patches, 64)
        args.num_workers = 0
    if args.fold not in range(5) or args.epochs < 1:
        raise ValueError("Invalid fold/epoch count")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    complete = args.output / "complete.json"
    if complete.is_file():
        print(complete.read_text(), flush=True)
        return 0
    seed_all(args.seed)
    revision_root = REPOS[args.model] if args.model != "dimaf" else REPOS[args.model].parent
    revision = git_revision(revision_root)
    if revision != COMMITS[args.model]:
        raise RuntimeError(f"Unexpected {args.model} commit: {revision}")
    train_records, val_records, provenance = prepare_records(args.model, args.cohort, args.fold)
    if args.smoke:
        train_records = train_records[: min(4, len(train_records))]
        val_records = val_records[: min(4, len(val_records))]
    manifest = dict(
        model=args.model, cohort=args.cohort, fold=args.fold, repository_commit=revision,
        protocol="official model/loss + unified project ResNet50/DSS/splits adapter",
        feature_source="existing immutable PT, HDF5, or graph.x; 1024-D ResNet50",
        feature_conversion="none", max_patches=args.max_patches,
        epochs=args.epochs, seed=args.seed, started_at=time.time(), provenance=provenance,
    )
    atomic_json(args.output / "manifest.json", manifest)
    device = torch.device("cuda")
    if args.model == "ld_cvae":
        best, history = run_ld_cvae(train_records, val_records, provenance, args, device)
    elif args.model == "slotspe":
        best, history = run_slotspe(train_records, val_records, provenance, args, device)
    else:
        best, history = run_dimaf(train_records, val_records, provenance, args, device)
    score, epoch, predictions = best
    with (args.output / "predictions.pkl").open("wb") as handle:
        pickle.dump(predictions, handle)
    atomic_json(args.output / "history.json", history)
    atomic_json(complete, dict(val_cindex=score, best_epoch=epoch, patients=len(predictions), completed_at=time.time()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
