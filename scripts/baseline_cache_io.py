"""Read existing patch features without duplicating caches or using graph edges."""
from pathlib import Path
import h5py
import torch


def load_cached_features(filename):
    path = Path(filename)
    if path.is_file():
        features = torch.load(path, map_location="cpu", weights_only=True)
    else:
        root = path.parent.parent
        h5 = root / "h5_files" / (path.stem + ".h5")
        graph = root / "graph_files" / path.name
        if h5.is_file():
            with h5py.File(h5, "r") as handle:
                features = torch.from_numpy(handle["features"][:])
        elif graph.is_file():
            # Trusted local project cache. Only x is consumed; no graph edges.
            features = torch.load(graph, map_location="cpu", weights_only=False).x
        else:
            raise FileNotFoundError(f"No PT/HDF5/graph feature cache for {path}")
    if not isinstance(features, torch.Tensor) or features.ndim != 2 or features.shape[1] != 1024:
        raise ValueError(f"Expected [N,1024] ResNet50 features: {path}")
    if features.dtype != torch.float32 or not torch.isfinite(features).all():
        raise ValueError(f"Non-float32 or non-finite cache: {path}")
    return features
