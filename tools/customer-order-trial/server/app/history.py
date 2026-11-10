"""Local immutable export evidence; this is not the ERP business order ledger."""
from datetime import datetime,timezone
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


APPLICATION_ID=0x434F5452
SCHEMA_VERSION=1
ALLOWED_TABLES={'trial_meta','exports','order_ledger_lines','order_ledger_versions','order_ledger_sources',
    'order_ledger_line_sources','order_ledger_dispatches','order_ledger_shipments','order_ledger_shipment_reversals','order_ledger_identities'}


def validate_database(db,*,allow_empty=False):
    tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    identity=db.execute('PRAGMA application_id').fetchone()[0]
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if allow_empty and not tables and identity==0 and version==0:return False
    if identity!=APPLICATION_ID or version!=SCHEMA_VERSION or not {'trial_meta','exports'}<=tables or tables-ALLOWED_TABLES:
        raise RuntimeError('此文件不是当前版本的订单本机试用数据库，已拒绝修改；请选用本试用包原数据文件夹。')
    return True


class History:
    def __init__(self,directory,factory):
        directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
        self.path=directory/'order_trial.sqlite3';self.factory=factory
        with self.connect() as db:
            self.new_database=not validate_database(db,allow_empty=True)
            if self.new_database:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE trial_meta (name TEXT PRIMARY KEY,value TEXT NOT NULL)')
                db.executemany('INSERT INTO trial_meta VALUES (?,?)',[('factory',factory),('schema','1')])
                db.execute('''CREATE TABLE exports (id TEXT PRIMARY KEY, request_hash TEXT UNIQUE NOT NULL,
                  customer_code TEXT NOT NULL, file_name TEXT NOT NULL, created_at TEXT NOT NULL,
                  row_count INTEGER NOT NULL, controls TEXT NOT NULL, output_sha256 TEXT NOT NULL, content BLOB NOT NULL)''')
                db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                for operation in ('UPDATE','DELETE'):
                    db.execute(f"CREATE TRIGGER exports_no_{operation.lower()} BEFORE {operation} ON exports BEGIN SELECT RAISE(ABORT,'Export history is append-only'); END")
            else:
                existing=dict(db.execute('SELECT name,value FROM trial_meta'))
                if existing.get('factory')!=factory or existing.get('schema')!='1':
                    raise RuntimeError('试用数据所属厂区或版本不匹配，请使用本厂区原数据文件夹。')
                actual={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
                if not {'exports_no_update','exports_no_delete'}<=actual:
                    raise RuntimeError('本机导出证据保护不完整，请保留原文件，未自动重建。')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally:
            db.close()

    def save_on(self,db,customer,filename,output,rows,controls):
        """Use an existing SQLite transaction so ledger + generated evidence commit together."""
        raw=json.dumps(controls,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        request_hash=sha256((self.factory+'\n'+customer+'\n'+raw).encode()).hexdigest()
        cursor=db.cursor();cursor.row_factory=sqlite3.Row
        try:
            row=cursor.execute('SELECT * FROM exports WHERE request_hash=?',(request_hash,)).fetchone()
            if row is None:
                ident=uuid4().hex
                cursor.execute('INSERT INTO exports VALUES (?,?,?,?,?,?,?,?,?)',(ident,request_hash,customer,filename,
                    datetime.now(timezone.utc).isoformat(),rows,raw,sha256(output).hexdigest(),output))
                row=cursor.execute('SELECT * FROM exports WHERE id=?',(ident,)).fetchone()
            return dict(row)
        finally: cursor.close()

    def save(self,customer,filename,output,rows,controls):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self.save_on(db,customer,filename,output,rows,controls)

    def list(self,page):
        with self.connect() as db:
            total=db.execute('SELECT count(*) FROM exports').fetchone()[0]
            rows=db.execute('SELECT id,customer_code,file_name,created_at,row_count,output_sha256 FROM exports ORDER BY created_at DESC,id LIMIT 20 OFFSET ?',((page-1)*20,)).fetchall()
            return {'total':total,'items':[dict(row) for row in rows]}

    def get(self,ident):
        with self.connect() as db:
            row=db.execute('SELECT * FROM exports WHERE id=?',(ident,)).fetchone()
            return dict(row) if row else None
