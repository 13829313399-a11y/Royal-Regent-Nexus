"""Optional migrated SQLite index; no startup or request-time DDL."""
NAME = 'ix_cutting_period_headers'
COLUMNS = ('id', 'factory_id', 'month', 'version', 'action', 'actor_id', 'actor_name', 'created_at', 'reason')


def select_hint(reader):
    rows = reader.execute('PRAGMA index_list(cutting_ops_period_events)').fetchall()
    match = next((row for row in rows if row[1] == NAME), None)
    if match is None:
        return ''  # Existing 0172–0184 databases retain their original reads.
    keys = [row for row in reader.execute('PRAGMA index_xinfo(ix_cutting_period_headers)').fetchall() if row[5]]
    if (match[2] or match[4] or tuple(row[2] for row in keys) != COLUMNS
            or any(row[1] < 0 or row[3] or row[4] != 'BINARY' for row in keys)):
        from app.services.cutting_ops import require
        require(False, '月结历史索引与发布契约不符，请核对显式迁移', 503)
    return ' INDEXED BY ix_cutting_period_headers'
