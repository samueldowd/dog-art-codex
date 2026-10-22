"""Real-image feature extraction and conservative, reversible identity decisions."""

from .encoder import EncoderManifest, OnnxImageEncoder
from .engine import IdentityEngine
from .matching import Calibration, decide

__all__ = ["EncoderManifest", "OnnxImageEncoder", "IdentityEngine", "Calibration", "decide"]
