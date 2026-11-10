"""Read the observer leases and the last real device frames in one database snapshot."""
import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import text

from app.db import SessionLocal


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def snapshot():
    with SessionLocal() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        db.execute(text("SET LOCAL statement_timeout='5s'"))
        # The small fleet query uses indexed probes. JIT compilation of the
        # historical audit checks costs more than executing the query itself.
        db.execute(text('SET LOCAL jit=off'))
        now = db.scalar(text('SELECT CURRENT_TIMESTAMP'))
        floor = (now - timedelta(minutes=4)).isoformat(timespec='milliseconds')
        history_floor = (now - timedelta(hours=6)).isoformat(timespec='milliseconds')
        rows = db.execute(text("""
            SELECT p.machine_no, p.connected, c.connection_owner, c.connection_enabled, c.lan_host,
                   c.certificate_fingerprint, c.leader_leased_until, i.status, i.last_seen_at,
                   e.observed_at, e.received_at, h.observed_at AS good_at, h.received_at AS good_received
            FROM three_d_printing_printers p
            JOIN three_d_printing_printer_connections c ON (p.factory_id,p.id) = (c.factory_id,c.printer_id)
            LEFT JOIN three_d_printing_connector_instances i ON (c.factory_id,c.leader_instance_id) = (i.factory_id,i.id)
            LEFT JOIN LATERAL (
                SELECT observed_at, received_at FROM three_d_printing_printer_state_events e
                WHERE (e.factory_id,e.printer_id) = (p.factory_id,p.id) AND received_at >= :floor
                    AND e.raw_payload_json::jsonb->>'connected' = 'true'
                ORDER BY received_at DESC LIMIT 1
            ) e ON TRUE
            LEFT JOIN LATERAL (
                SELECT h.observed_at, h.received_at FROM three_d_printing_printer_state_events h
                WHERE (h.factory_id,h.machine_no,h.printer_id) = (p.factory_id,p.machine_no,p.id)
                    AND h.observed_at = p.last_seen_at AND h.observed_at >= :history_floor
                    AND h.connector_instance_id = c.leader_instance_id
                    AND h.raw_payload_json::jsonb->>'connected' = 'true'
                    AND (
                        h.raw_payload_json::jsonb->>'leader_lease_id' = c.leader_lease_id
                        OR (
                            h.state NOT IN ('OFFLINE', 'STALE')
                            AND h.raw_payload_json::jsonb->>'site_id' = c.site_id
                            AND h.raw_payload_json::jsonb->>'printer_id' = p.id
                            AND h.raw_payload_json::jsonb->>'connection_session_id' = h.connection_session_id
                            AND EXISTS (
                                SELECT 1 FROM three_d_printing_audit_events a
                                WHERE (a.factory_id, a.entity_id) = (p.factory_id, p.id)
                                    AND a.entity_type = 'printer_ownership' AND a.action = 'acquired'
                                    AND a.actor_id = c.leader_instance_id AND a.created_at <= h.observed_at
                                    AND a.detail_json::jsonb->>'lease_id' = h.raw_payload_json::jsonb->>'leader_lease_id'
                            )
                            AND EXISTS (
                                SELECT 1 FROM three_d_printing_audit_events a
                                WHERE (a.factory_id, a.entity_id) = (p.factory_id, p.id)
                                    AND a.entity_type = 'printer_ownership' AND a.action = 'acquired'
                                    AND a.actor_id = c.leader_instance_id AND a.created_at >= h.received_at
                                    AND a.detail_json::jsonb->>'lease_id' = c.leader_lease_id
                            )
                            AND NOT EXISTS (
                                SELECT 1 FROM three_d_printing_audit_events a
                                WHERE (a.factory_id, a.entity_id) = (p.factory_id, p.id)
                                    AND a.created_at >= h.observed_at
                                    AND (a.entity_type = 'printer_connection' OR
                                         (a.entity_type = 'printer_ownership' AND a.action = 'acquired'
                                          AND a.actor_id IS DISTINCT FROM c.leader_instance_id))
                            )
                        )
                    )
                ORDER BY h.received_at LIMIT 1
            ) h ON TRUE
            WHERE p.factory_id='huakang-a' AND c.site_id='3dsite-huakang-a-heyuan' ORDER BY p.machine_no
        """), {'floor': floor, 'history_floor': history_floor}).mappings().all()
        if [r['machine_no'] for r in rows] != list(range(1, 19)):
            raise ValueError('incomplete_fleet')
        mapping = '\n'.join(f"{r['machine_no']}|{r['lan_host']}|{r['certificate_fingerprint'].lower()}" for r in rows)
        printers = []
        healthy = True
        for row in rows:
            until, heartbeat = stamp(row['leader_leased_until']), stamp(row['last_seen_at'])
            healthy = healthy and bool(row['connection_enabled'] and row['connection_owner'] == 'cloud-observer'
                                       and row['status'] == 'active' and until and until > now and heartbeat
                                       and 0 <= (now - heartbeat).total_seconds() < 45)
            seen, received = stamp(row['observed_at']), stamp(row['received_at'])
            ages = [(now - t).total_seconds() for t in (seen, received) if t]
            fresh = bool(row['connected'] and len(ages) == 2 and min(ages) >= 0 and max(ages) <= 30)
            silent = not ages or (len(ages) == 2 and min(ages) >= 120)
            good, arrival = stamp(row['good_at']), stamp(row['good_received'])
            last_good = 0
            if good and arrival and now - timedelta(hours=6) <= good <= arrival <= now and (arrival - good).total_seconds() <= 30:
                last_good = int(good.timestamp())
            printers.append({'n': row['machine_no'], 'fresh': fresh, 'silent': silent,
                             'last_good_utc': last_good, 'ip': row['lan_host']})
        return {'timestamp': int(now.timestamp()), 'fleet': 'huakang-a/heyuan/18', 'version': 1,
                'mapping': hashlib.sha256(mapping.encode('ascii')).hexdigest(), 'collector_ok': healthy,
                'printers': printers}


if __name__ == '__main__':
    print(json.dumps(snapshot(), separators=(',', ':')))
