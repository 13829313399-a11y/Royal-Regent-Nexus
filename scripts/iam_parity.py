"""Compare existing IAM authorizations across two checkouts and both real startup sequences."""
import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import socket
import subprocess
import sys
import tempfile
from uuid import uuid4

from dotenv import dotenv_values

PHASES = ("old_before", "old_after", "candidate_before", "candidate_after")
PAIRS = (("old_before", "old_after"), ("candidate_before", "candidate_after"),
         ("old_before", "candidate_before"), ("old_after", "candidate_after"),
         ("old_before", "candidate_after"))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def code_id(root):
    files = sorted((root/"backend"/"app").rglob("*.py"))
    if not files:
        raise ValueError("Checkout must contain backend/app")
    h = hashlib.sha256()
    for path in files:
        h.update(path.relative_to(root).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


@contextmanager
def clones(args, work, phases):
    if args.snapshot:
        source = args.snapshot.resolve(strict=True)
        master = work/"master.sqlite"
        with ExitStack() as resources:
            src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            resources.callback(src.close)
            dst = sqlite3.connect(master)
            resources.callback(dst.close)
            src.backup(dst)
        with master.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        urls = {}
        for name in phases:
            target = work/(name + ".sqlite")
            shutil.copyfile(master, target)
            urls[name] = "sqlite:///" + target.as_posix()
        yield urls, {"engine": "sqlite", "snapshot_sha256": digest}
        return

    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    url = make_url(os.environ[args.postgres_template_env])
    if url.get_backend_name() != "postgresql" or not url.database or url.database in {"postgres", "template0", "template1"}:
        raise ValueError("Provide a dedicated restored PostgreSQL snapshot database as template")
    master = "iam_parity_" + uuid4().hex
    engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn, ExitStack() as owned:
            quote = engine.dialect.identifier_preparer.quote_identifier
            def clone(name, template):
                conn.exec_driver_sql("CREATE DATABASE " + quote(name) + " TEMPLATE " + quote(template))
                owned.callback(conn.exec_driver_sql, "DROP DATABASE " + quote(name))
            # Only databases newly created by this process are run or dropped.
            clone(master, url.database)
            urls = {}
            for phase in phases:
                name = master + "_" + phase
                clone(name, master)
                urls[phase] = url.set(database=name).render_as_string(hide_password=False)
            yield urls, {"engine": "postgresql", "template_copy": master}
    finally:
        engine.dispose()


def union_domain(results):
    domain = {key: sorted({v for result in results for v in result[key]})
              for key in ("codes", "departments", "factories")}
    times = {}
    for result in results:
        for uid, values in result["times"].items():
            times.setdefault(uid, set()).update(values)
    session_times = {}
    for result in results:
        for uid, sessions in result.get("session_times", {}).items():
            merged = session_times.setdefault(uid, {})
            for sid, values in sessions.items():
                merged.setdefault(sid, set()).update(values)
    domain["session_times"] = {uid:{sid:sorted(t) for sid,t in items.items()} for uid,items in session_times.items()}
    domain["departments"].append(None)  # the backend also accepts an omitted department
    domain["times"] = {uid: sorted(v) for uid, v in times.items()}
    domain["evaluators"] = ["canonical", "configured_runtime"]
    return domain


def differences(left, right, path=()):
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                yield path + (key,), "added" if key in right else "removed"
            else:
                yield from differences(left[key], right[key], path+(key,))
    elif left != right:
        yield path, "changed"


def rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            uid, when, bits, sessions = json.loads(line)
            yield (uid, when), bytes.fromhex(bits), sessions


def compare_streams(left, right, domain, emit):
    """Merge streams by employee and time, comparing every packed allow/deny cell."""
    a, b = iter(rows(left)), iter(rows(right))
    first, second = next(a, None), next(b, None)
    checks = 0
    while first or second:
        if not second or first and first[0] < second[0]:
            emit({"employee": first[0][0], "time": first[0][1], "matrix": "removed"})
            first = next(a, None)
            continue
        if not first or second[0] < first[0]:
            emit({"employee": second[0][0], "time": second[0][1], "matrix": "added"})
            second = next(b, None)
            continue
        (uid, when), old, sessions = first
        _, new, new_sessions = second
        if len(old) != len(new):
            raise ValueError("Evaluation matrix size mismatch")
        evaluators = domain.get("evaluators", ["canonical"])
        if old:
            checks += len(evaluators) * len(domain["codes"]) * len(domain["factories"]) * len(domain["departments"])
        for i, (before, after) in enumerate(zip(old, new)) if old != new else ():
            changed = before ^ after
            while changed:
                bit = changed & -changed
                changed ^= bit
                flat = i*8 + bit.bit_length()-1
                pair, d = divmod(flat, len(domain["departments"]))
                e_and_c, f = divmod(pair, len(domain["factories"]))
                e, c = divmod(e_and_c, len(domain["codes"]))
                emit({"employee": uid, "time": when, "code": domain["codes"][c], "evaluator": evaluators[e],
                      "factory": domain["factories"][f], "department": domain["departments"][d],
                      "before_allow": bool(before & bit), "after_allow": bool(after & bit)})
        for path, change in differences(sessions, new_sessions):
            emit({"employee": uid, "time": when, "session": list(path), "change": change,
                  "before": sessions.get(path[0]), "after": new_sessions.get(path[0])})
        first, second = next(a, None), next(b, None)
    return checks


def compare(args):
    anchor = datetime.fromisoformat(args.at.replace("Z", "+00:00"))
    if anchor.tzinfo is None:
        raise ValueError("--at requires a timezone")
    anchor = anchor.astimezone(timezone.utc).isoformat()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    explicit = dotenv_values(args.config)
    # Keep OS runtime settings; no app flags/credentials leak in from the launching shell.
    base_env = {k:v for k,v in os.environ.items() if k.upper() in {
        "WINDIR", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
        "COMSPEC", "PATHEXT", "PROGRAMDATA", "LANG", "LC_ALL", "SYSTEMDRIVE", "TZ"}}
    base_env.update({k:v for k,v in explicit.items() if v is not None})
    if args.require_utc:
        base_env["IAM_PARITY_REQUIRE_UTC"] = "1"
        base_env["TZ"] = "UTC"
    if args.isolated_network:
        base_env["IAM_PARITY_OFFLINE"] = "1"
    base_env["PYTHONUTF8"] = "1"
    base_env["PYTHONDONTWRITEBYTECODE"] = "1"
    phases = list(PHASES)
    pairs = list(PAIRS)
    roots = {"old": args.old.resolve(strict=True), "candidate": args.candidate.resolve(strict=True)}
    if args.additional_candidate:
        roots["alternate"] = args.additional_candidate.resolve(strict=True)
        phases.extend(("alternate_before", "alternate_after"))
        pairs.extend((a.replace("candidate","alternate"), b.replace("candidate","alternate")) for a,b in PAIRS
                     if "candidate" in a or "candidate" in b)
    (output/"progress").mkdir()
    report = {"status": "incomplete", "scope_label": args.label, "anchor_utc": anchor,
              "code_sha256": {k:code_id(v) for k,v in roots.items()},
              "explicit_config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(), "comparisons": {},
              "deployment_alembic_upgrade_head": args.deployment_migrations, "require_utc": args.require_utc}
    dump(output/"summary.json", report)
    probe = Path(__file__).with_name("iam_parity_probe.py").resolve()
    with tempfile.TemporaryDirectory(prefix="iam-parity-") as tmp:
        work = Path(tmp)
        with clones(args, work, phases) as (urls, provenance):
            report["input"] = provenance
            if base_env.get("QC_DEPARTMENT_MANAGED", "").lower() in {"true", "1", "yes", "on"}:
                with socket.socket() as isolated_port:
                    isolated_port.bind(("127.0.0.1", 0))
                    base_env["QC_DEPARTMENT_URL"] = "http://127.0.0.1:" + str(isolated_port.getsockname()[1])
            def run(phase, mode, out, value):
                root = roots[phase.split("_")[0]]
                sandbox = work/phase
                sandbox.mkdir(exist_ok=True)
                env = {**base_env, "DATABASE_URL": urls[phase], "IAM_PARITY_PROGRESS_FILE": str(output/"progress"/(phase+".json"))}
                for key in ("QC_DEPARTMENT_DATA_DIR", "ASSISTANT_STORAGE_DIR", "COLLABORATION_STORAGE_DIR",
                            "THREE_D_ASSET_DIR", "DOCUMENT_TOOLS_STORAGE_DIR"):
                    env[key] = str(sandbox/key.lower())
                interpreter = args.old_python if phase.startswith("old_") else args.candidate_python
                subprocess.run([interpreter, str(probe), str(root), mode, str(out), str(value)],
                               env=env, cwd=sandbox, check=True)
            inventory = {}
            for phase in phases:
                if args.deployment_migrations and phase != "old_before":
                    run(phase, "migrate", "", "")
                if phase.endswith("_after"):
                    run(phase, "startup", "", "")
                target = work/(phase+".json")
                run(phase, "inventory", target, anchor)
                inventory[phase] = json.loads(target.read_text(encoding="utf-8"))
            report["input"]["source_state_sha256"] = hashlib.sha256(json.dumps(inventory["old_before"]["sources"], sort_keys=True,
                                                       separators=(",", ":")).encode()).hexdigest()
            report["input"]["engine_version"] = inventory["old_before"].get("engine_version")
            domain = union_domain(inventory.values())
            dump(work/"domain.json", domain)
            report.update({"phase": "evaluating", "employee_count":len(domain["times"]),
                    "employee_instants":sum(map(len,domain["times"].values())), "permission_count":len(domain["codes"])})
            dump(output/"summary.json",report)
            with ThreadPoolExecutor(max_workers=min(len(phases), os.cpu_count() or 1)) as workers:
                checks = [workers.submit(run, phase, "evaluate", work/(phase+".jsonl"), work/"domain.json")
                          for phase in phases]
                for check in checks:
                    check.result()
            report.update({"configuration": {k:v["settings"] for k,v in inventory.items()},
                "runtimes": {k:v.get("runtime") for k,v in inventory.items()},
                "employee_count": len(domain["times"]), "permission_count": len(domain["codes"]),
                "factories": domain["factories"], "departments": domain["departments"], "evaluators": domain["evaluators"],
                "employee_instants": sum(len(v) for v in domain["times"].values()),
                "session_count": sum(len(s) for s in domain["session_times"].values()),
                "session_time_checks_per_phase": sum(2*len(set(t) | set(domain["times"][u])) for u,ss in domain["session_times"].items() for t in ss.values())})
            report["difference_file"] = "differences.jsonl.gz" if args.compress_differences else "differences.jsonl"
            diff_path = output/report["difference_file"]
            writer = gzip.open(diff_path, "wt", encoding="utf-8", compresslevel=1) if args.compress_differences else diff_path.open("w", encoding="utf-8")
            with writer as stream:
                for old, new in pairs:
                    label = old + "_vs_" + new
                    count = 0
                    def emit(row):
                        nonlocal count
                        count += 1
                        stream.write(json.dumps({"comparison":label, **row}, ensure_ascii=False) + "\n")
                    if inventory[old]["settings"] != inventory[new]["settings"]:
                        emit({"configuration": "changed"})
                    for path, change in differences(inventory[old]["sources"], inventory[new]["sources"]):
                        emit({"employee": path[0], "field": list(path[1:]), "change": change})
                    checks = compare_streams(work/(old+".jsonl"), work/(new+".jsonl"), domain, emit)
                    report["comparisons"][label] = {"decision_checks":checks, "differences":count}
    if report["code_sha256"] != {k:code_id(v) for k,v in roots.items()}:
        raise RuntimeError("Checkout changed during comparison; rerun using immutable release sources")
    report["phase"] = "finished"
    report["candidate_status"] = {}
    for variant in roots.keys()-{"old"}:
        relevant = [v for k,v in report["comparisons"].items() if variant in k or k == "old_before_vs_old_after"]
        report["candidate_status"][variant] = "blocked" if any(v["differences"] for v in relevant) else "matched"
    report["status"] = "blocked" if any(v["differences"] for v in report["comparisons"].values()) else "matched"
    dump(output/"summary.json", report)
    print(f"{report['status']}  {output / 'summary.json'}")
    return int(report["status"] != "matched")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True, help="actual deployed source checkout")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--additional-candidate", type=Path, help="optional second release evaluated against the same actual baseline and union of decisions")
    parser.add_argument("--old-python", default=sys.executable, help="baseline release Python runtime")
    parser.add_argument("--candidate-python", default=sys.executable, help="candidate Python runtime")
    parser.add_argument("--config", type=Path, required=True, help="shared explicit application environment file")
    parser.add_argument("--at", required=True, help="same UTC or explicit offset timestamp for both releases")
    parser.add_argument("--deployment-migrations", action="store_true", help="execute the deployment Alembic upgrade head before lifespan, record candidate migration-only state")
    parser.add_argument("--compress-differences", action="store_true", help="losslessly compress the employee-level private difference stream")
    parser.add_argument("--isolated-network", action="store_true", help="deny application TCP connections except to its isolated local PostgreSQL port")
    parser.add_argument("--require-utc", action="store_true", help="use and validate UTC wall clock and legacy local timestamp conversion")
    parser.add_argument("--output", type=Path, required=True, help="new directory")
    parser.add_argument("--label", required=True, help="snapshot provenance e.g. local synthetic data")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", type=Path, help="source SQLite snapshot, opened read-only")
    source.add_argument("--postgres-template-env", help="environment variable holding a restored offline snapshot PostgreSQL URL")
    sys.exit(compare(parser.parse_args()))
