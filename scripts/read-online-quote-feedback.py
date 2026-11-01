"""Read live quotation feedback through an existing administrative SSH connection.

Credentials and pinned host keys must remain outside Git. Install paramiko into an
isolated directory and pass --dependencies; never disable host-key verification.
The remote Python source runs in memory inside the API container, with a database
transaction enforced READ ONLY. No deployment or server-side file is required.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import sys


def remote_source(offset, limit):
    root = Path(__file__).resolve().parents[1]
    report = (root / "backend/app/services/module_feedback_report.py").read_text(encoding="utf-8")
    return report + f'''
import json
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
if engine.dialect.name != "postgresql":
    raise RuntimeError("Expected production PostgreSQL")
with Session(engine) as db:
    db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '30s'"))
    report = collect_report(db, offset={offset}, limit={limit})
    db.rollback()
print(json.dumps(report, ensure_ascii=False))
'''


def connection_values(path):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^\s*([^:：=]+)\s*[:：=]\s*(.*?)\s*$", line)
        if match:
            values[match[1].strip().lower()] = match[2]
    host = values.get("ip") or values.get("host") or values.get("主机")
    password = values.get("password") or values.get("密码")
    if not host or not password:
        raise ValueError("Connection file must contain IP and password fields")
    return dict(hostname=host, password=password,
                username=values.get("user") or values.get("用户名") or "root",
                port=int(values.get("port") or values.get("端口") or "22"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path)
    parser.add_argument("--container", required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.container) or args.offset < 0 or not 1 <= args.limit <= 200:
        parser.error("Invalid container or pagination")
    if args.dependencies:
        sys.path.insert(0, str(args.dependencies.resolve()))
    import paramiko
    client = paramiko.SSHClient()
    client.load_host_keys(str(args.known_hosts))
    try:
        client.connect(**connection_values(args.connection_file), timeout=15, auth_timeout=15,
                       banner_timeout=15, allow_agent=False, look_for_keys=False)
        stdin, stdout, stderr = client.exec_command(
            f"docker exec -i {shlex.quote(args.container)} python -", timeout=60)
        stdin.write(remote_source(args.offset, args.limit))
        stdin.flush()
        stdin.channel.shutdown_write()
        output = stdout.read().decode("utf-8")
        if stdout.channel.recv_exit_status() != 0:
            # Avoid disclosing runtime configuration in remote error messages.
            raise RuntimeError("Remote read-only report failed; check the API container and feedback tables")
        report = json.loads(output)
        if report.get("module") != "internal-quote" or any(row.get("module") != "internal-quote" for row in report["items"]):
            raise ValueError("Unexpected report scope")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Online feedback read failed ({type(error).__name__}); credentials were not printed.", file=sys.stderr)
        sys.exit(1)
