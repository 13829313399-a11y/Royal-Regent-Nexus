"""No global database URL: each factory trial owns one explicitly supplied SQLite file."""
import json
from pathlib import Path
import sqlite3
from sqlalchemy import create_engine,event,inspect
from sqlalchemy.orm import DeclarativeBase,sessionmaker
from app.history import validate_database,ALLOWED_TABLES

class Base(DeclarativeBase):
    pass


def local_sessions(path,*,new_database=False):
    with sqlite3.connect(path) as database:
        validate_database(database)
    engine=create_engine('sqlite:///'+str(path),connect_args={'check_same_thread':False,'timeout':15})
    @event.listens_for(engine,'connect')
    def sqlite_constraints(connection,_):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=15000')
    from app.models import customer_order_ledger
    guards=json.loads(Path(__file__).with_name('ledger-guards.json').read_text())
    try:
        with engine.begin() as connection:
            if new_database:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
                Base.metadata.create_all(connection)
                for statement in guards:connection.exec_driver_sql(statement)
            schema=inspect(connection)
            if set(schema.get_table_names())!=ALLOWED_TABLES:
                raise RuntimeError('本机订单库表结构不完整，未自动重建或覆盖，请保留原数据。')
            for name,table in Base.metadata.tables.items():
                if {column['name'] for column in schema.get_columns(name)}!=set(table.columns.keys()):
                    raise RuntimeError('本机订单库字段不符，未自动重建或覆盖，请保留原数据。')
            existing={row[0]:row[1] for row in connection.exec_driver_sql("SELECT name,sql FROM sqlite_master WHERE type='trigger'")}
            for statement in guards:
                name=statement.split()[2]
                if name not in existing or existing[name].rstrip(';')!=statement.rstrip(';'):
                    raise RuntimeError('本机订单证据保护规则与记录版本不符，已停止启动。')
    except BaseException:
        engine.dispose();raise
    return sessionmaker(engine,autoflush=False,expire_on_commit=False)
