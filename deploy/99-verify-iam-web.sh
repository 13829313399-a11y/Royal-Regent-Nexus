#!/bin/sh
set -eu
cd /usr/share/nginx/html
index_sha="$(sha256sum index.html)"
index_sha="${index_sha%% *}"
receipt="/run/rrn-iam-approved/$index_sha.sha256"
if [ ! -r "$receipt" ]; then
    echo "IAM frontend startup check failed: no host approval for index $index_sha" >&2
    exit 1
fi
if ! sha256sum -c "$receipt" >/dev/null; then
    echo "IAM frontend startup check failed: approved static resources differ" >&2
    exit 1
fi
echo "IAM frontend startup check passed: $index_sha"
