"""Read-only Frigate ingest: client, event filtering, durable queue and polling.

Use EventIngestor.record/API or ingest_notification/MQTT, then PollReconciler for
startup/reconnect/outage recovery. Claim `extract` jobs through the shared Store;
read the persisted events.payload and parse_event before media processing.
"""

from .client import FrigateClient, FrigateError, parse_event
from .ingest import EventIngestor, PollReconciler

__all__ = ["FrigateClient", "FrigateError", "parse_event", "EventIngestor", "PollReconciler"]
