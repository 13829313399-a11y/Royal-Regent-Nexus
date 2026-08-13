# ADR-008/009 — Knowledge and Artifact data location

- ADR-008 status: `ACCEPTED`
- ADR-009 status: `ACCEPTED`
- Decision still required before: none for NIF-12 implementation; production enablement keeps the operational gates below
- Runtime behavior changed by NIF-00: no

## Knowledge proposal

Start with reviewed repository Git knowledge plus structured ownership/version metadata and local controlled exact/keyword retrieval. The first implementation uses a bounded in-process index and a retriever adapter, so NIF-11 adds no database migration. PostgreSQL full-text retrieval may be added behind that adapter only after a separate measured need; pgvector requires evaluation evidence of a semantic recall gap. Do not send internal sensitive knowledge or real-time business data to a Provider File Search.

Real-time orders, quotes, inventory, schedules, and approval state always come from authorized domain Tools. Knowledge explains versioned process; it does not become a duplicate business ledger.

Knowledge documents are owned by their corresponding module Knowledge Owner and may reach only `PILOT_READY` before NIF-17. `EVAL_PASSED` and `PUBLISHED` require a real NIF-17 Dataset/Runner result and reviewer evidence. This approval was given by the user acting for product, security, operations, and the module Knowledge Owners as an engineering rollout baseline; it is not additional legal compliance sign-off.

## Artifact proposal

The following recommended engineering baseline was explicitly approved on 2026-08-12 by the user acting for product, security, and operations. It authorizes NIF-12 implementation behind default-off controls. This is an engineering rollout baseline, not an additional legal compliance sign-off, and does not itself authorize production enablement.

### Storage and backup

- store database metadata separately from immutable original bytes behind a Storage Adapter;
- use a private, non-public `ai-artifacts` Docker production volume on the Nexus production host, mounted only by the API and AI Worker; filenames never participate in storage keys;
- use a content-independent opaque storage key, record SHA-256, uploader, factory, classification, media type, retention, scanner result, and lineage;
- run a daily encrypted backup to a private, non-public Aliyun OSS bucket in an approved mainland-China region, using server-side KMS encryption and a maximum 30-day backup-deletion tail; the exact bucket name, KMS key and credentials remain deployment secrets, and a verified restore drill is required before production readiness;
- create mapping, translation, OCR and report outputs as new derived Artifacts; never overwrite the original.

### Classification and Provider egress

- use `INTERNAL`, `CONFIDENTIAL_BUSINESS`, and `RESTRICTED` as the closed first-version classifications;
- `RESTRICTED` bytes never leave Nexus for an external Provider;
- `INTERNAL` or `CONFIDENTIAL_BUSINESS` may be sent only to the reviewed Aliyun Bailian Beijing Provider route with `store=false`, when the corresponding Skill/feature flag is independently enabled and the current request has explicit consent for that exact content class;
- customer workbooks, ordinary documents and images have separate per-request consent. Consent is not reusable across classes or requests and must name the Provider, region and classification;
- no Artifact is uploaded to a Provider automatically. NIF-12 only records the policy; later adapters must reauthorize and enforce it.

### Scanner and closed file limits

- production scanning uses a private ClamAV daemon service behind the Scanner Adapter, with signature updates at least every four hours and health/signature-age surfaced to operations; tests use a deterministic Fake Scanner;
- scanner unavailable, timeout, error, rejected content or incomplete scan fails closed for external uploads and blocks Parser/Provider access;
- the initial allowlist is `.xlsx`, `.csv`, `.pdf`, `.docx`, `.png`, `.jpg`, `.jpeg`, and `.webp`; legacy binary Office files, macro-enabled Office files and active content are rejected;
- workbook, CSV, PDF and Word files are limited to 20 MiB each; PDFs are limited to 200 pages;
- images retain the existing boundary of 4 MiB and 16 megapixels each, at most three images and 12 MiB/24 megapixels total per request;
- OOXML/ZIP expansion is limited to 100 MiB and a 100:1 compression ratio; extension, declared MIME, detected MIME and magic bytes must agree.

### Retention, deletion and authorization

- original and derived bytes default to 30-day retention unless a narrower approved policy applies;
- delete immediately revokes listing/download/derivation, online bytes are cleaned within 24 hours, and encrypted backup remnants expire within the maximum 30-day backup tail;
- metadata-only tombstones and security audit are retained for 180 days; existing Action audit remains governed separately;
- derived Artifacts keep immutable parent and parser/model-version lineage and cannot silently extend the parent's approved data-use scope;
- every metadata read, download, derivation and Provider send reauthorizes current owner, factory and permission; no public bucket or permanent public URL is allowed.

## Production release evidence still required

- exact deployment secret values, KMS-key custody assignment and the named restore-drill operator, which are operational release evidence rather than repository values;
- alert delivery integration for ClamAV health/signature age, which must be verified before production enablement;
- Provider-specific retention terms remain a separate egress release gate even after ADR-009 is accepted; until then all Artifact-to-Provider feature flags remain off.

The policy owner is platform engineering; security must review classification/egress changes, operations must review storage/scanner/backup changes, and the relevant module owner must review content-specific retention changes.

PDF/OCR parsing and production code execution remain `DEFERRED`; Artifact v1 must not claim those parsers exist.

## Rollback

If NIF-12 is rolled back before production data exists, remove the default-off API, adapters, schema, and deployment configuration. Once Artifact records or bytes exist, close upload and Provider-egress flags first, retain metadata and immutable bytes under the accepted deletion schedule, and complete an operator-reviewed export/cleanup; never blindly downgrade or orphan stored data. Existing workbook, Vision, and translation paths remain separate until their own two-stage migration packages are accepted.
