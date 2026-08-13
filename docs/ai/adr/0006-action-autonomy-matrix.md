# ADR-012/013 — Action autonomy and external capability boundary

- ADR-012 status: `ACCEPTED` on 2026-08-13 for the current DRAFT-only write Pilot
- ADR-013 status: `DEFERRED` for external research and arbitrary MCP
- Decision effect: authorizes the default-off NIF-16 engineering baseline; NIF-18 field evidence and
  a separate operator enablement decision remain required for production
- Approval receipt: the user explicitly approved the recommended ADR-012 baseline while acting for
  product, security and operations. This is an engineering rollout baseline, not an additional legal
  or compliance sign-off, production enablement, or authority for a second L3/L4 action.

## Current source fact

The repository already has AI-specific database state in `ai_action_confirmations` and one consequential action handler, `apply_preview_run`. It is default-off, applies a selected scheduling run only to DRAFT, and never Publishes or Rolls Back. The model-callable Tool can propose a confirmation; the execution handler is available only through the separate authenticated confirmation/execute API.

## Accepted autonomy matrix

| Level | Allowed class | Approval posture |
| --- | --- | --- |
| L0 | Explanation and ordinary conversation | No action approval |
| L1 | Authorized read-only Tool | Server IAM/factory checks |
| L2 | Deterministic compute, Simulation, Preview, draft Artifact | No formal business write |
| L3 | Reversible or bounded command | Explicit user approval, frozen arguments/revision/TTL/idempotency, post-verification, audit |
| L4 | Publish, final release, inventory adjustment, similar high-impact action | `DEFERRED`; separate domain policy and normally stronger or dual approval |
| L5 | Arbitrary SQL, bypassed authorization, irreversible bulk mutation, arbitrary public code/MCP | `REJECTED` by the architecture boundary |

## Required policy

- Keep `apply_preview_run` as the sole L3 Pilot until field acceptance.
- Do not add a second consequential write, Publish, Rollback, final release, or inventory adjustment in NIF-00 through NIF-17.
- Proposal creation and final execution each recheck current IAM and factory scope.
- Approval binds actor, factory, canonical arguments/hash, entity revision/input hash, TTL, and an idempotent execution request.
- The domain Service and database remain authoritative; execution must read back and verify the formal DRAFT.
- Provider, Prompt, Tool text, user files, images, and MCP output cannot authorize an action.

## Production gate

The current code is not evidence of production approval. NIF-18 requires real TLS/HSTS, Secure cookies, rotated Provider secret, authorization posture, kill-switch drill, browser/field acceptance, cost monitoring, and named Pilot users/factories before production-ready status.

External research, arbitrary MCP URLs, and public code execution remain disabled until an independent allowlist, data-egress, download isolation, source-rating, credential, regional, logging, and administrator-registration design is approved.

## Rollback

Keep all new action flags off. The runtime marker can stop AI work without affecting ordinary business functions; no NIF-00 document change executes or cancels a business action.
