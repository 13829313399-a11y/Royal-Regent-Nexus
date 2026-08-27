# Document Studio activation runbook

## 1. Configure local tools

Enable `DOCUMENT_TOOLS_ENABLED`, set the file/page/temporary-file limits, and configure the optional local translation model plus LibreOffice. Document Studio has no cloud-provider, background worker, task or artifact configuration.

## 2. Check capabilities before traffic

Verify `/health`, then call `/api/tools/capabilities` and the administrator-only `/api/tools/diagnostics`. Confirm unavailable local engines report explicit reason codes. A missing translation model must disable only document translation; a missing LibreOffice binary must disable only Word-to-PDF.

## 3. Run the five-tool smoke gate

Use non-sensitive fixtures and reopen every result:

1. PDF-to-Excel in `AUTO` and `LOCAL`, including a leading-zero identifier.
2. PDF-to-Word in editable and layout-preserving modes.
3. PDF translation through the configured offline model.
4. Word-to-PDF through the real LibreOffice binary.
5. PDF split with more than one output PDF.

Also test invalid MIME/signature, an over-limit file/page count, malformed OOXML and one local-engine failure. Verify logs do not contain file contents or Base64 data.

## 4. Rollback

Disable `DOCUMENT_TOOLS_ENABLED` to close the public surface. Application rollback does not require a database downgrade.
