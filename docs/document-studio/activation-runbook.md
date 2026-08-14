# Document Studio activation runbook

Use this runbook only after the repository checks in `implementation-status.md` pass on the release commit.

## 1. Keep kill switches off

Start with Document Studio, cloud OCR, reconciliation and Office rendering disabled. Confirm the existing synchronous PDF and Office-document translation routes remain healthy.

## 2. Validate governed Task prerequisites

Verify PostgreSQL migrations/current schema, the separate AI Task Worker, ClamAV health and signatures, private Artifact storage, authorized factory/user allowlists, retention cleanup, backup encryption and restore evidence. Enable only `AI_DOCUMENT_STUDIO_ENABLED`, then verify local-private PDF-to-Excel, PDF-to-Word and PDF split through upload, Task, derived Artifact and reauthorized download.

## 3. Validate Qwen document processing

Deploy the reviewed HTTPS signing broker. Configure an exact lease host allowlist, a 60–600 second TTL and request-bound deletion/revocation. Configure the Beijing workspace and secret outside Git. Exercise native-only, low-confidence, 50-page and 51–80-page PDFs; timeout, 429, 5xx, invalid schema, expired URL and revocation failure; and confirm that raw content, Base64 and signed URLs do not appear in logs. Confirm `RESTRICTED` and no-consent requests fail before transmission. Only then enable cloud OCR, followed separately by structured reconciliation.

## 4. Validate Office rendering

Build the Worker image with LibreOffice Writer and Noto CJK fonts. Prove the configured isolation command creates a no-external-network namespace and that the Worker, not the FastAPI request process, owns conversion. Test macro, external-link, corrupt, missing-font, timeout, memory/CPU limit and invalid-output cases. Visually accept representative headers, footers, tables, images, bookmarks, portrait/landscape sections and intentional blank pages. Set the isolation verification flag only after this evidence exists, then enable the renderer.

## 5. Gold-set and canary gates

Record the metrics listed in `evaluation.md`; do not use screenshots alone as acceptance. Canary one authorized user and one factory with runtime kill switches ready, compare success/review/P95/cloud-page metrics and cost alerts, then widen one factory at a time. Roll back by disabling the relevant capability flag; derived Artifacts remain governed by normal retention and authorization.
