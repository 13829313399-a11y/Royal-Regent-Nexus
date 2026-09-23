"""Machine-bound DPAPI credential; installer restricts its directory ACL."""
import json
from pathlib import Path
import secrets
from hashlib import sha256
from uuid import uuid4


def save(path, identity):
    import win32crypt
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = win32crypt.CryptProtectData(json.dumps(identity).encode(), "RR UV Agent", None, None, None, 4)
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as output:
        output.write(encrypted)
        output.flush()
        __import__('os').fsync(output.fileno())
    temporary.replace(path)


def load(path):
    import win32crypt
    _, value = win32crypt.CryptUnprotectData(Path(path).read_bytes(), None, None, None, 0)
    return json.loads(value)


def enroll(transport, path, code):
    path = Path(path)
    pairing_fingerprint = sha256((transport.base_url+'\n'+code).encode()).hexdigest()
    identity = load(path) if path.exists() else None
    if identity and identity.get('pairing_fingerprint') != pairing_fingerprint:
        # A new agent identity must never relabel the old agent's durable queue.
        # Use a separate state directory, retaining the old encrypted identity,
        # outbox and source cursors for authorized reconciliation.
        raise ValueError('new_pairing_requires_separate_state_directory')
    identity = identity or dict(token=secrets.token_urlsafe(48), enrollment_id=uuid4().hex, pairing_fingerprint=pairing_fingerprint, server_url=transport.base_url)
    save(path, identity)
    result = transport.request("/api/internal/uv-agent/enroll", dict(pairing_code=code, token=identity["token"], enrollment_id=identity["enrollment_id"]))
    identity.update(result)
    save(path, identity)
    return result
