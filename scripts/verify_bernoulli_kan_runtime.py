#!/usr/bin/env python3
"""Verify the full model after a dependency build; never report test C-index."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def process_identity(pid):
    try:
        # /proc field 22, after the parenthesized process name.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=["hnsc", "blca"], required=True)
    parser.add_argument("--wait-pid", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    status = args.output / "runtime_verification.json"

    def record(state, **extra):
        temp = status.with_suffix(".json.partial")
        temp.write_text(json.dumps(dict(state=state, at=time.time(), **extra), indent=2) + "\n")
        temp.replace(status)

    try:
        if args.wait_pid:
            initial = process_identity(args.wait_pid)
            record("waiting_for_dependency_build", pid=args.wait_pid)
            deadline = time.monotonic() + 7200
            while initial and process_identity(args.wait_pid) == initial:
                if time.monotonic() > deadline:
                    raise TimeoutError("Dependency build exceeded two-hour verification wait")
                time.sleep(15)
        record("verifying")
        os.chdir(ROOT)
        import torch
        import torch_scatter
        import torch_sparse
        from torch_geometric.data import Data
        from datasets.dataset_survival import SurvivalDatasetFactory
        from models.model_HGNN import MRePath
        from utils.pc_cmka import load_pc_cmka_config, build_fold_pc_cmka_priors

        torch.manual_seed(1)
        torch.cuda.manual_seed_all(1)
        cohort = args.cohort
        factory = SurvivalDatasetFactory(
            study=f"tcga_{cohort}", label_file=f"datasets_csv/metadata/tcga_{cohort}.csv",
            omics_dir=f"datasets_csv/raw_rna_data/combine/{cohort}", seed=1,
            print_info=False, n_bins=4, label_col="survival_months_dss",
            num_patches=4096, is_mcat=False, is_survpath=False, type_of_pathway="combine")
        data_args = SimpleNamespace(study=f"tcga_{cohort}", modality="hgnn",
            dataset_factory=factory, fold_survival_bins=True,
            data_root_dir=f"data/tcga_{cohort}/clam_20x_resnet50_paper_k9")
        train, val = factory.return_splits(data_args, f"splits/5folds/tcga_{cohort}/splits_0.csv", 0)
        config = load_pc_cmka_config("configs/pc_cmka_ddkac_word.json", "C4_bernoulli_views")
        graphs, _ = build_fold_pc_cmka_priors(train, config)
        model = MRePath(omic_sizes=factory.omic_sizes, num_patches=4096,
            genomic_encoder="pc_cmka_ddkac", gene_graphs=graphs, pc_cmka_config=config,
            gene_aggregation="kan", graph_type="shgnn", hyperedge_mode="both",
            weighting_mode="dynamic", fusion_variant="ifa", rebalance_variant="original").cuda().train()
        index = torch.arange(64, device="cuda")
        edge = torch.stack([index, (index + 1) % 64])
        inputs = dict(x_path=torch.randn(64, 1024, device="cuda"),
                      graph=Data(edge_index=edge, edge_latent=edge))
        inputs.update({f"x_omic{k+1}": torch.tensor(
            train.omics_data_dict["rna"][names].iloc[0].to_numpy(),
            dtype=torch.float32, device="cuda").unsqueeze(0)
            for k, names in enumerate(train.omic_names)})
        logits = model(**inputs)
        loss = logits.square().mean() + model.auxiliary_loss
        loss.backward()
        assert logits.shape == (1, 4) and torch.isfinite(logits).all()
        assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())
        assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.gene_aggregator.parameters())
        with (args.output / "environment_verified.txt").open("w") as handle:
            subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=handle, check=True)
        record("passed", torch=torch.__version__, cuda=torch.version.cuda,
               torch_scatter=torch_scatter.__version__, torch_sparse=torch_sparse.__version__,
               fold0_train=len(train), fold0_val=len(val), omic_sizes=factory.omic_sizes,
               peak_cuda_gib=torch.cuda.max_memory_allocated()/2**30,
               scope="Real fold-0 RNA and train-only prior; synthetic 64-node pathology graph; CUDA forward/backward only, NOT a performance result")
        print(status.read_text(), flush=True)
    except BaseException as exc:
        record("failed", error=repr(exc))
        raise


if __name__ == "__main__":
    main()
