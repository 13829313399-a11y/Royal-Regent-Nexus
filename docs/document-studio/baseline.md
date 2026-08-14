# Public Document Studio baseline

Captured on 2026-08-14 before the first Document Studio implementation batch.

## Repository state

- Repository: `D:\RR\royal-regent-nexus`
- Baseline commit: `61e273b58da1`
- `HEAD` and `origin/main` pointed to the same commit and tree.
- `rrceshi3/main` had different history (`HEAD` was ahead 1 / behind 28), but the tracked tree matched the baseline tree.
- Pre-existing untracked QA, output, data, and artifact directories were left untouched.

## Runtime

- Node.js: `24.14.0`
- npm: `11.9.0`
- Python: `3.14.6`
- Frontend dependencies and `backend/.venv` were already present.

## Repeatable baseline commands and results

### Frontend

```powershell
npm run test:unit -- --reporter=dot
npm run typecheck:test
npm run build
```

Results:

- Unit tests: passed — 158 files passed, 5 skipped; 934 tests passed, 6 skipped.
- Test TypeScript check: passed.
- Production build: passed (785 modules in the pre-change baseline).
- Existing non-blocking build warnings remained: `@vueuse/core` PURE annotation placement, chunks over 500 kB, and plugin timing diagnostics.

### Existing public document tools

The repository already contained synthetic service fixtures for PDF-to-Excel, PDF-to-Word, PDF split, and Office document translation. No real business file was added.

```powershell
backend\.venv\Scripts\python.exe -m pytest -q `
  backend\tests\test_pdf_to_excel_service.py `
  backend\tests\test_pdf_document_tools.py `
  backend\tests\test_document_translation_service.py
```

Result: passed — 18 tests.

### Backend full suite

```powershell
backend\.venv\Scripts\python.exe -m pytest -q backend\tests
```

Result: not completed — the command was terminated by the execution timeout after 904 seconds. It produced no terminal test summary before timeout. This is recorded as an unverified full-suite boundary, not as a pass or a test failure.

## Known test-environment warning

Focused backend runs report a `PytestCacheWarning`: `.pytest_cache/v/cache` already exists in a shape that prevents pytest from creating its normal cache path (`WinError 183`). Tests still execute, but the existing cache artifact should not be removed without separately confirming ownership and scope.

## Compatibility boundary for the first batch

- Keep the authenticated `/tools?factory=...` route and the real global shell.
- Keep existing `/api/tools/pdf-to-excel`, `/api/tools/pdf-to-word`, `/api/tools/pdf-split`, and Office document translation behavior available.
- Do not manufacture task progress or recent-job records for synchronous calls.
- Reuse AI Task and AI Artifact later; do not add a parallel task state machine.
- Keep Document Studio, cloud OCR, and Office renderer feature switches off by default.
- Do not enable `DOCUMENT_OCR` in the general AI capability router in this batch.
