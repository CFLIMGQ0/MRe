"""Resource lifetime regression tests; opt in to 120-slide CUDA stress below.

MREPATH_CUDA_STRESS=1 python -m unittest discover -s tests \
    -p test_preprocess_wsi_resources.py -v

The stress test uses real DataLoader workers, pinned memory, CUDA and HDF5;
only WSI image decoding/model computation are replaced with tiny fixtures.
"""
import contextlib
import io
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import resource
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import h5py
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preprocess_wsi_clam as prep

prep.add_clam_to_path(prep.DEFAULT_CLAM_DIR)
# unittest discovery may already import the project's own `datasets` package.
# Explicitly load only CLAM's submodule; do not replace that project package.
spec = importlib.util.spec_from_file_location("datasets.dataset_h5",
    prep.DEFAULT_CLAM_DIR / "datasets/dataset_h5.py")
dataset_h5 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dataset_h5
spec.loader.exec_module(dataset_h5)


class TinyDataset(torch.utils.data.Dataset):
    def __init__(self, file_path, **kwargs):
        with h5py.File(file_path, "r") as handle:
            self.coords = handle["coords"][:]

    def __len__(self):
        return len(self.coords)

    def __getitem__(self, index):
        return torch.full((1, 3, 4, 4), float(index)), self.coords[index]


class TinyEncoder(torch.nn.Module):
    def forward(self, images):
        return images.mean(dim=(1, 2, 3)).unsqueeze(1).repeat(1, 1024)


class TrackedSlide:
    def __init__(self, path):
        self.handle = open(path, "rb")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.handle.close()


class PreprocessResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mrepath_fd_test_")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.slide_path = self.output / "tiny.svs"
        self.slide_path.touch()
        (self.output / "patches").mkdir()
        self.coords = np.arange(16).reshape(8, 2)
        with h5py.File(self.output / "patches/tiny.h5", "w") as handle:
            dset = handle.create_dataset("coords", data=self.coords)
            dset.attrs["patch_size"] = 256
        self.slides = []
        self.addCleanup(patch.stopall)
        patch.object(dataset_h5, "Whole_Slide_Bag_FP", TinyDataset).start()
        patch.object(prep.openslide, "OpenSlide", self.make_slide).start()

    def make_slide(self, path):
        slide = TrackedSlide(path)
        self.slides.append(slide)
        return slide

    def extract(self, model=None, workers=0, device="cpu"):
        with contextlib.redirect_stdout(io.StringIO()):
            return prep.extract_features(self.slide_path, self.output,
                TinyEncoder() if model is None else model, torch.device(device), 4, workers)

    def test_features_and_coords_unchanged_and_slide_closed(self):
        self.assertEqual(self.extract(workers=2), (8, 1024))
        self.assertTrue(self.slides[-1].handle.closed)
        with h5py.File(self.output / "h5_files/tiny.h5", "r") as handle:
            np.testing.assert_array_equal(handle["coords"][:], self.coords)
            np.testing.assert_array_equal(handle["features"][:],
                                          np.arange(8)[:, None].repeat(1024, axis=1))
        self.assertFalse((self.output / "h5_files/tiny.h5.partial").exists())

    def test_cpu_no_worker_path(self):
        self.assertEqual(self.extract(), (8, 1024))
        self.assertTrue(self.slides[-1].handle.closed)

    def test_early_model_failure_closes_slide_and_workers(self):
        children_before = {p.pid for p in multiprocessing.active_children()}
        model = MagicMock(side_effect=RuntimeError("injected model error"))
        with self.assertRaisesRegex(RuntimeError, "injected model error"):
            self.extract(model=model, workers=2)
        self.assertTrue(self.slides[-1].handle.closed)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, children_before)
        self.assertFalse((self.output / "h5_files/tiny.h5").exists())

    def test_writer_failure_preserves_previous_complete_cache(self):
        self.extract()
        path = self.output / "h5_files/tiny.h5"
        original = path.read_bytes()
        with patch.object(prep, "save_feature_batch", side_effect=OSError("injected disk error")):
            with self.assertRaisesRegex(OSError, "injected disk error"):
                self.extract(workers=2)
        self.assertTrue(self.slides[-1].handle.closed)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(multiprocessing.active_children())

    def test_validation_failure_does_not_publish_bad_features(self):
        self.extract()
        path = self.output / "h5_files/tiny.h5"
        original = path.read_bytes()
        with patch.object(prep, "validate_features", return_value=(8, 10)):
            with self.assertRaisesRegex(RuntimeError, "Feature validation failed"):
                self.extract(workers=2)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(self.slides[-1].handle.closed)

    def test_loader_does_not_persist_and_stops_workers_on_early_exit(self):
        dataset = TinyDataset(self.output / "patches/tiny.h5")
        with self.assertRaisesRegex(RuntimeError, "early stop"):
            with prep.managed_feature_loader(dataset, 4, 2, torch.device("cpu")) as (loader, batches):
                self.assertFalse(loader.persistent_workers)
                next(batches)
                processes = batches._workers
                raise RuntimeError("early stop")
        self.assertTrue(all(not process.is_alive() for process in processes))

    def test_segmentation_failure_closes_slide(self):
        wsi = MagicMock()
        wsi.getOpenSlide.return_value = self.make_slide(str(self.slide_path))
        wsi_module = SimpleNamespace(WholeSlideImage=lambda path: wsi)
        with patch.dict(sys.modules, {"wsi_core.WholeSlideImage": wsi_module}), \
             patch.object(prep, "select_patch_geometry", side_effect=ValueError("bad geometry")):
            with self.assertRaisesRegex(ValueError, "bad geometry"):
                prep.segment_slide(self.slide_path, self.output, "true-20x")
        self.assertTrue(self.slides[-1].handle.closed)

    @unittest.skipUnless(os.environ.get("MREPATH_CUDA_STRESS") == "1", "opt-in CUDA/8-worker stress")
    def test_cuda_120_consecutive_slides_under_1024_fd_limit(self):
        self.assertTrue(torch.cuda.is_available(), "CUDA stress requires a free GPU")
        old_limits = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(1024, old_limits[1]), old_limits[1]))
        self.addCleanup(resource.setrlimit, resource.RLIMIT_NOFILE, old_limits)
        model = TinyEncoder().cuda().eval()
        # Warm up CUDA and its one-time descriptors before measuring growth.
        self.extract(model=model, workers=8, device="cuda")
        baseline = prep.open_fd_count()
        counts = []
        for index in range(120):
            self.assertEqual(self.extract(model=model, workers=8, device="cuda"), (8, 1024))
            counts.append(prep.open_fd_count())
            self.assertTrue(self.slides[-1].handle.closed)
            self.assertFalse(multiprocessing.active_children())
            self.assertLessEqual(counts[-1], baseline + 8)
            if (index + 1) % 20 == 0:
                print(f"[fd_stress] slides={index+1}/120 fd={counts[-1]} baseline={baseline}", flush=True)
            if (index + 1) % 30 == 0:
                with patch.object(prep, "save_feature_batch", side_effect=OSError("injected CUDA writer error")):
                    with self.assertRaisesRegex(OSError, "injected CUDA writer error"):
                        self.extract(model=model, workers=8, device="cuda")
                self.assertFalse(multiprocessing.active_children())
        self.assertLessEqual(max(counts[-60:]) - min(counts[-60:]), 4)
        print("[fd_stress_result] " + json.dumps(dict(status="passed", successful_slides=120,
            injected_error_slides=4, workers=8, pin_memory=True, persistent_workers=False,
            fd_limit=resource.getrlimit(resource.RLIMIT_NOFILE)[0], baseline=baseline,
            fd_min=min(counts), fd_max=max(counts), fd_final=counts[-1],
            torch=torch.__version__, synthetic_images=True)), flush=True)


if __name__ == "__main__":
    unittest.main()
