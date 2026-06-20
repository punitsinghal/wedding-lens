"""Qdrant vector store operations for face embeddings."""
import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import settings

logger = logging.getLogger("weddinglens.qdrant")

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return _client


def collection_name(event_id: uuid.UUID) -> str:
    """Return Qdrant collection name for an event: event_<32-char hex>."""
    return f"event_{event_id.hex}"


def ensure_collection(event_id: uuid.UUID) -> None:
    """Create collection if it does not exist. Idempotent."""
    client = get_qdrant_client()
    name = collection_name(event_id)
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=512, distance=Distance.COSINE),
        )
        logger.info('{"event": "qdrant_collection_created", "collection": "%s"}', name)


def upsert_face_vectors(
    event_id: uuid.UUID,
    points: list[dict[str, Any]],
) -> None:
    """
    Upsert face vectors into the event's Qdrant collection.

    Each point dict: {"id": uuid, "vector": list[float], "payload": {...}}
    """
    client = get_qdrant_client()
    name = collection_name(event_id)
    qdrant_points = [
        PointStruct(id=str(p["id"]), vector=p["vector"], payload=p["payload"])
        for p in points
    ]
    client.upsert(collection_name=name, points=qdrant_points)
    logger.info(
        '{"event": "qdrant_upsert", "collection": "%s", "count": %d}',
        name,
        len(qdrant_points),
    )


def delete_collection(event_id: uuid.UUID) -> None:
    """Delete the Qdrant collection for an event."""
    client = get_qdrant_client()
    name = collection_name(event_id)
    client.delete_collection(name)
    logger.info('{"event": "qdrant_collection_deleted", "collection": "%s"}', name)
