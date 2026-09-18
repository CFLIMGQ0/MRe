#!/usr/bin/env python3
"""Exercise official model/training functions on SYNTHETIC data, CPU only.

This is an executable compatibility test, NOT a TCGA experiment or performance
measurement. Each repository runs in a separate subprocess to avoid collisions
between their top-level `models`, `dataset`, and `utils` Python packages.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/repository_baselines_20260913.json"


def provenance(model):
    cfg = json.loads(MANIFEST.read_text())["models"][model]
    repo = ROOT / cfg["directory"]
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if head != cfg["commit"]:
        raise RuntimeError(f"Unreviewed repository revision: {head}")
    diff = subprocess.check_output(["git", "-C", str(repo), "diff", "--no-ext-diff"], text=True)
    return repo, {"repository": cfg["url"], "commit": head, "local_diff": diff}


def tracking_adam(parameters, **kwargs):
    import torch

    class TrackingAdam(torch.optim.Adam):
        """Identical Adam update; observe gradients before upstream clears them."""
        steps_checked = 0
        parameters_with_grad = 0

        def step(self, closure=None):
            grads = [p.grad for g in self.param_groups for p in g["params"] if p.grad is not None]
            assert grads and all(torch.isfinite(g).all() for g in grads), "Non-finite or missing gradients"
            assert any(torch.count_nonzero(g) for g in grads), "All gradients zero"
            self.parameters_with_grad = len(grads)
            self.steps_checked += 1
            return super().step(closure)

    return TrackingAdam(parameters, **kwargs)


def roundtrip(model, predict):
    import torch
    model.eval()
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    with torch.no_grad():
        torch.manual_seed(731)
        expected = predict().detach().clone()
        assert torch.isfinite(expected).all()
        # Verify loading really restores a changed parameter, not just no-op load.
        next(model.parameters()).add_(1)
        buffer.seek(0)
        model.load_state_dict(torch.load(buffer, map_location="cpu", weights_only=True), strict=True)
        torch.manual_seed(731)
        actual = predict().detach()
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)
    return list(actual.shape)


class ListLoader(list):
    def __init__(self, batches, sample_count):
        super().__init__(batches)
        self.dataset = range(sample_count)


def smoke_ld(repo):
    import torch
    from types import SimpleNamespace
    from models.model_coattn import Robust_MCAT
    from models.model_survpath import Robust_SurvPath
    from trainer.coattn_trainer import train_loop_survival_coattn
    from utils.annealing import Annealer
    from utils.utils import NLLSurvLoss

    sizes = [16, 20, 24, 28, 32, 36]  # synthetic genes, six official functional groups
    outputs = {}
    for name, cls in [("mcat", Robust_MCAT), ("survpath", Robust_SurvPath)]:
        torch.manual_seed(2024)
        model = cls(generator=True, use_condition=True, g_model_type="ldvae",
                    decoder_mode="specific", wsi_encoding_dim=768, omic_sizes=sizes)
        optimizer = tracking_adam(model.parameters(), lr=2e-4, weight_decay=1e-5)
        before = next(model.parameters()).detach().clone()
        batches = [(torch.randn(64, 768), *[torch.randn(s) for s in sizes],
                    torch.tensor([i]), float(10 + i * 10), torch.tensor([float(i == 1)]))
                   for i in range(3)]
        with tempfile.TemporaryDirectory(prefix="ld_cvae_cpu_smoke_") as tmp:
            args = SimpleNamespace(warm_epoch=5, generator=True, beta=1.0, alpha=0.1,
                                   writer_dir=tmp, annealing_agent=Annealer(60, "cosine"))
            for epoch in (0, 5):
                train_loop_survival_coattn(epoch, model, batches, optimizer, 4,
                                          loss_fn=NLLSurvLoss(alpha=0), gc=1, args=args)
        assert not torch.equal(before, next(model.parameters()).detach())
        kw = {"x_path": batches[0][0], "train": False}
        kw.update({f"x_omic{i + 1}": batches[0][i + 1] for i in range(6)})
        shape = roundtrip(model, lambda: model(**kw)[0])
        with torch.no_grad():
            missing = model(omic_missing=True, x_path=batches[0][0], train=False)[0]
            assert missing.shape == (1, 4) and torch.isfinite(missing).all()
        outputs[name] = {"native_train_epochs_exercised": ["warmup", "jointly"],
                         "optimizer_steps": optimizer.steps_checked,
                         "parameters_with_grad": optimizer.parameters_with_grad,
                         "output_shape": shape, "full_and_missing_modalities": "pass",
                         "checkpoint_roundtrip": "pass"}
    return outputs


def smoke_dimaf(repo):
    import numpy as np
    import pandas as pd
    import torch
    from types import SimpleNamespace
    from models.PANTHER import PANTHER
    from embeddings.embeddings import get_mixture_params
    from models.DIMAF import DIMAF
    from survival.losses import DisentangledSurvLoss
    from survival.train import train_loop

    torch.manual_seed(1)
    sig = pd.read_csv(repo / "src/data/data_files/hallmarks_signatures.csv")
    sizes = [int(sig[c].dropna().nunique()) for c in sig.columns]
    args = SimpleNamespace(in_dim=1024, n_proto=16, em_iter=1, tau=0.001,
                           ot_eps=0.1, fix_proto=True)
    device = torch.device("cpu")
    # Synthetic prototypes test PANTHER interfaces, NOT fitted clinical prototypes.
    prototypes = torch.randn(16, 1024).numpy().astype(np.float32)
    panther = PANTHER(args, prototypes, device)
    with torch.no_grad():
        raw = panther(torch.randn(4, 64, 1024))
        prob, mean = get_mixture_params(raw, 16)
        features = torch.cat([prob.unsqueeze(-1), mean], dim=-1)
    assert features.shape == (4, 16, 1025) and torch.isfinite(features).all()
    loss_fn = DisentangledSurvLoss("cox", "distcor", weight_surv=1, weight_disentanglement=7)
    model = DIMAF(sizes, 1025, device, loss_fn=loss_fn)
    rna = [torch.randn(4, size) for size in sizes]
    times = torch.tensor([[10.], [20.], [30.], [40.]])
    censor = torch.tensor([[0.], [1.], [0.], [0.]])
    batch = dict(img=features, rna=rna, label=times, survival_time=times, censorship=censor)
    optimizer = tracking_adam(model.parameters(), lr=1e-4, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda _: 1.0)
    before = next(model.parameters()).detach().clone()
    logs, _ = train_loop(model, ListLoader([batch], 4), optimizer, scheduler, device)
    assert not torch.equal(before, next(model.parameters()).detach())
    shape = roundtrip(model, lambda: model(features, rna, times, censor)[0]["logits"])
    return {"native_train_loop": "pass", "optimizer_steps": optimizer.steps_checked,
            "parameters_with_grad": optimizer.parameters_with_grad,
            "pathway_count": len(sizes), "PANTHER_output_shape": list(raw.shape),
            "DIMAF_input_shape": list(features.shape), "output_shape": shape,
            "loss": "native Cox + 7 * distance correlation", "checkpoint_roundtrip": "pass",
            "clustering_tested": False, "scheduler_note": "constant only for one synthetic step"}


def smoke_slotspe(repo):
    import pandas as pd
    import torch
    from models.SlotSPE import SlotSPE
    from utils.process_args import _process_args
    from utils.core_utils import _init_loss_function, _train_loop_survival, _init_scheduler

    saved_argv = sys.argv
    try:
        sys.argv = [str(repo / "survival.py")]
        args = _process_args()
    finally:
        sys.argv = saved_argv
    torch.manual_seed(args.seed)
    sig = pd.read_csv(repo / "dataset_csv/signatures/combine_signatures.csv")
    args.omic_sizes = [int(sig[c].dropna().nunique()) for c in sig.columns]
    assert all(args.omic_sizes)
    model = SlotSPE(args)
    optimizer = tracking_adam(model.parameters(), lr=args.lr)  # official Adam ignores args.reg
    scheduler = _init_scheduler(args, optimizer)
    wsi = torch.randn(4, 64, args.encoding_dim)
    per_patient = [[torch.randn(s) for s in args.omic_sizes] for _ in range(4)]
    y, c = torch.arange(4), torch.tensor([0., 1., 0., 0.])
    batch = (wsi, per_patient, y, torch.tensor([10., 20., 30., 40.]), c)
    before = next(model.parameters()).detach().clone()
    _train_loop_survival(args, 0, model, ListLoader([batch], 4), optimizer, scheduler,
                         _init_loss_function(args), io.StringIO())
    assert not torch.equal(before, next(model.parameters()).detach())
    kw = dict(x_wsi=wsi, y=y, c=c, omic_missing=False)
    kw.update({f"x_omic{i + 1}": torch.stack([p[i] for p in per_patient])
               for i in range(len(args.omic_sizes))})
    shape = roundtrip(model, lambda: model(**kw)[0])
    kw["omic_missing"] = True
    with torch.no_grad():
        logits, _ = model(**kw)
        assert logits.shape == (4, 4) and torch.isfinite(logits).all()
    return {"native_train_loop": "pass", "optimizer_steps": optimizer.steps_checked,
            "parameters_with_grad": optimizer.parameters_with_grad,
            "pathway_count": len(args.omic_sizes), "output_shape": shape,
            "slot_counts": [args.slot_num_wsi, args.slot_num_omics], "slot_iters": args.slot_iters,
            "loss": "native main NLL + slot decoder NLL + reconstruction auxiliaries",
            "full_and_missing_modalities": "pass", "checkpoint_roundtrip": "pass"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["all", "ld_cvae", "dimaf", "slotspe"], default="all")
    parser.add_argument("--output", type=Path, required=True, help="New directory; never overwrite a run")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.child:
        args.output.mkdir(parents=True, exist_ok=False)
        models = [args.model] if args.model != "all" else ["ld_cvae", "dimaf", "slotspe"]
        results = []
        env = dict(os.environ, CUDA_VISIBLE_DEVICES="", OMP_NUM_THREADS="2", MKL_NUM_THREADS="2")
        for model in models:
            command = [sys.executable, str(Path(__file__).resolve()), "--child", "--model", model,
                       "--output", str(args.output.resolve())]
            with (args.output / f"{model}.log").open("x") as log:
                result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            results.append({"model": model, "returncode": result.returncode})
            print(json.dumps(results[-1]), flush=True)
        (args.output / "summary.json").write_text(json.dumps({"synthetic_only": True, "runs": results}, indent=2) + "\n")
        return int(any(r["returncode"] for r in results))
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import torch
    import numpy as np
    torch.set_num_threads(2)
    repo, source = provenance(args.model)
    sys.path.insert(0, str(repo / "src" if args.model == "dimaf" else repo))
    started = time.monotonic()
    result = dict(source, model=args.model, synthetic_only=True, device="cpu",
                  python=sys.version, torch=torch.__version__, numpy=np.__version__,
                  input_note="Random tensors; 64 patches. No TCGA performance measured.")
    try:
        result["checks"] = {"ld_cvae": smoke_ld, "dimaf": smoke_dimaf, "slotspe": smoke_slotspe}[args.model](repo)
        result["status"] = "passed"
    except Exception:
        result["status"] = "failed"
        result["error"] = traceback.format_exc()
        print(result["error"], flush=True)
    result["seconds"] = round(time.monotonic() - started, 3)
    (args.output / f"{args.model}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return int(result["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
