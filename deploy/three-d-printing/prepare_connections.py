"""Prepare device connection metadata without opening printer sessions."""
import argparse
import csv
import ipaddress
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from sqlalchemy import select
from app.models import three_d_printing as m


def prepare(db, rows, *, observed=False):
    numbers, addresses = set(), set()
    created = 0
    for row in rows:
        number = int(row['machine_no'])
        address = ipaddress.IPv4Address(row['ip'])
        if not 1 <= number <= 11 or number in numbers or str(address) in addresses or not address.is_private:
            raise ValueError('Invalid printer number or LAN address')
        numbers.add(number); addresses.add(str(address))
        printer = db.scalar(select(m.ThreeDPrintingPrinter).where(
            m.ThreeDPrintingPrinter.factory_id == 'huakang-a',
            m.ThreeDPrintingPrinter.machine_no == number,
        ))
        if printer is None:
            raise ValueError(f'Machine {number} is not initialized')
        existing = db.get(m.ThreeDPrintingPrinterConnection, printer.id)
        if existing is not None:
            if observed:
                pin = row['cert_sha256'].lower()
                if not re.fullmatch('[a-f0-9]{64}',pin):
                    raise ValueError('Missing onsite certificate hash')
                if existing.connection_enabled:
                    raise ValueError(f'Machine {number} already active; stop its session before reconfiguration')
                if (existing.lan_host, existing.certificate_fingerprint)!=(str(address),pin):
                    existing.lan_host=str(address)
                    existing.certificate_fingerprint=pin
                    existing.connection_revision+=1
            continue
        db.add(m.ThreeDPrintingPrinterConnection(
            printer_id=printer.id, factory_id='huakang-a', site_id='3dsite-huakang-a-heyuan',
            lan_host=str(address), mqtt_port=8883, credential_ref=f'printer-{number:02}',
            certificate_fingerprint=row['cert_sha256'] if observed else '', connection_enabled=False, connection_owner='edge-legacy',
        ))
        created += 1
    db.flush()
    return {'created':created,'existing':len(rows)-created,'sessions_started':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--printers',help='CSV with machine_no and ip')
    group.add_argument('--network-config',help='Cloud config built from the physically checked Windows report')
    args=parser.parse_args()
    from app.db import SessionLocal
    if args.network_config:
        sys.path.insert(0,str(Path(__file__).parent/'network'))
        from tailscale_doctor import validate
        data=json.loads(Path(args.network_config).read_text(encoding='utf-8-sig'))
        validate(data)
        rows=data['printers']
    else:
        with open(args.printers,encoding='utf-8-sig',newline='') as handle:
            rows=list(csv.DictReader(handle))
    with SessionLocal() as db:
        result=prepare(db,rows,observed=bool(args.network_config))
        db.commit()
    print(json.dumps(result))


if __name__=='__main__': main()
