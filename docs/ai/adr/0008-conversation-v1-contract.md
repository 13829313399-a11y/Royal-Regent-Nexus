# ADR/NIF-05 — Conversation v1 resource and policy decision contract

- Contract status: `FROZEN`
- Retention-policy status: `ACCEPTED`
- Runtime implementation status: `AUTHORIZED`
- Date: 2026-08-12
- Depends on: ADR-004/005 and NIF-04
- Runtime behavior changed by this ADR: no

## Purpose

This ADR freezes the resource, authorization, compatibility, data-minimization,
and accepted retention contract for NIF-05. The approval receipt below authorizes
the engineering implementation of conversation persistence behind its
default-off Feature Flag.

## Authority and source of truth

- RR-Nexus PostgreSQL will own persistent conversation state if the policy gate
  is accepted.
- Provider requests continue to use `store=false` and remain stateless from the
  RR-Nexus perspective.
- Provider response IDs and `previous_response_id` cannot become conversation
  identity, recovery state, or business-task state.
- Git-reviewed Skill, Prompt, Tool, Evidence, and Renderer definitions remain
  authoritative. Conversation rows record version/hash references only.
- Formal business facts are never authoritative conversation memory. A later
  request must re-read them through a currently authorized Tool.

## Closed resource vocabulary

### Conversation mode

```text
PERSISTENT
TEMPORARY
```

The persistence effect of `TEMPORARY` is controlled by the required
`TEMPORARY_BODY_PERSISTENCE` decision. Until that decision is accepted, the mode
is vocabulary only and cannot be exposed by a runtime route.

### Conversation lifecycle

```text
ACTIVE
DELETION_PENDING
DELETED
EXPIRED
```

These states describe API behavior. Whether deletion uses an immediate hard
delete, anonymization, or a queue is controlled by `USER_DELETE_MODE`.

### Message roles and kinds

```text
role: USER | ASSISTANT
kind: TEXT | SAFE_STAGE_SUMMARY
```

System Prompt text, private reasoning, raw Tool results, credentials, image
bytes, workbook bytes, OCR bodies, and arbitrary Provider payloads are not
message kinds and cannot be persisted as conversation text.

### Opaque IDs

```text
conversation: aicv-<32 lowercase hexadecimal characters>
message:      aimsg-<32 lowercase hexadecimal characters>
summary:      aisum-<32 lowercase hexadecimal characters>
```

IDs must use cryptographically random values, must not encode user/factory/time,
and must never be sequential or accepted from a client on creation.

## Resource contracts

### Conversation list item

The list endpoint returns metadata only:

```json
{
  "id": "aicv-...",
  "mode": "PERSISTENT",
  "status": "ACTIVE",
  "title": "bounded user-visible title",
  "factory_scope": "huaxing",
  "created_at": "timezone-aware timestamp",
  "updated_at": "timezone-aware timestamp",
  "expires_at": "timezone-aware timestamp or null",
  "message_count": 0,
  "last_message_at": "timezone-aware timestamp or null"
}
```

It must not include message text, summaries, Tool arguments/results, Evidence
payloads, Provider IDs, deletion reasons, IP addresses, or audit details.

### Conversation detail

Detail may add the owner's bounded messages and current summary only when the
accepted retention policy permits them. Each Assistant message may carry only:

- Skill ID/version/hash;
- Prompt version/hash;
- Provider profile/catalog/model aliases, not credentials or base URLs;
- safe usage counters;
- Evidence v1 references, not copied Tool results;
- safe stage summaries, never private reasoning.

Every returned object uses a closed schema. Unknown roles, kinds, modes, status,
versions, or fields fail closed.

### Message append

- The server owns message ID, timestamps, owner, and conversation binding.
- The client may send one bounded user text message and optional optimistic
  concurrency token.
- The service rechecks conversation ownership, status, factory membership,
  Pilot/runtime flags, and current page/factory/Tool authorization.
- A stored summary cannot grant Tool access or assert formal business facts.
- Duplicate idempotency keys return the original safe result; an idempotency key
  cannot be reused with different canonical input.

## API contract

```text
POST   /api/ai/conversations
GET    /api/ai/conversations
GET    /api/ai/conversations/{conversation_id}
DELETE /api/ai/conversations/{conversation_id}
POST   /api/ai/conversations/{conversation_id}/messages
```

### HTTP and enumeration behavior

| Operation | Success | Closed failure behavior |
| --- | --- | --- |
| Create | `201` | invalid mode/factory/body `422`; disabled resource `404` |
| List | `200` | owner-only cursor page; never returns another owner |
| Detail | `200` | unknown and non-owner both return indistinguishable `404` |
| Delete | `204` | idempotent; unknown and non-owner are non-enumerating |
| Append | `201` | unknown/non-owner `404`; inactive/conflict `409`; stale precondition `412` |

The API cannot expose whether a guessed ID belongs to another user. Security
denials use metadata-only audit outside conversation text.

### Pagination and history budget

- Lists use an opaque server cursor; client offsets are not accepted.
- Default list page is 20 and maximum is 50.
- Detail message pages use an opaque cursor and maximum 50 messages.
- Provider history selection remains bounded by the existing maximum 12 input
  messages, 8,000 characters per message, and 40,000 total characters unless a
  later reviewed version changes those limits.
- The Context Assembler selects the most recent safe messages and one controlled
  summary. Truncation is explicit.

## Authorization invariants

- `owner_user_id` is immutable and is never accepted from request JSON.
- A conversation is owner-only in v1. Administrator role membership alone does
  not authorize body access; the final rule is controlled by
  `ADMIN_BODY_ACCESS`.
- `factory_scope` must be one canonical factory validated at creation. It is a
  scope record, not an authorization grant.
- Every read, append, Tool call, Evidence open, Artifact open, and Action rechecks
  current IAM, explicit deny, current factory scope, and current resource state.
- Explicit deny overrides historical grants and cached summaries.
- Switching account or factory cannot reuse the prior owner's cached body.

## Data minimization and classification

The following are structurally excluded regardless of the final retention days:

- Provider API keys, workspace IDs, cookies, session tokens, passwords, signing
  keys, base URLs, and internal connection strings;
- raw system Prompt, private reasoning, hidden chain of thought, or arbitrary
  model trace;
- raw Tool arguments/results and ORM objects;
- raw file/image/workbook/PDF/OCR bytes or unbounded extracted text;
- full Action payloads or mutable copies of formal business facts.

Messages may contain user-entered text, so the accepted
`PERSISTENT_DATA_CLASSIFICATION` and prohibited-data policy must be recorded
before persistence is enabled.

## Temporary mode contract boundary

The recommended baseline is that `TEMPORARY` writes no user/assistant body and no
summary. It may retain only approved security metadata outside the message-body
tables. This is not active policy until `TEMPORARY_BODY_PERSISTENCE` is accepted.

If a different value is approved, it requires a new ADR revision and cannot be
silently implemented as ordinary `PERSISTENT` mode with a shorter expiry.

## Delete, audit, backup, and legal-hold boundaries

- Conversation text and Action/security audit are separate data classes.
- Deleting a conversation can never delete or rewrite a formal domain Action
  audit.
- A deleted conversation cannot be returned, summarized, sent to a Provider, or
  used as Tool context.
- Backup copies cannot be synchronously edited in place. The accepted policy must
  specify backup maximum age and deletion completion SLA.
- Restore procedures must reapply deletion tombstones before the restored system
  serves conversation bodies.
- Legal hold is not implicitly supported. If required, scope, authority,
  notification, release, and access auditing require a separate accepted policy.

## Required policy decision record

The following values were accepted as the NIF-05 engineering rollout baseline.

| Decision key | Required value | Recommended engineering baseline | Current status |
| --- | --- | --- | --- |
| `MESSAGE_BODY_RETENTION_DAYS` | positive integer | `30` | `ACCEPTED` |
| `SUMMARY_RETENTION_DAYS` | positive integer | `30` | `ACCEPTED` |
| `TEMPORARY_BODY_PERSISTENCE` | `NONE` or reviewed alternative | `NONE` | `ACCEPTED` |
| `USER_DELETE_MODE` | `HARD_DELETE_BODY_KEEP_TOMBSTONE`, `ANONYMIZE`, or `RETENTION_QUEUE` | `HARD_DELETE_BODY_KEEP_TOMBSTONE` | `ACCEPTED` |
| `DELETE_TOMBSTONE_RETENTION_DAYS` | non-negative integer | `180` | `ACCEPTED` |
| `SECURITY_AUDIT_RETENTION_DAYS` | positive integer | `180` | `ACCEPTED` |
| `ACTION_AUDIT_RETENTION_DAYS` | positive integer or authoritative domain-policy reference | `365` | `ACCEPTED` |
| `BACKUP_RETENTION_DAYS` | positive integer | `30` | `ACCEPTED` |
| `BACKUP_DELETE_SLA_DAYS` | positive integer | `30` | `ACCEPTED` |
| `ADMIN_BODY_ACCESS` | `OWNER_ONLY`, `BREAK_GLASS`, or `ADMIN_READ` | `OWNER_ONLY` | `ACCEPTED` |
| `PERSISTENT_DATA_CLASSIFICATION` | approved classification label and prohibited-data rule | `INTERNAL_SENSITIVE`; secrets and special-category personal data prohibited | `ACCEPTED` |
| `LEGAL_HOLD_MODE` | `NOT_SUPPORTED` or separately reviewed contract | `NOT_SUPPORTED` | `ACCEPTED` |
| `USER_PREFERENCES_IN_NIF05` | `DEFERRED` or closed field list | `DEFERRED` | `ACCEPTED` |

### Approval receipt

- Approval date: 2026-08-12
- Approver authority statement: the user represents product, security, and
  operations for this decision.
- Exact approval instruction: “按推荐方案批准；我代表产品、安全和运维批准
  ADR-004/005。这是工程上线基线，不代表额外法律合规签署。”
- Approval scope: engineering rollout baseline for ADR-004/005 and NIF-05.
- Legal status: this approval is not an additional legal compliance sign-off.
- Delegated policy references: none; every decision key has an exact value in
  this ADR.

### Approval receipt requirements

The accepting ADR revision must record:

- the exact value of every decision key;
- approving product, security, and operations owner identities or an explicit
  statement that one authorized owner is acting for all three roles;
- approval date;
- policy/document references when a value delegates to an existing domain rule;
- whether the approval is an engineering rollout baseline or a separate legal
  compliance sign-off.

A general instruction to “continue implementation” does not fill missing policy
values and is not a retention approval receipt.

## Implementation gate checklist

Only after the approval receipt exists may NIF-05 implementation:

1. re-verify one Alembic head and allocate the next revision after `0066`;
2. add Conversation/Message/Summary models and protected downgrade behavior;
3. add services, retention execution, and owner-only resource routes;
4. add default-off `AI_CONVERSATIONS_ENABLED` configuration;
5. bind `/api/ai/responses` additively while preserving unbound v1 behavior;
6. implement SQLite and PostgreSQL contract/migration tests;
7. prove temporary-mode non-persistence, deletion, audit separation, restore
   tombstone behavior, IAM reauthorization, and Provider `store=false`.

## Rollback

Before data exists, remove no tables because this ADR creates none. After an
approved implementation, disable the Conversation Feature Flag first, stop new
writes, retain tables for policy evaluation, and prohibit downgrade while any
protected user text or tombstone remains.
