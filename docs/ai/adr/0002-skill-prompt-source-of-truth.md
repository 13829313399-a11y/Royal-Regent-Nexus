# ADR-003/014 — Skill, Prompt, and Runtime source of truth

- Status: `ACCEPTED`
- Decision required before: NIF-03
- Date: 2026-08-12
- Runtime behavior: Git-first Skill/Prompt and the single bounded Runtime are
  implemented behind `AI_NIF_RUNTIME_ENABLED=false` and
  `AI_SKILL_ROUTER_ENABLED=false` defaults.

## Decision

Use Git-reviewed files as the authority for Skill manifests, Prompt fragments, closed output schemas, examples, evaluation cases, ownership, and versions. Runtime persistence may record the published ID, version, content hash, and status snapshot, but it must not become a second freely editable authority.

Use one Nexus Runtime with registered Skills, Tools, Context adapters, and Verifiers. Planner/Executor/Reviewer are bounded internal roles, not independent user-facing bots or an autonomous agent swarm.

## Invariants

- Existing IAM, factory isolation, Tool schemas, and domain Services remain authoritative.
- Prompt text cannot grant permissions or register a Tool.
- A Skill version identifies its manifest, prompt, schemas, Tool set, renderer contract, and eval suite together.
- Publishing a Skill or Prompt requires tests and a content hash.
- Technical documents such as `AGENTS.md` and `PROJECT_MEMORY.md` are not exposed as ordinary business knowledge.

## Alternatives not selected

- Database-authored Skills/Prompts are not approved.
- A third-party autonomous Agent framework is not approved.
- Multiple user-visible agents are not approved.

## Gate result

The repository owner's explicit instruction to execute the reviewed NIF roadmap
accepts ADR-003 and ADR-014 for NIF-03. Enabling either source flag is a separate
rollout decision; while the flags remain off, the existing Tool Registry and
global Prompt stay the compatibility implementation.
