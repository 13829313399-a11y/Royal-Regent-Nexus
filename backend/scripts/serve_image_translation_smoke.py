"""Loopback-only synthetic QA API and worker, with its own disposable DB/files."""
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.api.document_tools import router
from app.core.config import settings
from app.db import Base, get_db
from app.models.auth import AuthUser
from app.models.document_tools import DocumentToolSource, DocumentToolJob, DocumentToolArtifact, DocumentToolCorrection
from app.services.auth import get_current_user
from app.services.document_tools import pipeline, storage

root = Path(os.environ['RR_IMAGE_QA_DIR']).resolve()
root.mkdir(parents=True, exist_ok=True)
settings.document_tools_storage_dir = str(root / 'files')
settings.document_tools_ai_mode = 'off'
engine = create_engine('sqlite:///' + str(root / 'qa.db'), connect_args={'check_same_thread': False})
@event.listens_for(engine, 'connect')
def foreign_keys(connection, _):
    connection.execute('PRAGMA foreign_keys=ON')
Base.metadata.create_all(engine, tables=[AuthUser.__table__, DocumentToolSource.__table__, DocumentToolJob.__table__, DocumentToolArtifact.__table__, DocumentToolCorrection.__table__])
sessions = sessionmaker(engine, expire_on_commit=False)
with sessions() as session:
    for name in ('qa-alice', 'qa-bob'):
        if session.get(AuthUser, name) is None:
            session.add(AuthUser(id=name, username=name, password_salt='qa', password_hash='qa'))
    session.commit()

stop = threading.Event()
def worker():
    while not stop.is_set():
        storage.atomic_json(storage.resolve('heartbeats/synthetic.json'), {'timestamp': time.time()})
        if not pipeline.run_one(sessions):
            stop.wait(.2)

@asynccontextmanager
async def lifespan(app):
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    yield
    stop.set()
    thread.join(timeout=5)

app = FastAPI(lifespan=lifespan)
app.include_router(router)
repo = Path(__file__).resolve().parents[2]
app.mount('/image-translation', StaticFiles(directory=repo / 'shinobu-web/apps/web/dist', html=True))
app.mount('/brand', StaticFiles(directory=repo / 'public/brand'))
def database():
    with sessions() as session:
        yield session
def account(request: Request):
    return SimpleNamespace(id='qa-bob' if request.headers.get('x-qa-account') == 'qa-bob' else 'qa-alice')
app.dependency_overrides[get_db] = database
app.dependency_overrides[get_current_user] = account
@app.get('/api/auth/me')
def me(request: Request):
    return {'id': account(request).id, 'force_password_change': False}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8001)
