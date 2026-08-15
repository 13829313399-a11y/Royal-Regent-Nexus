# Document Studio implementation status

Current repository status after Milestones 0–7 and the repository-side Phase 5 slice on 2026-08-14.

## Implemented

- One five-tab Document Studio shell for PDF-to-Excel, PDF-to-Word, Word-to-PDF, PDF translation and PDF split. The existing synchronous tools remain the fallback for the original three PDF tools.
- Closed preflight, job, snapshot, page/block/table/cell evidence, quality, review-patch, event, result and operational-metric contracts. The façade reuses AI Task and AI Artifact; it does not add a second task table or state machine.
- A fixed six-step Task plan: inspect, extract, reconcile, review, render and verify. Task/plan/input/Snapshot hashes bind human review, and an accepted review resumes the same Task.
- Native extraction and local OCR evidence, page-level Qwen OCR selection and 50-page chunking, an isolated `qwen3.5-ocr` Responses `input_file` provider, exact signed-file host/TTL/hash/size validation and lease revocation.
- Optional `qwen3.7-plus` strict-JSON cell reconciliation for PDF-to-Excel. It may update only known cell IDs; raw evidence, bbox and source identity remain immutable, and leading-zero identifiers fail into review instead of being rewritten.
- Evidence-aware Excel output with source mapping, conservative/smart type inference and table/page/same-schema worksheet strategies.
- Editable and layout-preserving PDF-to-Word modes.
- Offline bidirectional PDF translation for blocks and table cells, protected-token preservation, one-to-one unit validation, overflow review, translated-only/side-by-side/stacked PDF layouts and optional editable DOCX packaging.
- Word-to-PDF in the AI Task Worker through a temporary-profile LibreOffice subprocess. DOCX validation rejects corruption, macros and external relationships; production activation additionally requires an attested no-network namespace command. CPU, address-space, output-size, file-descriptor and wall-clock limits are applied on Linux, fonts are preflighted, the result PDF is validated and low-resolution page rendering records blank-page counts without rejecting intentional blank pages.
- Frontend source/result PDF preview, per-tool settings, explicit Beijing Qwen consent, issue-by-issue human review, authorized history, quality summary, sequential batches of up to ten files and four common configuration templates.
- Operational aggregation for success rate, review rate, P50/P95 duration, cloud-page count and average quality confidence.

## Default-off activation boundary

Repository examples keep all new external or high-risk capabilities off:

```text
AI_DOCUMENT_STUDIO_ENABLED=false
AI_DOCUMENT_CLOUD_OCR_ENABLED=false
AI_DOCUMENT_RECONCILE_ENABLED=false
DOCUMENT_OFFICE_RENDERER_ENABLED=false
DOCUMENT_OFFICE_RENDERER_NETWORK_ISOLATION_VERIFIED=false
```

Document Job capability additionally requires the existing AI Pilot, AI Task, Artifact workflow, PostgreSQL Worker and ClamAV gates. `RESTRICTED` documents cannot leave Nexus. AI-enhanced requests require request-bound consent, and cloud failure retains local evidence with an explicit warning. Word-to-PDF is advertised only when both the renderer and network-isolation verification flags are true.

## Verification snapshot

- Focused Document Studio plus wider AI Task/Artifact/Tool/Skill regression set: 119 passed.
- Full frontend unit suite: 160 files and 941 tests passed; 5 files and 6 tests skipped by their existing declarations.
- TypeScript test configuration, production frontend build, targeted Ruff and `git diff --check` passed.
- See `baseline.md` for the pre-change full-backend timeout boundary. A full backend suite pass is not claimed.

## External acceptance still required

The repository implementation is complete, but the following cannot be proven on this workstation and must remain disabled until the deployment environment supplies evidence:

- Real signing-broker deployment, allowed lease host, Qwen credentials/workspace, retention/deletion evidence, 429/timeout drill and request-log redaction check.
- LibreOffice Linux Worker image build, `unshare --net` (or an equivalent reviewed isolation mechanism), font inventory, resource-limit exercise and representative DOCX visual acceptance.
- Gold-set scores for table structure, character accuracy, leading-zero/type accuracy, translation glossary/code preservation, layout fidelity and manual-correction rate.
- Production backup/restore, artifact cleanup, load/concurrency, cost alerting, kill-switch drill and factory-by-factory canary approval.

Do not describe those field gates as completed merely because the code and mocks pass.
