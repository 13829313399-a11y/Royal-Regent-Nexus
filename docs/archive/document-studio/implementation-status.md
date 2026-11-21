# Document Studio implementation status

> **历史归档 · 2026 年 8 月。** 本文记录当时的同步工具。维护现行服务请读[公共文档工具运行说明](../../document-tools/README.md)。

## Current runtime

Document Studio is an authenticated, synchronous five-tool surface backed by `/api/tools/*`.

- PDF to Excel: deterministic local extraction in `AUTO` or `LOCAL`.
- PDF to Word: local editable or layout-preserving output.
- PDF translation: the configured offline translation model.
- Word to PDF: headless LibreOffice conversion.
- PDF split: deterministic local splitting.

The runtime has no cloud-provider call, assistant integration, task queue, artifact store, background worker or malware-scanner dependency. Source files and generated results are not persisted.

## Runtime configuration

`DOCUMENT_TOOLS_ENABLED` controls the public surface. `DOCUMENT_TOOL_*` settings control file/page limits and temporary-file lifetime. The offline translation model uses `DOCUMENT_TRANSLATION_*`; Word-to-PDF uses the configured LibreOffice command.

## Preserved boundaries

- Source files are never overwritten and generated results are not persisted.
- MIME/signature, PDF structure, OOXML ZIP, macro, external relationship, decompression and output validation remain mandatory.
- Temporary files are isolated and cleaned after each request.
- Request bodies and document contents are not logged.
