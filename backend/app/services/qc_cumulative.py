"""Legacy workbook archive access for summary reconciliation and history import.

The workbench no longer creates, replaces, merges, repairs or exports workbooks.
Existing immutable archive bytes and bindings remain available to the summary.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3

from fastapi import HTTPException
from app.core.config import settings

TEMPLATES=Path(__file__).resolve().parents[1]/'templates'/'qc-cumulative'
SCHEMA='''
CREATE TABLE IF NOT EXISTS archives(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,version_id INTEGER NOT NULL,filename TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS base_inputs(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,version_id INTEGER NOT NULL,filename TEXT NOT NULL,content BLOB NOT NULL,receipt TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS heads(factory TEXT PRIMARY KEY,current_id INTEGER NOT NULL,undo_id INTEGER,revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,content BLOB NOT NULL,snapshot TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(factory TEXT NOT NULL,actor TEXT NOT NULL,request_key TEXT NOT NULL,digest TEXT NOT NULL,status TEXT NOT NULL,response TEXT,started REAL NOT NULL,pid INTEGER NOT NULL,PRIMARY KEY(factory,actor,request_key));
CREATE TABLE IF NOT EXISTS repairs(id INTEGER PRIMARY KEY,factory TEXT NOT NULL,before_head TEXT NOT NULL,after_head TEXT NOT NULL,mapping TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL,rolled_back INTEGER NOT NULL DEFAULT 0);
'''

@contextmanager
def store(write=False):
    path=Path(settings.qc_department_data_dir).resolve()/'_cumulative'/'workbooks.sqlite3'
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path,timeout=60);conn.row_factory=sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys=ON');conn.executescript(SCHEMA)
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn;conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.close()

def template(factory):
    # Each factory needs its own approved template. Never clone Huaxing history to another factory.
    if not re.fullmatch('[a-z0-9-]+',factory):raise HTTPException(422,'厂区无效')
    folder=TEMPLATES/factory
    try:
        manifest=json.loads((folder/'manifest.json').read_text());content=(folder/'initial.xlsx').read_bytes()
    except (OSError,ValueError):raise HTTPException(503,'当前厂区尚未配置已验证的累计模板') from None
    if manifest.get('factory')!=factory or not manifest.get('validated') or sha256(content).hexdigest()!=manifest.get('sha256'):
        raise HTTPException(503,'累计模板校验未通过，原版本未修改')
    return content
