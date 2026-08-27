# Document Studio evaluation contract

Store only deidentified or approved synthetic fixtures in the repository. Keep business documents in the governed external evaluation environment.

| Capability | Required measures |
| --- | --- |
| PDF to Excel | cell character accuracy, table structure F1, merged-header accuracy, leading-zero preservation, numeric/date/currency type accuracy, row/column/total consistency, manual correction rate |
| PDF to Word | character accuracy, reading-order accuracy, heading/list/table/image recall, missing/duplicate block rate, layout-preserving page-image count |
| PDF translation | glossary hit rate, number/code preservation, one-to-one unit rate, table-cell coverage, overflow rate, human acceptance rate |
| Word to PDF | page-count consistency, unintended blank-page rate, missing-font rate, header/footer/table/image checks, visual-difference review rate |
| Platform | success/failure rate, P50/P95 request duration, temporary-file cleanup rate and local-engine resource usage |

Every evaluation record must bind the source fixture version, code commit, parser/engine versions, processing mode, option template, expected values, observed values and reviewer. Thresholds require product and operations approval; this repository intentionally does not invent pass scores without a gold set.
