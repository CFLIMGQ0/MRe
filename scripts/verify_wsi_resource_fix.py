#!/usr/bin/env python3
"""Re-extract a real WSI repeatedly in a separate directory and compare caches."""
import argparse
import json
from pathlib import Path
import resource
import shutil
import time

import h5py
import numpy as np
import torch

import preprocess_wsi_clam as prep


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slide", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True, help="Existing CLAM cache root")
    parser.add_argument("--output", type=Path, required=True, help="New verification-only directory")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("At least two repetitions are required")
    args.output.mkdir(parents=True, exist_ok=False)
    prep.add_clam_to_path(prep.DEFAULT_CLAM_DIR)
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(soft, 1024), hard))
    device = torch.device("cuda")
    model = prep.build_model(device)
    with h5py.File(args.reference / "h5_files" / f"{args.slide.stem}.h5", "r") as handle:
        reference_features = handle["features"][:]
        reference_coords = handle["coords"][:]
    records = []
    for repeat in range(args.repeats):
        started = time.time()
        output = args.output / f"pass_{repeat}"
        (output / "patches").mkdir(parents=True)
        shutil.copy2(args.reference / "patches" / f"{args.slide.stem}.h5", output / "patches")
        before = prep.open_fd_count()
        shape = prep.extract_features(args.slide, output, model, device, batch_size=256, workers=8)
        after = prep.open_fd_count()
        with h5py.File(output / "h5_files" / f"{args.slide.stem}.h5", "r") as handle:
            actual_features = handle["features"][:]
            np.testing.assert_array_equal(handle["coords"][:], reference_coords)
            np.testing.assert_array_equal(actual_features, reference_features)
        records.append(dict(repeat=repeat, shape=shape, fd_before=before, fd_after=after,
            max_abs_feature_difference=float(np.max(np.abs(actual_features-reference_features))),
            coords_identical=True, seconds=round(time.time()-started, 3)))
        print("[real_wsi_verification] " + json.dumps(records[-1]), flush=True)
    counts = [row["fd_after"] for row in records]
    if max(counts) - min(counts) > 8:
        raise RuntimeError(f"Descriptors grew across repeated real slides: {counts}")
    report = dict(status="passed", slide=str(args.slide), reference=str(args.reference),
        synthetic_images=False, workers=8, batch_size=256,
        fd_limit=resource.getrlimit(resource.RLIMIT_NOFILE)[0],
        torch=torch.__version__, records=records)
    (args.output / "verification.json").write_text(json.dumps(report, indent=2)+"\n")
    print("[passed] real WSI: exact features/coords, bounded descriptors", flush=True)


if __name__ == "__main__":
    main()
