#!/usr/bin/env python3
"""Build GDC manifests for diagnostic WSIs in the repository's fixed folds."""

from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path


COHORT_PROJECTS = {
    "blca": ("TCGA-BLCA",),
    "brca": ("TCGA-BRCA",),
    "coadread": ("TCGA-COAD", "TCGA-READ"),
    "hnsc": ("TCGA-HNSC",),
    "stad": ("TCGA-STAD",),
}

CASE_PATTERN = re.compile(r"^(TCGA-[^-]+-[^-]+)", re.IGNORECASE)
DX_PATTERN = re.compile(r"-DX[0-9A-Z]?(?:\.|-)", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("gdc_download/manifests"),
    )
    return parser.parse_args()


def fixed_fold_cases(project_dir: Path, cohort: str) -> set[str]:
    cases: set[str] = set()
    split_dir = project_dir / "splits" / "5folds" / f"tcga_{cohort}"
    paths = sorted(split_dir.glob("splits_*.csv"))
    if len(paths) != 5:
        raise RuntimeError(f"Expected 5 split files for {cohort}, found {len(paths)}")
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                for column in ("train", "val"):
                    value = (row.get(column) or "").strip().upper()
                    if value:
                        cases.add(value)
    return cases


def fetch_slide_files() -> list[dict]:
    projects = sorted({p for values in COHORT_PROJECTS.values() for p in values})
    filters = {
        "op": "and",
        "content": [
            {
                "op": "in",
                "content": {
                    "field": "cases.project.project_id",
                    "value": projects,
                },
            },
            {
                "op": "in",
                "content": {"field": "data_type", "value": ["Slide Image"]},
            },
            {
                "op": "in",
                "content": {"field": "access", "value": ["open"]},
            },
        ],
    }
    params = urllib.parse.urlencode(
        {
            "filters": json.dumps(filters, separators=(",", ":")),
            "fields": (
                "file_id,file_name,file_size,md5sum,state,"
                "cases.submitter_id,cases.project.project_id"
            ),
            "format": "JSON",
            "size": "10000",
        }
    )
    request = urllib.request.Request(
        f"https://api.gdc.cancer.gov/files?{params}",
        headers={"User-Agent": "MRePath-manifest-builder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    hits = payload["data"]["hits"]
    total = payload["data"]["pagination"]["total"]
    if len(hits) != total:
        raise RuntimeError(f"GDC response truncated: received {len(hits)} of {total}")
    return hits


def case_from_filename(filename: str) -> str:
    match = CASE_PATTERN.match(filename)
    return match.group(1).upper() if match else ""


def projects_for_hit(hit: dict) -> set[str]:
    return {
        case.get("project", {}).get("project_id", "")
        for case in hit.get("cases", [])
    }


def main() -> None:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = project_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    hits = fetch_slide_files()
    summary: dict[str, dict[str, int]] = {}
    all_ids: set[str] = set()

    for cohort, projects in COHORT_PROJECTS.items():
        cases = fixed_fold_cases(project_dir, cohort)
        selected = [
            hit
            for hit in hits
            if case_from_filename(hit["file_name"]) in cases
            and DX_PATTERN.search(hit["file_name"])
            and projects_for_hit(hit).intersection(projects)
        ]
        selected.sort(key=lambda hit: (case_from_filename(hit["file_name"]), hit["file_name"]))

        found_cases = {case_from_filename(hit["file_name"]) for hit in selected}
        missing_cases = sorted(cases - found_cases)
        if missing_cases:
            raise RuntimeError(f"{cohort}: cases without a DX slide: {missing_cases}")

        ids = {hit["file_id"] for hit in selected}
        if len(ids) != len(selected):
            raise RuntimeError(f"{cohort}: duplicate GDC file IDs")
        overlap = ids.intersection(all_ids)
        if overlap:
            raise RuntimeError(f"{cohort}: file IDs overlap another cohort: {sorted(overlap)}")
        all_ids.update(ids)

        manifest_path = output_dir / f"tcga_{cohort}_fixed_folds_dx.tsv"
        with manifest_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(("id", "filename", "md5", "size", "state"))
            for hit in selected:
                writer.writerow(
                    (
                        hit["file_id"],
                        hit["file_name"],
                        hit["md5sum"],
                        hit["file_size"],
                        hit["state"],
                    )
                )

        total_bytes = sum(int(hit["file_size"]) for hit in selected)
        summary[cohort] = {
            "fixed_fold_cases": len(cases),
            "dx_cases": len(found_cases),
            "files": len(selected),
            "bytes": total_bytes,
        }
        print(
            f"{cohort}: cases={len(cases)} files={len(selected)} "
            f"GiB={total_bytes / 2**30:.2f} manifest={manifest_path}"
        )

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
