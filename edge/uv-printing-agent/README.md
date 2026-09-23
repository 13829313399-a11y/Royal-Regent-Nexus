# Royal Regent UV agent 1.0

Read-only outbound evidence collector. Simulator and `synthetic-csv-v1` demonstrate the pipeline, not a verified vendor adapter. No native print/pause/cancel command, UI automation, network-share WAL or generic shell execution is shipped.

## Install and enroll

1. Build on Windows with Python 3.11+ and `pip install .[test,package]`; run `scripts/package.ps1 -Python <venv/python.exe>`. Packaging locks APSW 3.53.4.0 and pywin32 311. Record the executable hash and `diagnostics` runtime versions.
2. Copy the package to the approved collection PC. Configure HTTPS origin, a local state directory and specifically authorized log files. Production defaults do not allow HTTP; loopback HTTP is solely for isolated tests.
3. As administrator, run `install.ps1 -Executable <exe> -ConfigPath <toml>`. The service uses LocalService with a dedicated service SID, no interactive desktop access. Grant that SID read-only access to approved logs. Do not grant access to the whole RIP/program/user directory.
4. In Nexus create an agent and obtain its one-time 15-minute pairing code. Run `rr-uv-agent.exe --config <toml> enroll`; the prompt does not echo the code. Credential and enrollment identity are durably DPAPI-protected before the request, so a lost response can safely be retried with the same identity.
5. Bind the exact machine/source/version in Nexus, then `Start-Service RRUvAgent`. Observe API, agent, collector and RIP evidence independently. Capability claims remain fixture-only until site validation.

## Durability and recovery

Outbox, per-source byte cursor and monotonically increasing sequence commit together under SQLite WAL + FULL. Only `persisted`/`duplicate` per-event responses remove rows; rejected events remain quarantined and do not block other events. Acknowledgment watermarks advance only through contiguous sequences. Restart resumes the same stream. Low disk or queue capacity stops source cursor advancement and logs a diagnostic; it never discards existing critical evidence. Source logs must be retained beyond the maximum offline window; no program can recover logs removed before collection.

Retryable rejections (for example a new stream requiring source rebind) stay queued, not quarantined. A new pairing identity requires a separate state directory; retain the previous identity and outbox for reconciliation. The saved credential is pinned to the configured server origin. Never copy a token to another origin or silently reuse an old queue under a new identity.

Back up with SQLite's backup API while running, or stop the service before copying database plus any WAL/SHM. Never copy only the main database while active. Restoring an old backup is a manual recovery: preserve its outbox, revoke/re-enroll identity and create a new source binding; do not silently reuse historical sequence space. Keep the recovered evidence for explicit reconciliation.

CSV identity includes file identity, rotation generation and byte offsets. Half lines wait; invalid rows preserve original bytes in local quarantine. UTF-8/GBK/GB18030 are explicit. A new native job must have a new native identity; cumulative counts 0,1,3 mean 3 boards. Counts and ink are observations, never automatic output or stock movements.

Rotation drains unread bytes from the previous file identity when that file remains in the same directory (bounded scan of 1000 entries). Rows over 64 KB are quarantined by size/hash without unbounded memory; valid following rows continue. Deleted unread source logs cannot be reconstructed. Only the exact synthetic CSV schema is shipped, not an arbitrary vendor format mapper.

The service reads filesystem logs in session zero. Locked screen/logoff/RDP behavior needs actual site acceptance. An unavailable UI source is unsupported, not silently replaced by CPU/process heuristics.

Upgrade: stop service, back up state using the method above, replace only executable, retain config/identity/outbox, start and verify queue drains without duplicate runs. Uninstall removes service registration and preserves all evidence files. Revoke its token in Nexus separately.

## Runtime basis

Packaged exe was exercised against an isolated synthetic API: 8 seconds running, forced stop, 5 seconds after restart, 4 Run records, queue/quarantine both zero, unchanged 2 manual production entries. Interactive CLI enrollment was not automated; the same DPAPI enrollment library prepared its state. SCM installation and locked/logged-out/RDP behavior remain site gates.

`scripts/benchmark_capacity.py` persisted and restored 259200 events (20 machines × 72 hours × 1 job/minute × 3 key events), occupying 243666944 bytes. Batch enqueue p50/p95 was 168.224/211.966 ms, local ACK drain 6794.49 events/second, zero failures. This is an accelerated capacity model, not a 72-hour soak or measured network recovery. See [test evidence](../../docs/uv-operations/TEST_EVIDENCE.md).

[SQLite WAL documentation](https://www.sqlite.org/wal.html#walreset) describes the WAL-reset correction in 3.51.3 and backports. The agent refuses affected versions. [APSW package](https://pypi.org/project/apsw/3.53.4.0/) supplies its own SQLite independently of the backend Python installation.
