# NIF-18 production readiness and fault-drill evidence

## Current result

`NO-GO` for production NIF completion.

The repository-side gates and evidence format exist, but this file does not claim that a production browser, TLS edge, database, Provider, Worker, ClamAV/OSS/KMS path, alert channel or rollback image has been exercised. ADR-012 is `ACCEPTED` for the default-off NIF-16 engineering baseline, and that repository implementation now exists. The mandatory DRAFT-only Controlled Apply scenario has not received `FIELD-PASS`, so production enablement remains unauthorized. L4 Publish, Rollback, final release and inventory adjustment remain prohibited.

## Evidence classes

| Class | Meaning |
| --- | --- |
| `IMPLEMENTED` | Source, tests or deployment controls exist in the repository. |
| `VERIFIED-HERE` | A named local command passed against this worktree. |
| `FIELD-PASS` | A named operator ran the scenario on the exact deployed revision and attached evidence. |
| `NO-GO` | One or more mandatory field/approval gates are absent. |

Local tests can reach only the first two classes. Operators must never copy a local result into a `FIELD-PASS` gate.

## Current local verification snapshot

On 2026-08-13 this isolated worktree merged `origin/main` at `b0575ef` in local
merge commit `9128eff`, after preserving the AI implementation in safety commit
`1b71a60`. The upstream QC migration remains `20260812_0067`, the AI chain follows
as `20260813_0068`–`20260813_0074`, and Alembic reports the single head
`20260813_0074`. The post-merge worktree verified 72 migration/compatibility tests,
440 passed/2 intentionally skipped backend AI tests, 13 deployment/security tests,
and the full frontend suite at 895 passed/6 skipped across 157 test files. Ruff on
the branch Python scope, frontend test typecheck, production build, four
deployment-script syntax checks and `git diff --check` also passed. The build
reported only non-blocking dependency annotation warnings from `@vueuse/core`.

Docker remains unavailable on this workstation, so Compose/container validation
and every real production field scenario remain unverified. The repository merge
and local gates close the earlier integration gap but do not change the production
result from `NO-GO` or authorize enabling AI.

## Two-stage rollout

1. Deploy with `/app/backend/control/ai.disabled` present. Keep every newly introduced NIF Feature Flag default-off until its own prerequisite and approval is complete.
2. Run `deploy/verify-ai-pilot-readiness.sh` with the disable marker expected. Verify backup checksum and restore list before migration, one Alembic head, the exact deployed Git SHA, Secure/HttpOnly/SameSite cookie behavior, HSTS, Beijing Provider route and named Pilot scope.
3. Enable only approved read/compute/preview packages. ADR-012 and the NIF-16 automated gates do not by themselves enable Controlled Apply; keep both Action Gateway and Controlled Apply off until the dedicated action field stage is approved and passed.
4. Remove the marker only for the approved observation window. Run every scenario below while preserving ordinary-business availability evidence.
5. Recreate the marker before analysing any failure. A failed or interrupted drill leaves AI disabled.
6. Complete an out-of-repository copy of `deploy/nif18-production-evidence.template`. The evidence contains references and approvals only—never secrets, cookies, prompts, Tool results or customer data.
7. On the deployed, clean revision, run:

   ```sh
   NIF18_EVIDENCE_FILE=/secure/path/nif18.evidence \
   UPSTREAM_REF=origin/main \
   sh deploy/verify-ai-nif18-evidence.sh
   ```

Only a successful final verifier result may be considered with product, security and operations approval. It still does not authorize a second L3 action or any L4 action.

## Mandatory field scenarios

For every scenario record UTC start/end, deployed SHA, operator, expected result, actual result, safe log/metric reference, ordinary `/health` result and rollback action. Do not record request bodies.

1. Persistent Conversation survives Drawer close, refresh and route changes; a Temporary Conversation retains no body.
2. A single-factory user requesting another factory receives a non-enumerating denial.
3. Semantic analysis invokes only the registered single-domain Tool and shows factory/as-of/truncation Evidence; cross-domain analysis remains `DEFERRED`.
4. Image Observation remains `USER_PROVIDED` and separate from fresh formal Backlog Evidence.
5. Workbook Mapping and scheduling Scenario remain Preview and perform no formal write.
6. With accepted ADR-012 and the verified NIF-16 build deployed behind the active disable marker: the sole approved Action applies one current Preview to DRAFT, with current IAM/Revision/TTL/idempotency/audit/read-back verification; replay, stale, expired and duplicate attempts fail closed; no Publish occurs. Record this as `FIELD-PASS` only after the exact deployed revision succeeds.
7. Inject Provider 429, timeout, DNS and 5xx independently. AI produces stable errors while login, quotation, order, scheduling and local translation health remains available.
8. Crash a Worker during an explicitly retry-safe Step. Lease recovery, Cancel and Resume obey the recorded state machine; Preview mutation and Action Steps do not replay.
9. With at least two API/Worker instances, prove shared concurrency, RPM, daily Token budget and kill-switch state; capture PostgreSQL contention/latency evidence.
10. Activate the file/shared kill switch. New API and Worker work stops while ordinary business health remains green. Leave the marker present after any failed drill.
11. Upload clean and rejected test Artifacts. Verify private storage, current ClamAV signatures, fail-closed scanner outage, owner/factory download authorization, retention cleanup, encrypted OSS backup and restore.
12. Trigger cost, Provider failure, Tool failure, Worker recovery, scanner-age and budget alerts and obtain the receiving channel acknowledgement.
13. Roll back API/Web to captured images without deleting new AI/audit tables or business data; apply retention/tombstones after any restore.
14. In an authenticated browser, repeat all user-visible paths and verify unknown Renderer/Tool/Skill contracts fail closed.

The shared file-marker portion of scenario 10 has a deliberately one-way helper. It requires an authenticated cookie-jar file outside the repository, writes no response body to the evidence record, gives its helper container no network, and never removes the marker:

```sh
CONFIRM_NIF18_KILL_SWITCH_DRILL=DISABLE_AI_AND_VERIFY_BUSINESS \
AI_PUBLIC_ORIGIN=https://your-approved-host \
AI_DRILL_COOKIE_FILE=/secure/path/operator-cookie-jar \
sh deploy/run-ai-nif18-kill-switch-drill.sh
```

Removing the marker is a separate operator decision after evidence review; this script cannot reactivate AI.

## Required automated gate

Run the exact NIF-18 command group in the development direction document. Docker Compose rendering is `FIELD-ONLY` on a workstation without Docker. A passing local group is necessary but cannot change `NO-GO` to `FIELD-PASS`.

## Next autonomy decision

ADR-012 is accepted only for the sole DRAFT Apply engineering baseline. Every mandatory production
gate, including the Controlled Apply DRAFT scenario, must still be `FIELD-PASS` on the exact deployed
revision before production NIF completion. No next L3 Action ADR is formed by this package; a later
proposal for one additional bounded L3 action is a separate decision.
ADR-013 remains `DEFERRED`; arbitrary MCP endpoints, external research and public code execution
are not part of NIF-18.
