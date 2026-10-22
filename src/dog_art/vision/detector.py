"""Hashed official YOLOX nano ONNX detector; per-frame boxes, no fixed PTZ crop.

Preprocessing/decoding follows the producer's ONNXRuntime demonstration. Frigate
track anchor points associate independent detections; ambiguous associations abstain.
The detector cannot certify anatomy/full-body visibility; that stays review evidence.
"""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .crops import TrackSample
from .media import MediaError


class YoloXDetector:
    def __init__(self, manifest, *, session=None):
        path = Path(manifest)
        if path.is_symlink() or path.stat().st_size > 65536:
            raise MediaError("detector_manifest_invalid")
        self.manifest = json.loads(path.read_text())
        m = self.manifest
        if set(m) != {
            "path",
            "sha256",
            "source",
            "license",
            "input_size",
            "score_threshold",
            "nms_threshold",
        }:
            raise MediaError("detector_manifest_invalid")
        self.path = Path(m["path"])
        if not self.path.is_absolute():
            self.path = path.parent / self.path
        if self.path.is_symlink() or not self.path.is_file():
            raise MediaError("detector_model_invalid")
        data = self.path.read_bytes()
        if len(data) > 500 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != m["sha256"]:
            raise MediaError("detector_hash_mismatch")
        if m["input_size"] != 416 or not all(
            type(m[k]) in (int, float) and math.isfinite(m[k]) and 0 < m[k] < 1
            for k in ("score_threshold", "nms_threshold")
        ):
            raise MediaError("detector_policy_invalid")
        if session is None:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            session = ort.InferenceSession(
                data, sess_options=opts, providers=["CPUExecutionProvider"]
            )
        self.session = session
        if len(session.get_inputs()) != 1 or session.get_inputs()[0].shape != [1, 3, 416, 416]:
            raise MediaError("detector_input_mismatch")
        self.input_name = session.get_inputs()[0].name

    def detect(self, image):
        image = image.convert("RGB")
        size = 416
        ratio = min(size / image.height, size / image.width)
        resized = image.resize(
            (int(image.width * ratio), int(image.height * ratio)), Image.Resampling.BILINEAR
        )
        array = np.full((size, size, 3), 114, dtype=np.float32)
        array[: resized.height, : resized.width] = np.asarray(resized, dtype=np.float32)
        # Official 0.1.1rc0 export uses RGB unit pixels plus ImageNet normalization.
        # Current-main YOLOX raw BGR preprocessing is incompatible with this artifact.
        array = (array / 255.0 - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
            [0.229, 0.224, 0.225], dtype=np.float32
        )
        tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[None], dtype=np.float32)
        pred = np.asarray(self.session.run(None, {self.input_name: tensor})[0], dtype=np.float32)
        if pred.shape != (1, 3549, 85) or not np.isfinite(pred).all():
            raise MediaError("detector_output_invalid")
        pred = pred[0].copy()
        grids = []
        strides = []
        for stride in (8, 16, 32):
            h = w = size // stride
            yy, xx = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
            grids.append(np.stack((xx, yy), axis=2).reshape(-1, 2))
            strides.append(np.full((h * w, 1), stride))
        grid = np.concatenate(grids)
        stride = np.concatenate(strides)
        pred[:, :2] = (pred[:, :2] + grid) * stride
        pred[:, 2:4] = np.exp(np.clip(pred[:, 2:4], -20, 20)) * stride
        results = []
        for cls in (0, 16):  # COCO person and dog only; person overlap causes occlusion review.
            scores = pred[:, 4] * pred[:, 5 + cls]
            indices = np.flatnonzero(scores >= self.manifest["score_threshold"])
            indices = indices[np.argsort(-scores[indices])]
            accepted = []
            for idx in indices[:1000]:
                cx, cy, w, h = pred[idx, :4] / ratio
                box = (
                    max(0, float(cx - w / 2)),
                    max(0, float(cy - h / 2)),
                    min(image.width, float(cx + w / 2)),
                    min(image.height, float(cy + h / 2)),
                )
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue
                if any(iou(box, b) > self.manifest["nms_threshold"] for b in accepted):
                    continue
                accepted.append(box)
                results.append({"class_id": cls, "score": float(scores[idx]), "box": box})
        return results

    def sample(self, frame, anchor, track_id, *, region_edge):
        """Detect in a native-resolution region around this frame's own track anchor.

        anchor is Frigate's normalized bottom-center at the exact source timestamp.
        region_edge chooses a search area only; no old detection box is reused.
        """
        image = frame.image
        ax, ay = anchor
        if not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in anchor):
            raise MediaError("track_anchor_invalid")
        edge = min(max(int(region_edge), 416), max(image.size))
        cx = ax * image.width
        cy = ay * image.height - edge * 0.25
        x = max(0, min(image.width - edge, int(cx - edge / 2)))
        y = max(0, min(image.height - edge, int(cy - edge / 2)))
        right = min(image.width, x + edge)
        bottom = min(image.height, y + edge)
        detections = self.detect(image.crop((x, y, right, bottom)))
        dogs = []
        for item in detections:
            if item["class_id"] != 16:
                continue
            b = item["box"]
            distance = math.hypot((b[0] + b[2]) / 2 + x - cx, b[3] + y - ay * image.height) / edge
            if distance <= 0.35:
                dogs.append((distance, item))
        dogs.sort(key=lambda value: value[0])
        if not dogs or len(dogs) > 1 and dogs[1][0] - dogs[0][0] < 0.1:
            raise MediaError("dog_track_association_ambiguous")
        local = dogs[0][1]["box"]
        box = tuple(v + offset for v, offset in zip(local, (x, y, x, y)))
        occluded = any(iou(local, d["box"]) > 0.02 for d in detections if d is not dogs[0][1])
        return TrackSample(
            track_id, frame.observed_at, box, image.size, full_body=False, occluded=occluded
        )


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0
