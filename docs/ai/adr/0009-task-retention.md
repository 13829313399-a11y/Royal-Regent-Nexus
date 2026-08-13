# ADR-015 — AI Task, Step, and Event retention

- Status: `ACCEPTED`
- Accepted: 2026-08-12
- Approval authority: user acting for product, security, and operations
- Approval scope: engineering rollout baseline; not additional legal or regulatory sign-off
- Decision required before: NIF-07
- Runtime behavior changed by this proposal: no

## Why this is a separate decision

ADR-004/005 authorizes Nexus-owned conversations and their retention policy. An AI
Task is a durable orchestration/audit record, not chat memory and not a production
scheduling Task. NIF-07 therefore must not inherit the 30-day conversation-body
period or the 365-day Action-audit period without an explicit product, security,
and operations decision.

## Recommended engineering baseline

1. Retain terminal `ai_tasks`, `ai_task_steps`, and metadata-only
   `ai_task_events` for **180 days** from the terminal transition.
2. A non-terminal Task is not removed by elapsed-time retention. Stale-task
   detection and terminalization belong to the approved Worker/recovery package;
   NIF-07 does not pretend that an unfinished external call has stopped.
3. Store only bounded Runtime Plan snapshots, Skill/Prompt/Tool identifiers and
   hashes, state transitions, timestamps, safe error codes, Evidence references,
   Artifact references, and necessary idempotency metadata.
4. Structurally prohibit Provider secrets, raw Tool responses, uploaded file
   bodies, chat bodies, model private reasoning, access tokens, session cookies,
   and ordinary business-record copies in Task/Step/Event payloads.
5. Task retention does not control referenced Artifacts or formal Actions:
   Artifact content remains gated by ADR-009/NIF-12; Action audit remains 365 days
   and is not deleted with a Task or Conversation.
6. Task detail remains owner-only and always rechecks current factory and IAM.
   Administrator access does not bypass the owner/body boundary; security
   investigation uses metadata-only audit records.
7. No user delete API is added in NIF-07. After 180 days, retention may hard-delete
   the Task/Step/Event rows together. There is no legal-hold feature in this phase.
8. Backups retain deleted task rows for at most **30 additional days**, matching
   the accepted backup-deletion SLA baseline. Restore must replay retention before
   task data can be served.
9. Access-denial/security audit metadata remains governed by the accepted
   **180-day** security-audit period; it never includes Task input or Event bodies.
10. The policy is an engineering rollout baseline and is not additional legal or
    regulatory sign-off.

## Approval receipt

The user explicitly approved the recommended ADR-015 baseline on 2026-08-12 and
stated: “按推荐方案批准 ADR-015；我代表产品、安全和运维批准。这是工程上线基线，不代表额外法律合规签署”. This receipt accepts all ten recommendations above and authorizes NIF-07 engineering implementation. It does not authorize NIF-08 Worker topology, Artifact retention, additional Actions, production enablement, or additional legal/compliance sign-off.

## Rollback

Before acceptance, do not create Task tables, migration, runtime routes, or active
retention settings. After records exist, disable new Task creation and preserve
existing rows until the approved retention executor removes them; do not blindly
downgrade populated tables.
