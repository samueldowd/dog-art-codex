"""Canonical private observation payloads; timestamps are always explicit UTC."""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .contracts import CropRef, DogDescription, DogObservation


def observation_dict(observation):
    data = asdict(observation)
    data["observed_at"] = observation.observed_at.isoformat()
    for c, crop in zip(data["crops"], observation.crops):
        c["path"] = str(crop.path)
        c["observed_at"] = crop.observed_at.isoformat()
    return data


def observation_from_dict(data):
    values = dict(data)
    values["observed_at"] = datetime.fromisoformat(values["observed_at"])
    crops = []
    for value in values["crops"]:
        c = dict(value)
        c["path"] = Path(c["path"])
        c["observed_at"] = datetime.fromisoformat(c["observed_at"])
        c["box"] = tuple(c["box"])
        c["source_size"] = tuple(c["source_size"])
        crops.append(CropRef(**c))
    values["crops"] = tuple(crops)
    return DogObservation(**values)


def description_from_dict(data):
    values = dict(data)
    for k in ("coat_colors", "visible_areas", "occluded_areas", "uncertainty"):
        values[k] = tuple(values[k])
    return DogDescription(**values)
