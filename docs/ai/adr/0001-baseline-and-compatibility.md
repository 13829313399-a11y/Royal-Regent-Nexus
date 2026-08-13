# ADR/NIF-00 — Baseline, compatibility, and capability semantics

- Status: `ACCEPTED` for the execution baseline and NIF-01 compatibility contract
- Date: 2026-08-12
- Scope: NIF-00 baseline governance and NIF-01 compatibility freeze
- Runtime behavior changed: only an additive context-capability resource behind a default-off Flag; v1 behavior is unchanged

## Decision status index

This index is the canonical NIF-00 status table. `PROPOSED` does not authorize implementation. A proposal marked `DECISION_REQUIRED` needs the named product, business, security, or operations owner before its dependent package may encode the policy.

| Plan ADR | Decision | Status | Gate |
| --- | --- | --- | --- |
| ADR-001 | Start every NIF package from a freshly verified `origin/main` in an isolated worktree | `ACCEPTED` | Executed by NIF-00 under the user's request |
| ADR-002 | Preserve `/api/ai/responses` and SSE v1 during the migration window | `ACCEPTED` | Frozen by NIF-01 JSON/SSE fixtures and contract tests |
| ADR-003 | Git-first Skill and Prompt definitions | `ACCEPTED` | Implemented by NIF-03 behind default-off Flags |
| ADR-004 | Nexus-owned conversations while Provider requests keep `store=false` | `ACCEPTED` | Engineering rollout baseline approved 2026-08-12; not an additional legal sign-off |
| ADR-005 | Conversation and memory retention policy | `ACCEPTED` | All `0008` decision keys accepted by the user acting for product, security, and operations |
| ADR-006 | PostgreSQL lease-based Worker v1 | `ACCEPTED` | Recommended baseline approved 2026-08-12 by product/security/operations authority; engineering rollout baseline, not additional legal sign-off |
| ADR-007 | PostgreSQL atomic shared Guard v1 | `ACCEPTED` | Recommended baseline approved 2026-08-12 by product/security/operations authority; engineering rollout baseline, not additional legal sign-off |
| ADR-008 | Reviewed local Git knowledge and local controlled retrieval before vector services | `ACCEPTED` | Recommended baseline approved 2026-08-12 by product/security/operations and module Knowledge Owners; PILOT_READY ceiling before NIF-17, not additional legal sign-off |
| ADR-009 | Immutable Artifact originals behind a storage/scanner adapter | `ACCEPTED` | Recommended baseline approved 2026-08-12 by product/security/operations authority; default-off implementation authorized, production restore/operations evidence remains required, not additional legal sign-off |
| ADR-010 | Business code requests internal model capability aliases | `ACCEPTED` | Frozen by NIF-02 Catalog/Router tests |
| ADR-011 | Stable internal reasoning tiers mapped by Provider capabilities | `ACCEPTED` | Frozen by NIF-02 Adapter mapping tests |
| ADR-012 | Existing DRAFT Apply remains the sole L3 write Pilot | `ACCEPTED` | Recommended baseline approved 2026-08-13 by product/security/operations authority; NIF-16 engineering only, default-off and not production or legal sign-off |
| ADR-013 | External research, arbitrary MCP endpoints, and public code execution | `DEFERRED` | Separate governance package required |
| ADR-014 | One Runtime with registered Skills/Tools/Verifier | `ACCEPTED` | Implemented by NIF-03 behind default-off Flags |
| ADR-015 | AI Task, Step, and Event retention | `ACCEPTED` | Engineering rollout baseline approved 2026-08-12; not additional legal sign-off |

No proposed retention period, cloud data path, queue technology, knowledge location, or additional write action is treated as approved by NIF-00.

## Authoritative execution baseline

| Evidence | Result | Classification |
| --- | --- | --- |
| Repository | `D:\RR\royal-regent-nexus` source, isolated at `D:\RR\worktrees\nif-00-baseline-20260812` | `VERIFIED-HERE` |
| Remote default branch | `refs/heads/main` | `VERIFIED-HERE` |
| Remote and worktree SHA | `18dc3b11333742a0963248b39c235939b9685939` | `VERIFIED-HERE` |
| Branch | `agent/nif-00-baseline-adr-20260812` tracking `origin/main` | `VERIFIED-HERE` |
| Divergence at creation | `0 ahead / 0 behind` | `VERIFIED-HERE` |
| Historical source worktree | `agent/ai-b1-b9-internal-quote-20260811@67da509`, `6 behind / 0 ahead` | `VERIFIED-HERE`; preserved |
| Database migration | `20260812_0066_add_ai_action_confirmations.py` is present | `IMPLEMENTED`; head verification is recorded by the NIF-00 command result |
| Production | Outside NIF-00 | `NOT VERIFIED BY THIS PACKAGE` |

The old worktree's `.codex-phase1-qa/`, `artifacts/`, `backend/data/`, design QA images, and `outputs/` paths remain outside this worktree and must not be cleaned, moved, or staged by NIF work.

## AI-B1 through AI-B15 disposition

This is a source audit of the latest main baseline. `IMPLEMENTED` means the named source and contract tests exist; it does not mean this package reran every historical test or enabled the capability in production.

| Batch | Existing capability | Current evidence | Disposition |
| --- | --- | --- | --- |
| AI-B1 | Fake/Qwen Responses Provider, validated Beijing workspace endpoint, `store=false` | `provider_factory.py`, `providers/` | Reuse; extend contract in NIF-02 |
| AI-B2 | Bounded orchestrator and versioned SSE terminal contract | `orchestrator.py`, `/api/ai/responses` | Freeze v1 in NIF-01 |
| AI-B3 | Closed-schema Tool Registry/Executor with risk and authorization checks | `tool_registry.py`, `tool_executor.py` | Reuse; later wrap with Skill/Tool Catalog |
| AI-B4 | Versioned injection-scheduling module knowledge | `module_knowledge.py`, `docs/ai/modules/injection-scheduling.md` | Reuse; later publish through Knowledge governance |
| AI-B5 | Global memory-only Drawer and page context | `src/features/ai-assistant/` | Preserve compatibility; do not extend the monolithic store |
| AI-B6 | Injection scheduling and internal-quote read paths | `scheduling_read_tools.py`, `internal_quote_read_tools.py` | Reuse authorized domain services |
| AI-B7 | Vision attachments, sanitization, consent boundary, Provider compatibility | `attachment_service.py`, vision tests | Reuse; Artifact/two-stage migration is later work |
| AI-B8 | Pilot allowlists, runtime marker, limits, budget, TLS/provider readiness checks | `pilot_guard.py`, `runtime_gate.py` | Reuse; shared state is NIF-09 |
| AI-B9 | Read-only molding sample, carton procurement, raw material, customer order, and quote projections | `tools/*_read_tools.py`, `serializers/` | Reuse; do not recreate domain batches |
| AI-B10 | Bounded workbook semantic inspection | `workbook_inspection.py`, `/workbooks/inspect` | Reuse; migrate behind Artifact later |
| AI-B11 | Human-governed mapping proposal/Profile boundary | `workbook_mapping.py`, `/workbooks/mapping-proposal` | Reuse; cloud mapping remains default-off |
| AI-B12 | Cloud document translation switch with local fallback | `cloud_document_translation.py`, document translation service | Reuse; separate file consent/policy still required |
| AI-B13 | Scheduling candidate Preview generation and comparison | `scheduling_advisor.py`, advisor tools | Reuse as the first Simulation/Preview adapter |
| AI-B14 | Persisted action confirmation, TTL, argument hash, revision/freshness, idempotency | `ai_action_confirmations`, `action_confirmation.py`, migration `0066` | Reuse as compatibility input to NIF-16 |
| AI-B15 | Provider may propose, but cannot directly execute, DRAFT-only `apply_preview_run` | `controlled_apply.py`, action registry and APIs | Reuse; default-off; no Publish/Rollback |

## Current `/api/ai/capabilities` audit

Observed v1 behavior at this SHA:

1. Anonymous callers receive `401`.
2. `_pilot_capability_access` fails with `403 AI_PILOT_ACCESS_DENIED` for a non-Pilot user or invalid/empty Pilot scope, so no capability envelope is returned in those cases.
3. `enabled` reflects `AI_ENABLED` through Provider status; `available` and `streaming` additionally require Provider availability and a granted Pilot guard.
4. `vision_enabled` reflects the configured Vision Provider plus Pilot grant, but the endpoint has no page/factory/consent context and therefore cannot prove that the current request context may submit an image.
5. `conversation_persistence` is correctly hard-coded `false` for v1.
6. The endpoint constructs `ToolExecutionContext(page_context=None)`. Registry scope then permits only the global `identity` group; page-specific authorized groups are not represented.
7. The schema has no individual status for workbook inspection, cloud mapping, cloud translation, scheduling Preview, action confirmation, or Controlled Apply.
8. `pilot_access.read_only=false` and `max_tool_risk_level=PREVIEW_WITH_AUDIT` describe the maximum registered Pilot class, not which Preview/Action is usable in the caller's current page and factory.
9. The default registry is constructed once at module import from the Controlled Apply flag. NIF-01 must explicitly freeze whether configuration is startup-only or dynamically reloaded; NIF-00 does not change it.

Therefore v1 is safe and fail-closed, but it does not fully distinguish:

- platform support;
- server configuration/Feature Flag state;
- runtime/provider health;
- current-user authorization;
- current factory/page/context availability.

## Accepted NIF-01 compatibility contract

NIF-01 does not reinterpret old fields silently. It freezes the current response/SSE behavior and adds `POST /api/ai/capabilities/context` behind `AI_NIF_RUNTIME_ENABLED=false`. The new resource uses these dimensions:

```text
contract_version
platform_supported
configured_enabled
runtime_available
user_allowed
context_status: MISSING | INVALID | ALLOWED | DENIED
reason_code
feature_flags (server-owned, coarse, non-secret, and explicitly named as configured state)
available_tool_groups (only after validated page/factory context)
available_tools (only after server registry, IAM, factory, page, and Feature Flag filtering)
max_autonomy_level
```

Compatibility rules accepted for NIF-01:

- keep anonymous `401`;
- freeze current v1 `403` for users outside the Pilot while the old Drawer consumes v1;
- expose context-specific groups only after the server rebuilds `AIServerPageContext`; never trust client-supplied groups;
- keep `conversation_persistence=false` until NIF-05 is implemented and enabled;
- never report `DOCUMENT_OCR`, external research, arbitrary MCP, Publish, Rollback, or other deferred capabilities as available;
- report each default-off file/Preview/Action feature independently from broad text-chat availability;
- make unknown capability fields fail safely in the old frontend normalizer;
- keep ordinary business routes independent of AI availability.

The old `GET /api/ai/capabilities` remains the Drawer contract and is covered by an exact JSON fixture. The context resource is not called by the old Drawer and returns `404` while the NIF Runtime Flag is off. When enabled, it rebuilds the allowlisted server page context and derives provider definitions from the existing registry. `injection_scheduling.propose_apply` is absent unless Controlled Apply is configured and the current page/factory/user checks allow it. `injection_scheduling.apply_preview_run` is never returned because it remains an authenticated Action handler, not a model-callable Tool.

## v1 compatibility window and removal gate

The v1 JSON/SSE contract will be supported until all of the following are true:

1. NIF-18 production acceptance has passed;
2. the replacement client and Runtime have completed at least one subsequent normal production release without requiring v1 rollback;
3. compatibility telemetry and support review show no remaining required v1 consumer;
4. a separate removal package documents client migration, rollback, security review, and operator approval; and
5. the removal date is no earlier than 2026-12-31.

The effective removal date is the latest of those gates. Reaching the calendar date alone never authorizes removal. Until then, unknown additive events are ignored by the old frontend, existing event meanings remain fixed, sequence numbers stay strictly increasing, and exactly one terminal event is required.

NIF-01 contract coverage:

- anonymous, non-Pilot, disabled, runtime-marker, TLS, Provider-invalid, and granted states;
- no page context versus valid/invalid route, factory, and permission context;
- controlled-apply off/on and page-ineligible cases;
- mapping/translation/Vision flags independently off/on without implying consent;
- v1 exact response and SSE event fixtures;
- frontend handling of unknown additive fields and explicit unavailable reasons;
- proof that capability probing cannot refresh auth recursively or leak object existence.

## Consequences and rollback

NIF-00 changed documentation and current-state memory only. NIF-01 adds no migration and does not change v1 production behavior while the new Flag is off. Its rollback is removal of the new fixtures/tests, named Fake scenarios, context-capability schema/resource, and Flag entries. No source workbook, real Provider, or production state is touched.
