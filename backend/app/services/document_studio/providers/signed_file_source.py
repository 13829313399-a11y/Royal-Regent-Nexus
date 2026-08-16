from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlparse

import httpx2
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings


class SignedFileSourceError(RuntimeError):
    code = "DOCUMENT_SIGNED_SOURCE_UNAVAILABLE"
    retryable = True


class SignedFileLease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(pattern=r"^doclease-[0-9a-f]{32}$")
    file_url: str = Field(min_length=1, max_length=4096)
    expires_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0, le=20 * 1024 * 1024)


class SignedFileSource(Protocol):
    def create(
        self,
        *,
        artifact_id: str,
        sha256: str,
        filename: str,
        mime_type: str,
        data: bytes,
        ttl_seconds: int,
    ) -> SignedFileLease: ...

    def revoke(self, lease: SignedFileLease) -> None: ...


class BrokerSignedFileSource:
    """Uploads to a reviewed signing broker without exposing its URL to clients/logs."""

    def __init__(self, settings: Settings) -> None:
        self.service_url = settings.ai_document_signed_file_service_url.strip().rstrip("/")
        self.token = settings.ai_document_signed_file_service_token.get_secret_value().strip()
        self.allowed_hosts = frozenset(
            item.strip().casefold()
            for item in settings.ai_document_signed_file_allowed_hosts.split(",")
            if item.strip()
        )
        parsed = urlparse(self.service_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not self.token
            or not self.allowed_hosts
        ):
            raise SignedFileSourceError("文档签名文件服务尚未安全配置。")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def create(
        self,
        *,
        artifact_id: str,
        sha256: str,
        filename: str,
        mime_type: str,
        data: bytes,
        ttl_seconds: int,
    ) -> SignedFileLease:
        try:
            with httpx2.Client(timeout=30, follow_redirects=False) as client:
                response = client.post(
                    f"{self.service_url}/leases",
                    headers=self._headers(),
                    data={
                        "artifact_id": artifact_id,
                        "sha256": sha256,
                        "ttl_seconds": str(ttl_seconds),
                    },
                    files={"file": (filename, data, mime_type)},
                )
                response.raise_for_status()
                lease = SignedFileLease.model_validate(response.json())
        except Exception as exc:
            raise SignedFileSourceError("无法创建受控文档文件租约。") from exc
        parsed = urlparse(lease.file_url)
        current = datetime.now(timezone.utc)
        expires_at = (
            lease.expires_at
            if lease.expires_at.tzinfo is not None
            else lease.expires_at.replace(tzinfo=timezone.utc)
        )
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname.casefold() not in self.allowed_hosts
            or parsed.username
            or parsed.password
            or parsed.fragment
            or lease.sha256 != sha256
            or lease.size_bytes != len(data)
            or expires_at <= current
            or (expires_at - current).total_seconds() > ttl_seconds + 5
        ):
            self._best_effort_revoke(lease)
            raise SignedFileSourceError("签名文件租约未通过安全校验。")
        return lease

    def revoke(self, lease: SignedFileLease) -> None:
        try:
            with httpx2.Client(timeout=10, follow_redirects=False) as client:
                response = client.delete(
                    f"{self.service_url}/leases/{lease.lease_id}",
                    headers=self._headers(),
                )
                response.raise_for_status()
        except Exception as exc:
            raise SignedFileSourceError("无法撤销文档文件租约。") from exc

    def _best_effort_revoke(self, lease: SignedFileLease) -> None:
        try:
            self.revoke(lease)
        except SignedFileSourceError:
            pass
