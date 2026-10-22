#!/usr/bin/env python3
"""Export existing genuine features with explicit human labels; never infer labels."""

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dog_art.contracts import ImageFeature
from dog_art.description import parse_description
from dog_art.identity.evaluation import LabeledSample


def main(argv=None):
    os.umask(0o077)
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if (
        args.catalog.is_symlink()
        or args.labels.is_symlink()
        or args.labels.stat().st_size > 16 * 1024 * 1024
    ):
        raise ValueError("unsafe private input")
    labels = json.loads(args.labels.read_text())
    if labels.get("schema") != 2:
        raise ValueError("human labels schema 2 required")
    db = sqlite3.connect(args.catalog.absolute().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("schema 1 catalog required")
        samples = []
        seen = set()
        for label in labels["samples"]:
            oid = label["observation_id"]
            if oid in seen:
                raise ValueError("duplicate observation label")
            seen.add(oid)
            row = db.execute(
                """SELECT o.*, f.model,f.digest,f.preprocessing,f.dimension,f.vector,
                                d.payload AS description FROM observations o
                                JOIN features f USING(observation_id)
                                JOIN descriptions d USING(observation_id)
                                WHERE observation_id=?""",
                (oid,),
            ).fetchone()
            if row is None:
                raise ValueError("labeled observation lacks durable feature/description evidence")
            observation = json.loads(row["payload"])
            if not observation["crops"] or any(
                c.get("provenance") != "real_camera" for c in observation["crops"]
            ):
                raise ValueError("real camera observations required")
            vectors = json.loads(row["vector"])
            if vectors and isinstance(vectors[0], (float, int)):
                vectors = [vectors]
            features = [
                dict(
                    values=v,
                    model=row["model"],
                    model_digest=row["digest"],
                    preprocessing=row["preprocessing"],
                    provenance="real_camera",
                )
                for v in vectors
            ]
            item = {
                **label,
                "event_id": row["event_id"],
                "camera": row["camera"],
                "observed_day": datetime.fromtimestamp(
                    row["observed_at"], ZoneInfo("America/New_York")
                )
                .date()
                .isoformat(),
                "features": features,
                "description": json.loads(row["description"]),
                "quality": observation["quality"],
                "provenance": "real_camera",
            }
            # Validate label field names/types through the actual evaluation record.
            check = {
                **item,
                "features": tuple(
                    ImageFeature(**{**f, "values": tuple(f["values"])}) for f in features
                ),
                "description": parse_description(item["description"]),
            }
            LabeledSample(**check)
            samples.append(item)
    finally:
        db.close()
    with args.output.open("x") as f:
        json.dump({"schema": 2, "samples": samples}, f, indent=2, sort_keys=True, allow_nan=False)
    print(
        json.dumps({"samples": len(samples), "output": str(args.output), "labels_inferred": False})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
