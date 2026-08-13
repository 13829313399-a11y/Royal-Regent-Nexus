# Knowledge correction review queue

This directory is the Git-backed review queue for proposed corrections to module knowledge. It is not part of the runtime retrieval corpus and no user or model submission can publish knowledge directly.

## Candidate flow

1. Record the user's correction as a new `DRAFT` candidate without copying secrets, credentials, personal data, or live business records.
2. Identify the target `knowledge_id`, exact section, submitter context, reason, and repository source files that can verify the correction.
3. The manifest `owner` reviews the source evidence. Product, security, or operations review again when the change affects their boundary.
4. Apply an accepted correction to `docs/ai/modules/*.md`, increment its semantic version, refresh `reviewed_at`, `reviewed_by`, `expires_at`, and source bindings, then run Knowledge validation.
5. Before NIF-17, the document can advance no further than `PILOT_READY`. `EVAL_PASSED` and `PUBLISHED` require a real Dataset, Runner result, and reviewer evidence.

Rejected, unverifiable, expired, or sensitive corrections do not enter the retrieval corpus. Runtime chat feedback remains conversation data only until an authorized owner creates and reviews a Git candidate through this process.
