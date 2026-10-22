"""Explicit local ONNX visual features; no model retrieval code exists here."""

import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from dog_art.contracts import ImageFeature
from dog_art.description import validate_observation


@dataclass(frozen=True)
class EncoderManifest:
    model: str
    path: Path
    sha256: str
    dimension: int
    preprocessing: str
    width: int
    height: int
    resize: str
    mean: tuple[float, float, float]
    std: tuple[float, float, float]
    output: str
    pooling: str
    source: str
    license: str

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError("unsafe encoder manifest")
        value = json.loads(path.read_text())
        required = {f.name for f in fields(cls)}
        if set(value) != required:
            raise ValueError("encoder manifest fields mismatch")
        model_path = Path(value["path"])
        if not model_path.is_absolute():
            model_path = path.parent / model_path
        value["path"] = model_path
        for name in ("mean", "std"):
            if not isinstance(value[name], list) or len(value[name]) != 3:
                raise ValueError("three RGB normalization channels required")
            value[name] = tuple(float(x) for x in value[name])
        item = cls(**value)
        if (
            not item.model
            or not item.preprocessing
            or not item.source
            or not item.license
            or item.dimension < 1
            or item.dimension > 8192
            or not 16 <= item.width <= 1024
            or not 16 <= item.height <= 1024
            or item.resize not in {"stretch", "center_crop", "short_edge_256_center_crop"}
            or item.pooling not in {"none", "cls", "mean_tokens"}
            or not np.isfinite(item.mean + item.std).all()
            or min(item.std) <= 0
            or len(item.sha256) != 64
        ):
            raise ValueError("invalid encoder manifest")
        return item


class OnnxImageEncoder:
    """CPU image-only inference from an explicit hashed model and preprocessing manifest."""

    def __init__(self, manifest, *, session=None):
        self.manifest = (
            manifest if isinstance(manifest, EncoderManifest) else EncoderManifest.load(manifest)
        )
        m = self.manifest
        if m.path.is_symlink() or not m.path.is_file():
            raise ValueError("encoder must be a local regular file")
        digest = hashlib.sha256()
        with m.path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != m.sha256:
            raise ValueError("encoder digest mismatch")
        if session is None:
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            # Loading verified bytes disallows resolving unhashed external weight
            # files from the graph's directory. Single-file ONNX is required.
            model_bytes = m.path.read_bytes()
            if hashlib.sha256(model_bytes).hexdigest() != m.sha256:
                raise ValueError("encoder changed during initialization")
            session = ort.InferenceSession(
                model_bytes, sess_options=options, providers=["CPUExecutionProvider"]
            )
        self.session = session
        inputs = session.get_inputs()
        outputs = {o.name for o in session.get_outputs()}
        if len(inputs) != 1 or inputs[0].type != "tensor(float)" or m.output not in outputs:
            raise ValueError("encoder must expose one float image input and configured output")
        shape = inputs[0].shape
        if len(shape) != 4 or any(
            isinstance(s, int) and s != v for s, v in zip(shape, (1, 3, m.height, m.width))
        ):
            raise ValueError("encoder image input shape mismatch")
        self.input_name = inputs[0].name
        preprocessing_spec = {
            "version": m.preprocessing,
            "width": m.width,
            "height": m.height,
            "resize": m.resize,
            "mean": m.mean,
            "std": m.std,
            "output": m.output,
            "pooling": m.pooling,
            "pixels": "exif-transpose-rgb-bicubic-unit-float32-nchw",
        }
        digest = hashlib.sha256(json.dumps(preprocessing_spec, sort_keys=True).encode()).hexdigest()
        self.preprocessing = m.preprocessing + ":sha256:" + digest

    def _encode_crop(self, crop):
        m = self.manifest
        with Image.open(crop.path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            if m.resize == "short_edge_256_center_crop":
                scale = 256 / min(image.size)
                image = image.resize(
                    (int(image.width * scale), int(image.height * scale)), Image.Resampling.BICUBIC
                )
                left = (image.width - m.width) // 2
                top = (image.height - m.height) // 2
                image = image.crop((left, top, left + m.width, top + m.height))
            elif m.resize == "center_crop":
                image = ImageOps.fit(image, (m.width, m.height), method=Image.Resampling.BICUBIC)
            else:
                image = image.resize((m.width, m.height), Image.Resampling.BICUBIC)
            tensor = np.asarray(image, dtype=np.float32) / 255.0
        tensor = (tensor - np.array(m.mean, dtype=np.float32)) / np.array(m.std, dtype=np.float32)
        tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None, :])
        result = np.asarray(
            self.session.run([m.output], {self.input_name: tensor})[0], dtype=np.float32
        )
        if m.pooling in {"cls", "mean_tokens"}:
            if result.ndim != 3 or result.shape[0] != 1:
                raise ValueError("token output shape mismatch")
            result = result[:, 0, :] if m.pooling == "cls" else result.mean(axis=1)
        if result.shape not in {(1, m.dimension), (m.dimension,)}:
            raise ValueError("encoder feature dimension mismatch")
        vector = result.reshape(-1)
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 1e-12:
            raise ValueError("invalid encoder output")
        return vector / norm

    def encode_views(self, observation):
        """Return separately normalized real-crop features for multi-view agreement."""
        validate_observation(observation)
        m = self.manifest
        return tuple(
            ImageFeature(
                tuple(map(float, self._encode_crop(c))), m.model, m.sha256, self.preprocessing
            )
            for c in observation.crops
        )

    def encode(self, observation):
        """One normalized mean feature; encode_views preserves per-view disagreement."""
        features = self.encode_views(observation)
        vector = np.mean([f.values for f in features], axis=0)
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-12:
            raise ValueError("conflicting image features")
        first = features[0]
        return ImageFeature(
            tuple(map(float, vector / norm)), first.model, first.model_digest, first.preprocessing
        )
