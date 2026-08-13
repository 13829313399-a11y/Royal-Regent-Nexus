# ADR-004/005 — Conversation ownership, Provider storage, and retention

- Status: `ACCEPTED`
- Accepted: 2026-08-12
- Runtime behavior changed by NIF-00: no

The policy-independent resource and API boundary is frozen in
`0008-conversation-v1-contract.md`. That contract intentionally contains no
tables, migration, runtime routes, or active retention values.

## Current invariant

The existing Qwen adapter explicitly sends `store=false`. That compatibility invariant remains in force. It does not mean the Provider guarantees zero retention, and it does not define Nexus-side retention.

## Proposed architecture

- RR-Nexus PostgreSQL, not a Provider response ID, would own persistent conversation state.
- Provider calls would remain `store=false` by default.
- Temporary mode would avoid persisting message bodies while retaining only the security/audit metadata required by an approved policy.
- Formal business facts would be re-read through authorized Tools, not stored as authoritative personal memory.
- Action audit would remain separate from deletable conversation text.

## Accepted policy

- Message bodies and controlled summaries are retained for 30 days.
- Temporary sessions persist no user or assistant body and no summary.
- User deletion hard-deletes body and summary while retaining a tombstone for
  180 days.
- Security audit is retained for 180 days; Action audit is retained for 365
  days and remains separate from conversation deletion.
- Backups have a maximum age of 30 days and a deletion-completion SLA of 30
  days; restore must reapply tombstones before serving bodies.
- Conversation bodies remain owner-only, including against administrators.
- Persistent text is `INTERNAL_SENSITIVE`; secrets and special-category
  personal data are prohibited.
- Legal hold is not supported in v1 and user preferences are deferred.

## Gate and rollback

The user approved every recommended value while acting for product, security,
and operations on 2026-08-12. This is an engineering rollout baseline and not an
additional legal compliance sign-off. The exact values and approval receipt are
recorded in `0008-conversation-v1-contract.md`.

NIF-05 may now implement the accepted policy behind a default-off Feature Flag.
With the flag off, unbound v1 remains memory-only.
