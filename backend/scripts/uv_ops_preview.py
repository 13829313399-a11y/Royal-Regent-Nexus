"""Explicit isolated acceptance server. Never used by application startup.

Requires a migrated PostgreSQL database named uv_ops_preview on loopback:55439.
The account and all records are visibly synthetic. No existing business store.
"""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
database=os.environ.get('UV_PREVIEW_DATABASE','uv_ops_preview')
if database not in {'uv_ops_preview','uv_ops_preview_v2','uv_ops_preview_v3'}:
    raise SystemExit('Only explicitly disposable UV preview databases are allowed')
os.environ['DATABASE_URL']='postgresql+psycopg://uvqa@127.0.0.1:55439/'+database
os.environ['UV_OPS_ENABLED']='true'
os.environ['AUTHZ_MODE']='enforce'
os.environ['AUTHZ_WRITES_ENABLED']='false'
os.environ['SEED_DEFAULT_ACCOUNTS']='false'
os.environ['THREE_D_CONNECTOR_ENABLED']='false'
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from app.api import auth, uv_operations, uv_agent
from app.db import SessionLocal
from app.models.auth import AuthUser, AuthUserRole, AuthRole, AuthRolePermission, AuthPermission
from app.models import uv_operations as m
from app.services.auth import seed_auth_defaults, make_password_hash, now_text
from app.services.permission_codes import UV_OPS_PERMISSION_CODES
from app.services.uv_operations import exports
from sqlalchemy import select


def seed_account():
    with SessionLocal() as db:
        assert db.bind.url.database==database and db.bind.url.port==55439
        seed_auth_defaults(db)
        if db.get(AuthUser,'uv-qa-user') is None:
            salt,digest=make_password_hash('Uv-QA-only-2026!')
            now=now_text()
            db.add(AuthUser(id='uv-qa-user',username='uvqa',display_name='合成验收员',password_salt=salt,password_hash=digest,status='active',force_password_change=0,created_at=now,updated_at=now))
            db.add(AuthRole(id='uv-qa-role',code='uv-qa-role',name='UV 合成验收',description='Disposable local acceptance only'))
            db.flush()
            for permission in db.scalars(select(AuthPermission).where(AuthPermission.code.in_(UV_OPS_PERMISSION_CODES))):
                db.add(AuthRolePermission(id='uv-qa:'+permission.id,role_id='uv-qa-role',permission_id=permission.id))
            db.add(AuthUserRole(id='uv-qa-binding',user_id='uv-qa-user',role_id='uv-qa-role',factory_id='huakang-a',department='production'))
        db.get(m.UvOpsSettings,'huakang-a').data_mode='synthetic'
        db.commit()


@asynccontextmanager
async def lifespan(app):
    seed_account()
    task=asyncio.create_task(exports.worker())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app=FastAPI(title='UV isolated synthetic acceptance',lifespan=lifespan)
app.include_router(auth.router)
app.include_router(uv_operations.router)
app.include_router(uv_agent.router)


@app.get('/health')
def health():
    return dict(status='ok',data_mode='synthetic',database=database,process_id=os.getpid())


if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8019)
