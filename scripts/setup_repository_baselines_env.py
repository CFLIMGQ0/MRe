#!/usr/bin/env python3
"""Create a NEW venv with read-only access to existing Torch; install locally only."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-python", type=Path, required=True)
    p.add_argument("--target", type=Path, required=True)
    p.add_argument("--wheelhouse", type=Path, help="Optional local wheel directory; install with no network")
    args = p.parse_args()
    target = args.target.absolute()
    if target.exists():
        raise FileExistsError(f"Will not modify an existing environment: {target}")
    query = "import json,sys; print(json.dumps({'base_prefix':sys.base_prefix,'version':sys.version_info[:2],'sites':[p for p in sys.path if p.endswith('site-packages')]}))"
    base = json.loads(subprocess.check_output([str(args.base_python.absolute()), "-c", query], text=True))
    if base["version"] != [3, 12]:
        raise RuntimeError("This tested overlay recipe requires Python 3.12")
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    env["NO_PROXY"] = "*"
    env["LD_LIBRARY_PATH"] = str(Path(base["base_prefix"]) / "lib")
    subprocess.run([str(args.base_python.absolute()), "-m", "venv", str(target)], env=env, check=True)
    site = target / "lib/python3.12/site-packages"
    (site / "project_baselines_runtime.pth").write_text("\n".join(base["sites"]) + "\n")
    python = target / "bin/python"
    if args.wheelhouse:
        if not args.wheelhouse.is_dir():
            raise FileNotFoundError(args.wheelhouse)
        source_args = ["--no-index", "--find-links", str(args.wheelhouse.absolute())]
    else:
        source_args = ["--index-url", "https://pypi.org/simple", "--timeout", "15", "--retries", "1"]
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", *source_args, "-r",
                    str(ROOT / "configs/repository_baselines_overlay_requirements.txt")], env=env, check=True)
    (target / "repository_baselines_environment.json").write_text(json.dumps({
        "base_python": str(args.base_python.absolute()), "base": base,
        "LD_LIBRARY_PATH": env["LD_LIBRARY_PATH"], "shared_packages_read_only": True,
        "warning": "Shared unrelated image-codec packages may require NumPy 2; this overlay is for feature-based baselines only. Not a raw WSI extraction environment."
    }, indent=2) + "\n")
    print(f"Created {python}; base environment not modified")


if __name__ == "__main__":
    main()
