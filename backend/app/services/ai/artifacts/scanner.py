from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from typing import Protocol


class ArtifactScannerError(RuntimeError):
    pass


class ArtifactScannerUnavailable(ArtifactScannerError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactScanResult:
    clean: bool
    result_code: str


class ArtifactScanner(Protocol):
    def scan(self, data: bytes) -> ArtifactScanResult: ...


class ClamAVArtifactScanner:
    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def scan(self, data: bytes) -> ArtifactScanResult:
        response = bytearray()
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout_seconds
            ) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.sendall(b"zINSTREAM\0")
                view = memoryview(data)
                for offset in range(0, len(data), 64 * 1024):
                    chunk = view[offset : offset + 64 * 1024]
                    connection.sendall(struct.pack("!I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                while len(response) <= 4096:
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    response.extend(chunk)
                    if b"\0" in chunk or b"\n" in chunk:
                        break
        except (OSError, TimeoutError) as exc:
            raise ArtifactScannerUnavailable("scanner unavailable") from exc
        finally:
            if "view" in locals():
                view.release()

        message = bytes(response).split(b"\0", 1)[0].strip()
        if message.endswith(b" OK"):
            return ArtifactScanResult(clean=True, result_code="CLEAN")
        if message.endswith(b" FOUND"):
            return ArtifactScanResult(clean=False, result_code="MALWARE_DETECTED")
        raise ArtifactScannerUnavailable("scanner returned an incomplete result")


class FakeArtifactScanner:
    def __init__(self, outcome: str = "clean") -> None:
        self.outcome = outcome

    def scan(self, data: bytes) -> ArtifactScanResult:
        if self.outcome == "unavailable":
            raise ArtifactScannerUnavailable("scanner unavailable")
        if self.outcome == "rejected":
            return ArtifactScanResult(clean=False, result_code="MALWARE_DETECTED")
        if self.outcome != "clean":
            raise ArtifactScannerUnavailable("scanner returned an incomplete result")
        return ArtifactScanResult(clean=True, result_code="CLEAN")


class UnavailableArtifactScanner:
    def scan(self, data: bytes) -> ArtifactScanResult:
        raise ArtifactScannerUnavailable("scanner is not configured")
