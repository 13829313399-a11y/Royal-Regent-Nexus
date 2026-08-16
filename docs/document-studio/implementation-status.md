# Document Studio implementation status

## Current runtime

The public Document Studio is a request-time five-tool surface backed only by
`/api/tools/*`. It does not create AI Tasks or Artifacts, upload through ClamAV,
route through an AI Skill, or require an AI Pilot allowlist.

- PDF to Excel: local extraction in `LOCAL`; Base64 page OCR plus strict table
  JSON from Qwen in `QWEN`; confidence-driven selection in `AUTO`.
- PDF to Word: local editable/layout-preserving output; Qwen OCR can supply
  editable page text. Layout-preserving mode is intentionally local.
- PDF translation: local model in `LOCAL`; Qwen-MT in `QWEN`; capability-driven
  selection in `AUTO`.
- Word to PDF: deterministic headless LibreOffice conversion only.
- PDF split: deterministic local splitting only.

The old Document Job API, review drawer, six-step Task Tool, five dedicated AI
Skills and self-hosted signed-file Broker have been retired. Shared AI Task,
Artifact, Skill and Tool Registry infrastructure used by other modules remains
unchanged. Existing database tables and Alembic history are retained for one
version cycle; historical rows remain readable directly from the database but
are no longer exposed as a Document Studio runtime.

## Runtime configuration

`DOCUMENT_TOOLS_ENABLED` controls the public surface. File/page limits and
temporary-file lifetime are configured with `DOCUMENT_TOOL_*`. Qwen is enabled
with `QWEN_DOCUMENT_ENABLED` and backend-only Provider credentials; model names,
batch size, concurrency and timeout use `QWEN_*`. Word-to-PDF requires the
configured LibreOffice command. No domain or signed-file URL is required because
Qwen receives rendered pages as Base64 Data URLs.

## Preserved boundaries

- Source files are never overwritten and generated results are not persisted.
- MIME/signature, PDF structure, OOXML ZIP, macro, external relationship,
  decompression and output validation remain mandatory.
- API keys stay server-side and request bodies are not logged.
- The generic AI Task/Artifact/Skill stack keeps its existing stricter policy.
