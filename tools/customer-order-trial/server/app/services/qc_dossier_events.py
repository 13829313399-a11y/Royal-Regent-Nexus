"""Offline infrastructure boundary for the shared ledger's ERP QC outbox.

The trial has no enterprise QC dossier or remote synchronization. Its local
versions, dispatches and shipment records are persisted by the exact-copy ledger.
Only the production-specific outbox hooks are intentionally inactive here.
"""


def mark(db, line):
    return None


def install():
    return None
