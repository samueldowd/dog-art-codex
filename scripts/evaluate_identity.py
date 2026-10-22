#!/usr/bin/env python3
"""Evaluate a protected, human-labeled independent-event feature manifest locally."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from dog_art.contracts import ImageFeature
from dog_art.description import parse_description
from dog_art.identity.evaluation import LabeledSample, select_calibration


def main(argv=None):
    os.umask(0o077)
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--calibration-output", type=Path)
    p.add_argument("--reviewed-by", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--cameras", nargs=2, required=True)
    args = p.parse_args(argv)
    if args.manifest.is_symlink() or args.manifest.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("unsafe private manifest")
    for dest in (args.output, args.calibration_output):
        if dest and (dest.exists() or dest.is_symlink()):
            raise ValueError("output already exists")
    if args.calibration_output and args.calibration_output.absolute() == args.output.absolute():
        raise ValueError("receipt and runtime calibration need distinct paths")
    data = json.loads(args.manifest.read_text())
    if data.get("schema") != 2:
        raise ValueError("manifest schema 2 required")
    samples = []
    for item in data["samples"]:
        item = dict(item)
        item["features"] = tuple(
            ImageFeature(
                tuple(f["values"]),
                f["model"],
                f["model_digest"],
                f["preprocessing"],
                f.get("provenance", "real_camera"),
            )
            for f in item["features"]
        )
        item["description"] = parse_description(item["description"])
        samples.append(LabeledSample(**item))
    result = select_calibration(
        samples, required_cameras=args.cameras, reviewed_by=args.reviewed_by, version=args.version
    )
    with args.output.open("x") as f:
        json.dump(result.receipt(), f, indent=2, sort_keys=True, allow_nan=False)
    # Never emit a runtime file for provisional, synthetic or failed evaluation.
    if result.promotable and args.calibration_output:
        from dog_art.identity.matching import Calibration

        with args.calibration_output.open("x") as f:
            json.dump(asdict(result.calibration), f, indent=2, sort_keys=True, allow_nan=False)
        Calibration.load(args.calibration_output)
    print(
        json.dumps(
            {
                "promotable": result.promotable,
                "blocked_reason": result.blocked_reason,
                "receipt": str(args.output),
                "dataset_sha256": result.dataset_sha256,
                "runtime_calibration_written": bool(result.promotable and args.calibration_output),
            }
        )
    )
    return 0 if result.promotable else 2


if __name__ == "__main__":
    raise SystemExit(main())
