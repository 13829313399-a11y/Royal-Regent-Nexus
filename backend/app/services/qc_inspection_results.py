"""New judgments are four-valued; historical storage and exports remain lossless."""
ALLOWED_INSPECTION_RESULTS = ('PASS', 'FAIL', 'PENDING', 'LG')
RESULTS = ('PASS', 'FAIL', 'PENDING', 'REJ', 'COND', 'HOLD', 'LG')
EDITABLE_RESULTS = ('', *ALLOWED_INSPECTION_RESULTS)
