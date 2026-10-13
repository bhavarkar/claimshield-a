"""Case file storage: uploads and generated reports. Local directory or a Cloud Storage bucket."""

from __future__ import annotations

from pathlib import Path


class LocalStorage:
    name = "local filesystem"

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"file://{path}"

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()


class GcsStorage:
    name = "Cloud Storage"

    def __init__(self, project: str, bucket: str) -> None:
        from google.cloud import storage

        self._bucket = storage.Client(project=project).bucket(bucket)
        self._name = bucket

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._bucket.blob(key).upload_from_string(data, content_type=content_type)
        return f"gs://{self._name}/{key}"

    def get(self, key: str) -> bytes:
        return self._bucket.blob(key).download_as_bytes()

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists()
