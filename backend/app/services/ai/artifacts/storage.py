from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

_STORAGE_KEY = re.compile(r"v1/[0-9a-f]{2}/aiart-[0-9a-f]{32}\.bin")


class ArtifactStorageError(RuntimeError):
    pass


class ArtifactStorage(Protocol):
    def put(self, storage_key: str, data: bytes) -> None: ...

    def read(self, storage_key: str) -> bytes: ...

    def delete(self, storage_key: str) -> None: ...

    def exists(self, storage_key: str) -> bool: ...


def storage_key_for(artifact_id: str) -> str:
    suffix = artifact_id.removeprefix("aiart-")
    if not re.fullmatch(r"[0-9a-f]{32}", suffix):
        raise ArtifactStorageError("invalid artifact id")
    return f"v1/{suffix[:2]}/{artifact_id}.bin"


class LocalImmutableArtifactStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, storage_key: str) -> Path:
        if _STORAGE_KEY.fullmatch(storage_key) is None:
            raise ArtifactStorageError("invalid storage key")
        candidate = (self.root / Path(*storage_key.split("/"))).resolve()
        if self.root not in candidate.parents:
            raise ArtifactStorageError("storage path escaped root")
        return candidate

    def put(self, storage_key: str, data: bytes) -> None:
        path = self._path(storage_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(data)
                output.flush()
        except (FileExistsError, OSError) as exc:
            raise ArtifactStorageError("immutable storage write failed") from exc

    def read(self, storage_key: str) -> bytes:
        try:
            return self._path(storage_key).read_bytes()
        except OSError as exc:
            raise ArtifactStorageError("artifact bytes unavailable") from exc

    def delete(self, storage_key: str) -> None:
        try:
            self._path(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            raise ArtifactStorageError("artifact delete failed") from exc

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).is_file()


class FakeArtifactStorage:
    def __init__(self, *, fail_put: bool = False, fail_delete: bool = False) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_put = fail_put
        self.fail_delete = fail_delete

    def put(self, storage_key: str, data: bytes) -> None:
        if self.fail_put or storage_key in self.objects:
            raise ArtifactStorageError("immutable storage write failed")
        self.objects[storage_key] = bytes(data)

    def read(self, storage_key: str) -> bytes:
        try:
            return self.objects[storage_key]
        except KeyError as exc:
            raise ArtifactStorageError("artifact bytes unavailable") from exc

    def delete(self, storage_key: str) -> None:
        if self.fail_delete:
            raise ArtifactStorageError("artifact delete failed")
        self.objects.pop(storage_key, None)

    def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects
