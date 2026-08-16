# Document Studio activation runbook

## 1. Configure the direct tools

Enable `DOCUMENT_TOOLS_ENABLED`. Set the file/page/TTL limits, then configure
LibreOffice and the Qwen backend credentials/models if those modes are wanted.
Do not configure a signed-file Broker and do not enable AI Task/Artifact flags
solely for Document Studio.

## 2. Check capabilities before traffic

Verify `/health`, then call `/api/tools/capabilities` and the administrator-only
`/api/tools/diagnostics`. Confirm that unavailable modes report an explicit
reason code. A missing Qwen credential must disable only Qwen modes; a missing
LibreOffice binary must disable only Word-to-PDF.

## 3. Run the five-tool smoke gate

Use non-sensitive fixtures and reopen every result:

1. PDF-to-Excel in `QWEN`, including a leading-zero identifier.
2. PDF-to-Word editable in `QWEN`.
3. PDF translation in `QWEN`.
4. Word-to-PDF through the real LibreOffice binary.
5. PDF split with more than one output PDF.

Also test `LOCAL` where offered, invalid MIME/signature, an over-limit file/page
count, malformed OOXML and one Provider timeout. Verify logs do not contain file
contents, Base64 data or Provider secrets.

## 4. Rollback

Disable `DOCUMENT_TOOLS_ENABLED` to close the public surface, or disable
`QWEN_DOCUMENT_ENABLED` to keep deterministic local tools while removing cloud
processing. Application rollback does not require a database downgrade.
