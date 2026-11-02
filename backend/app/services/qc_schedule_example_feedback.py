"""Temporary QC example feedback; never opens inspection or Nexus databases."""
import sqlite3
from contextlib import closing
from pathlib import Path
from fastapi import HTTPException
from app.core.config import settings


def store_path():
    return Path(settings.qc_department_data_dir).resolve() / '_schedule_examples' / 'feedback.sqlite3'


def read_feedback(payload):
    path = store_path()
    values = {}
    if path.exists():
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
                values = {r[0]: r[1:] for r in conn.execute(
                    'SELECT row_id, completion, remark, revision FROM feedback WHERE factory=? AND source=?',
                    (payload['factory_id'], payload['source']['sha256']))}
        except sqlite3.Error:
            raise HTTPException(503, '示例回填暂不可读取，请重试') from None
    for row in payload['items']:
        # Preserve the original schedule note separately from historical QC feedback.
        row['sourceRemark'] = row.get('remark', '')
        saved = values.get(row['id'])
        row['feedbackRevision'] = saved[2] if saved else 0
        if saved:
            row['completion'], row['remark'] = saved[:2]
    return payload


def save_feedback(payload, body, actor):
    fields = {'id', 'sourceSha256', 'completion', 'remark', 'revision'}
    if not isinstance(body, dict) or set(body) != fields:
        raise HTTPException(422, '仅允许保存示例的完成情况和备注')
    if (not isinstance(body['id'], str) or type(body['revision']) is not int or body['revision'] < 0
            or not isinstance(body['completion'], str) or len(body['completion']) > 500
            or not isinstance(body['remark'], str) or len(body['remark']) > 4000):
        raise HTTPException(422, '示例回填字段不正确或内容过长')
    if body['sourceSha256'] != payload['source']['sha256']:
        raise HTTPException(409, '示例版本已变化，请刷新数据后重试')
    row = next((r for r in payload['items'] if r['id'] == body['id']), None)
    if row is None:
        raise HTTPException(404, '示例排期不存在')
    path = store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=5)) as conn, conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS feedback (
                factory TEXT NOT NULL, source TEXT NOT NULL, row_id TEXT NOT NULL,
                completion TEXT NOT NULL, remark TEXT NOT NULL, revision INTEGER NOT NULL,
                updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY (factory, source, row_id))''')
            conn.execute('BEGIN IMMEDIATE')
            key = (payload['factory_id'], payload['source']['sha256'], row['id'])
            previous = conn.execute('SELECT revision FROM feedback WHERE factory=? AND source=? AND row_id=?', key).fetchone()
            current = previous[0] if previous else 0
            if current != body['revision']:
                raise HTTPException(409, '该示例已被更新，请刷新数据后重新填写')
            revision = current + 1
            conn.execute('''INSERT INTO feedback VALUES (?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(factory,source,row_id) DO UPDATE SET completion=excluded.completion,
                remark=excluded.remark,revision=excluded.revision,updated_by=excluded.updated_by,
                updated_at=excluded.updated_at''', (*key, body['completion'], body['remark'], revision, actor))
    except (sqlite3.Error, OSError):
        raise HTTPException(503, '示例回填保存失败，请刷新核对后重试') from None
    return {'example': True, 'id': row['id'], 'completion': body['completion'],
            'remark': body['remark'], 'feedbackRevision': revision}
