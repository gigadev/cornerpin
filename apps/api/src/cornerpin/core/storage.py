"""Object storage for uploaded photos and documents (ADR-025): local disk in development, a
Cloud Storage bucket in the cloud. Callers use keys like
`tenants/<tenant>/lots/<lot>/photos/<id>.jpg` and never see paths or buckets.

Removing a file is an outbox event, queued in the transaction that deletes its row, so a failed
delete is retried and a rolled-back delete leaves the file alone."""

import re
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Protocol, cast

from sqlalchemy.orm import Session

from cornerpin.core.config import get_settings
from cornerpin.core.outbox import Event, enqueue, handler

KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9/_.-]{0,500}$")


def check_key(key: str) -> str:
    if not KEY_PATTERN.fullmatch(key) or ".." in key or "//" in key or key.endswith("/"):
        raise ValueError(f"invalid storage key: {key!r}")
    return key


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / check_key(key)).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"invalid storage key: {key!r}")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(data)
        temporary.replace(path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class _Blob(Protocol):
    def upload_from_string(self, data: bytes, content_type: str) -> None: ...
    def download_as_bytes(self) -> bytes: ...
    def delete(self) -> None: ...


class _Bucket(Protocol):
    def blob(self, blob_name: str) -> _Blob: ...


class GcsStorage:
    """Cloud Storage. Dormant until STORAGE_BACKEND=gcs and STORAGE_BUCKET are set; credentials
    come from the Cloud Run service account."""

    def __init__(self, bucket: str) -> None:
        # Imported here so local runs never load it. The client is untyped, so it is reached
        # only through the _Bucket and _Blob protocols above.
        from google.cloud import storage  # pyright: ignore[reportMissingTypeStubs]

        client = storage.Client()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        self._bucket = cast(_Bucket, client.bucket(bucket))  # pyright: ignore[reportUnknownMemberType]

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._bucket.blob(check_key(key)).upload_from_string(data, content_type=content_type)

    def get(self, key: str) -> bytes:
        return self._bucket.blob(check_key(key)).download_as_bytes()

    def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        with suppress(NotFound):
            self._bucket.blob(check_key(key)).delete()


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "gcs" and settings.storage_bucket:
        return GcsStorage(settings.storage_bucket)
    return LocalStorage(settings.storage_dir)


class StoredObjectRemoved(Event):
    event_type: ClassVar[str] = "storage.object_removed"

    key: str


def remove_later(session: Session, key: str) -> None:
    """Queue the file's removal in the caller's transaction."""
    enqueue(session, StoredObjectRemoved(key=check_key(key)))


@handler(StoredObjectRemoved)
def _remove_object(event: StoredObjectRemoved) -> None:
    get_storage().delete(event.key)
