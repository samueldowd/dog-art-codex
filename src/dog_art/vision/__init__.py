"""Native media/crop APIs. No model download or geometry guess occurs here.

Clean Frigate snapshots: decode_image(client.snapshot(event)), snapshot_sample(),
then CropExtractor.extract(event, (DecodedFrame(image, sample.observed_at),),
(sample,), private_root). Full-body unknown requires review. Video: supply verified
clip origin to VideoDecoder.frame; use an independently validated LocalTracker to
provide timestamped samples. path_data centers do not provide valid clip boxes.
"""

from .crops import CropExtractor, LocalTracker, TrackSample, snapshot_sample
from .media import DecodedFrame, MediaError, VideoDecoder, decode_image

__all__ = [
    "DecodedFrame",
    "MediaError",
    "VideoDecoder",
    "decode_image",
    "CropExtractor",
    "LocalTracker",
    "TrackSample",
    "snapshot_sample",
]
