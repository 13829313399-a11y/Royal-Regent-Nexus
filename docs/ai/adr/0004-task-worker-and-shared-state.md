# ADR-006/007 — Task Worker and shared Guard state

- ADR-006 status: `ACCEPTED` on 2026-08-12
- ADR-007 status: `ACCEPTED` on 2026-08-12
- ADR-006 approval authority: user acting for product, security, and operations
- ADR-006 approval scope: engineering rollout baseline; not additional legal or regulatory sign-off
- ADR-007 approval authority: user acting for product, security, and operations
- ADR-007 approval scope: engineering rollout baseline; not additional legal or regulatory sign-off
- Runtime behavior changed by NIF-08 source implementation: yes, behind default-off flags
- Runtime behavior changed by NIF-09 source implementation: yes, behind `AI_SHARED_GUARD_ENABLED=false`

## Proposal

For the initial single-region Pilot scale:

- use PostgreSQL task/step/event state with `FOR UPDATE SKIP LOCKED`, leases, heartbeats, cancellation, and idempotent retries;
- run the Worker as a separate process, never as an API-process background task for reliable jobs;
- implement concurrency, RPM, daily budget, and disable state behind a shared atomic Guard interface backed initially by PostgreSQL;
- retain a replacement boundary for Redis or a dedicated broker when measured contention or throughput requires it.

## Recommended ADR-006 engineering baseline

This recommendation is deliberately limited to NIF-08. It does not accept the
ADR-007 shared Guard design and does not authorize additional Action execution.

1. Use PostgreSQL as the Task queue and lease source for the initial single-region
   Pilot. Claim one Task at a time with `FOR UPDATE SKIP LOCKED`; the first rollout
   defaults to one Worker process with concurrency `1`, configurable only from
   `1` through `4`.
2. Use a **90-second lease** and a **15-second heartbeat**. A Worker that cannot
   renew stops claiming or starting new Steps immediately. A completed external
   call may commit its result only after atomically proving that the same Worker
   still owns a live lease.
3. Reclaim an expired lease only after its expiry is visible in PostgreSQL. Re-run
   only a Step whose registered contract is side-effect-free, idempotent, and
   `SAFE_TRANSIENT`; `UNKNOWN`, `NEVER_RETRY`, PREVIEW-state mutation, Action, and
   any consequential write fail closed for manual review.
4. Permit at most **two recovery retries after the initial attempt**. Backoff is
   bounded and recorded as metadata; exhausted attempts become a stable FAILED
   state rather than an infinite queue loop.
5. Keep Task execution behind a separate default-off Worker flag. The Worker must
   refuse SQLite, use the production PostgreSQL database, run as a separate
   process/service, and remain independently stoppable without making ordinary
   business APIs unhealthy.
6. Cancellation is durable intent. It prevents new Steps; a returning Provider or
   Tool call must recheck Task state and lease ownership before its result can
   advance the state. NIF-08 never executes an existing Action handler.
7. Evaluate Redis or a dedicated broker when **any one** of these conditions holds
   in two consecutive 15-minute windows:
   - claimable queue depth is at least **100**, or the oldest claimable Task waits
     at least **5 minutes**;
   - p95 PostgreSQL claim transaction time is at least **250 ms**, or claim/
     heartbeat lock, deadlock, or serialization retries reach **1%**;
   - sustained demand exceeds **30 Task starts per minute**, or meeting the Pilot
     service target requires more than **4 concurrent Workers**;
   - AI queue/lease load adds at least **20%** to ordinary API p95 latency or at
     least **10 percentage points** to database CPU compared with the same-hour
     non-AI baseline.
8. Start an immediate broker/topology review after any queue/lease incident that
   makes a non-AI business API unhealthy, even when the numeric threshold has not
   persisted for two windows. A trigger starts an engineering evaluation; it does
   not authorize an automatic infrastructure migration.

The values above are engineering rollout thresholds, not an availability SLA or
additional legal/compliance sign-off. Production enablement still requires the
later NIF-18 field and operational gates.

## ADR-006 approval receipt

The user explicitly accepted the complete recommended ADR-006 baseline on
2026-08-12, acting for product, security, and operations, and stated that the
decision is an engineering rollout baseline rather than additional legal or
regulatory sign-off. This approval authorizes NIF-08 lease columns, the separate
Worker process, bounded safe retry, recoverable Event flow, and the Workbench Task
experience under default-off rollout controls. It does not accept ADR-007, enable
production, authorize Action handlers, or change later NIF-18 field gates.

## Recommended ADR-007 engineering baseline

This recommendation is limited to NIF-09 shared Guard state. It does not enable
multiple instances, change Pilot allowlists or configured limits, authorize an
Action handler, or approve production rollout.

1. Keep the existing in-process Guard as an explicit single-instance compatibility
   mode. Add a separate default-off switch for the shared Guard; when selected it
   requires PostgreSQL and refuses an unsupported database instead of silently
   falling back to process-local counters.
2. Serialize an acquisition on stable global, factory and user advisory-lock keys
   in one PostgreSQL transaction. In that transaction, expire stale leases,
   evaluate durable disable state, enforce the existing per-user concurrency and
   rolling 60-second RPM limits, reserve the Asia/Shanghai daily Token budget and
   create the lease plus request event atomically.
3. Preserve the current conservative accounting contract: reserve before work;
   reconcile reported usage only after completion; charge the full reservation
   when a started Provider call has missing or lower usage; and never use billing
   data as a real-time limit source.
4. Give every lease an opaque identifier and token, owner user, verified factory,
   instance ID, reservation, budget day and expiry, but never a Prompt, Tool result
   or business payload. A lease is idempotently releasable and renewable; expired
   leases release their reservation during the next locked cleanup pass.
5. Keep the existing file marker as the strongest local emergency control. Shared
   disable evaluation is `GLOBAL`, then `FACTORY`, then `USER`; an enabled shared
   row at any level denies new work. Explicit Pilot allowlist denial remains a
   separate prerequisite and cannot be overridden by shared state.
6. Use the same shared backend from API streaming requests and Worker model work.
   Worker heartbeats renew both its Task lease and any active Guard lease; results
   may advance state only while those ownership boundaries remain valid.
7. Fail closed for new AI work when the selected shared backend cannot complete an
   atomic operation. Do not make ordinary business API health depend on Guard or
   Worker availability, and do not expose a public mutation endpoint for disable
   state in NIF-09.
8. Retain request metadata for only the rolling-window/cleanup need and budget rows
   for bounded operational diagnosis. Redis evaluation is triggered by measured
   Guard lock/contention or database impact; it is not an automatic migration or
   part of this approval.

The values and boundaries above are an engineering rollout baseline, not an
availability SLA or additional legal/compliance sign-off. Production enablement
still requires the later NIF-18 field and operational gates.

## ADR-007 approval receipt

The user explicitly accepted the complete recommended ADR-007 baseline on
2026-08-12, acting for product, security, and operations, and stated that the
decision is an engineering rollout baseline rather than additional legal or
regulatory sign-off. This approval authorizes the default-off NIF-09 PostgreSQL
atomic Guard backend, shared API/Worker accounting, metadata-only disable state and
single-instance compatibility boundary. It does not enable multiple instances or
production, authorize Action handlers, change Pilot membership or limits, or
replace the later NIF-18 field gates.

## Safety invariants

- A lease expiry may reassign only a step declared safe to retry.
- Cancellation and kill-switch state are durable.
- Provider failure or Worker crash cannot make ordinary business APIs unhealthy.
- A committed action is never blindly replayed; its idempotency/audit state is queried.
- Shared-state failure is fail-closed for new AI work.

## NIF-08 implementation receipt

The NIF-08 source implementation records the accepted ADR-006 baseline in migration
`20260813_0070`, an independent PostgreSQL-only Worker, conditional lease claim,
heartbeat renewal, bounded retry, timeout, crash recovery, persistent Event cursor
recovery and Workbench Task controls. The Worker registry excludes Controlled Apply
and its runner permits only NONE or PREVIEW_STATE contracts, with automatic replay
restricted further to side-effect-free idempotent `SAFE_TRANSIENT` work. All rollout
flags remain off in both environment examples. This receipt is implementation and
local verification evidence only; it is not production enablement.

## NIF-09 implementation receipt

The source implementation records the accepted ADR-007 baseline in migration
`20260813_0071`, a Guard backend interface, and a PostgreSQL implementation using
stable transaction-scoped advisory locks for global, factory and user scope. API
requests and Worker Steps share opaque leases, per-user concurrency, rolling RPM,
Asia/Shanghai daily reservations and conservative usage reconciliation. Active
Worker operations renew Guard leases; cancellation stops the protected coroutine.
The file marker remains the local emergency control, while durable shared disable
state is evaluated in GLOBAL, FACTORY, USER order. Expired lease, request-window,
budget and temporary-disable metadata has bounded cleanup, and no Guard table holds
a Prompt, business payload or Tool result.

`AI_SHARED_GUARD_ENABLED` remains false in both environment examples. Local tests
exercise two independent backend instances, threaded contention, lease recovery,
shared API/Worker accounting boundaries, RPM/day rollover, disable priority,
database-unavailable fail-closed behavior, cleanup and protected migration
downgrade. This workstation has no native Docker/PostgreSQL runtime, so a real
multi-process PostgreSQL contention/load drill remains a later field-gate check;
source implementation and local verification are not production enablement.

## Rollback

Before ADR-006 implementation is enabled, stop the Worker service and disable new
Task creation while retaining Task/Event state for diagnosis and recovery. Before
NIF-09 is enabled, keep the process-local Pilot Guard and single-instance topology.
To roll back an enabled shared Guard, first return the complete API/Worker topology
to one instance, then switch the Guard backend; never mix shared and process-local
accounting across live instances.
