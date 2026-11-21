"""File-backed QC originals and previews. Photo IDs and approval snapshots stay stable."""
from contextvars import ContextVar
from functools import wraps
from threading import BoundedSemaphore
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import asyncio
import json
import logging
import os
import sqlite3
import time
import warnings
from uuid import uuid4
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from app.core.config import settings

# Also register in fresh export/read workers which have not processed an upload.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

SCHEMA = '''CREATE TABLE IF NOT EXISTS photo_assets (
 photo_id TEXT PRIMARY KEY REFERENCES photos(id), metadata TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS photo_assets_retry ON photo_assets(status,retry_at);'''
decode_slots=BoundedSemaphore(2)
def bounded(fn):
    @wraps(fn)
    def run(*args,**kwargs):
        if not decode_slots.acquire(timeout=5):raise HTTPException(429,'照片处理繁忙，请稍后重试')
        try:return fn(*args,**kwargs)
        finally:decode_slots.release()
    return run

created_files = ContextVar('qc_photo_created_files', default=None)
log = logging.getLogger(__name__)
MIMES = {
    'JPEG': 'image/jpeg', 'MPO': 'image/jpeg',
    'PNG': 'image/png', 'WEBP': 'image/webp',
    'HEIF': 'image/heif', 'HEIC': 'image/heic', 'AVIF': 'image/avif',
    'TIFF': 'image/tiff', 'BMP': 'image/bmp', 'GIF': 'image/gif',
}
DISPLAY_AS_PNG = {'MPO', 'HEIF', 'HEIC', 'AVIF', 'TIFF', 'BMP'}
DISPLAY_MIME_FALLBACK = {'image/heif', 'image/heic', 'image/avif', 'image/tiff', 'image/bmp'}


def root():
    return Path(settings.qc_department_data_dir).resolve() / '_inspection_sheet' / 'photo-files'


@bounded
def inspect(content):
    if not content or len(content)>10*1024*1024:
        raise HTTPException(413,'单张照片须为 10 MB 以内的图片')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as im:
                if im.format not in MIMES:
                    raise HTTPException(422,'照片格式不支持，请选择 JPG、PNG、WebP、HEIC、HEIF、AVIF、TIFF、BMP 或 GIF')
                if im.width*im.height>40_000_000:
                    raise HTTPException(422,'单张照片最多 4000 万像素，请缩小尺寸后重试')
                # Pillow identifies some iPhone JPEGs as MPO. Its first image is
                # the primary JPEG; extra frames stay in the unmodified original.
                meta=dict(mime=MIMES[im.format],format=im.format,size=len(content),width=im.width,height=im.height,
                          sha256=sha256(content).hexdigest(),orientation=im.getexif().get(274,1))
                im.load()
        return meta
    except (Image.DecompressionBombWarning,Image.DecompressionBombError):
        raise HTTPException(422,'单张照片最多 4000 万像素，请缩小尺寸后重试') from None
    except (OSError,ValueError,EOFError,UnidentifiedImageError):
        raise HTTPException(422,'无法读取这张照片。请确认文件完整，或另存为 JPG 或 PNG 后重试') from None


def preview(content):
    raw=_preview(content)
    return raw,inspect(raw)


@bounded
def _preview(content):
    # Configuration belongs to this pipeline, not individual consumers.
    with Image.open(BytesIO(content)) as im:
        image=ImageOps.exif_transpose(im).convert('RGB')
        image.thumbnail((settings.qc_photo_preview_max_edge,)*2)
        output=BytesIO()
        for quality in range(settings.qc_photo_preview_quality,69,-5):
            output=BytesIO();image.save(output,'JPEG',quality=quality,optimize=True,exif=b'')
            if output.tell()<=settings.qc_photo_preview_target_bytes:break
        raw=output.getvalue()
    return raw


def write_file(content):
    # Unique per attempt: rollback never deletes another upload's file.
    folder=root();folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    name=uuid4().hex+'.bin';path=folder/name
    queue=created_files.get()
    try:
        with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
            if queue is not None:queue.append(path)
            stream.write(content);stream.flush();os.fsync(stream.fileno())
    except OSError:
        path.unlink(missing_ok=True)
        if queue is not None and path in queue:queue.remove(path)
        raise
    return name


def read_file(info):
    name=info.get('path','')
    if not name or Path(name).name!=name:raise HTTPException(503,'照片文件路径无效')
    path=root()/name
    if path.is_symlink():raise HTTPException(503,'照片文件路径无效')
    try:
        if path.stat().st_size>10*1024*1024:raise OSError()
        data=path.read_bytes()
    except OSError:raise HTTPException(503,'照片文件缺失或暂时不可读，请重试') from None
    if len(data)!=info['size'] or sha256(data).hexdigest()!=info['sha256']:
        raise HTTPException(503,'照片校验失败，请联系管理员恢复原文件')
    return data


def save(conn, photo_id, content, original_status='available', *, details=None):
    details=details or inspect(content)
    meta={'version':1,'original':None,'preview':None,'error':'',
          'originalStatus':original_status,'sourceSize':details['size']}
    if original_status=='available':
        meta['original']={**details,'path':write_file(content)}
    try:
        raw,details=preview(content)
        meta['preview']={**details,'path':write_file(raw)}
        status='ready'
    except Exception:
        if original_status=='preview-only':
            # There is no retained source for a background retry.
            raise HTTPException(503,'预览图生成或保存失败，照片未上传，请重试') from None
        # Retained original/legacy content survives a failed preview.
        meta['error']='预览图生成失败，后台将重试';status='failed'
        log.warning('qc_photo_preview_failed photo=%s',photo_id)
    conn.execute('INSERT INTO photo_assets(photo_id,metadata,status,retry_at) VALUES(?,?,?,?)',
                 (photo_id,json.dumps(meta),status,time.time()+30 if status=='failed' else 0))
    return meta


def metadata(conn,photo_id,schema=''):
    prefix='journal.' if schema=='journal' else ''
    tables={r[0] for r in conn.execute('SELECT name FROM '+prefix+"sqlite_master WHERE type='table'")}
    if 'photo_assets' not in tables:return None
    row=conn.execute('SELECT metadata,status FROM '+prefix+'photo_assets WHERE photo_id=?',(photo_id,)).fetchone()
    return {**json.loads(row[0]),'status':row[1]} if row else None


def public_metadata(conn,photo_id,schema=''):
    meta=metadata(conn,photo_id,schema)
    if not meta:return dict(originalAvailable=False,originalStatus='unavailable-legacy',previewStatus='legacy')
    return dict(originalAvailable=bool(meta['original']),originalStatus=meta['originalStatus'],previewStatus=meta['status'],
                original={k:v for k,v in (meta['original'] or {}).items() if k!='path'},
                preview={k:v for k,v in (meta['preview'] or {}).items() if k!='path'},previewError=meta['error'])


def read(conn,row,variant='preview'):
    if variant not in {'preview','original','original-display'}:raise HTTPException(422,'照片版本不正确')
    meta=metadata(conn,row['id'])
    if variant!='preview':
        if meta and meta['originalStatus']=='preview-only':
            raise HTTPException(409,'这张照片上传时仅保留了预览图')
        if not meta or not meta['original']:raise HTTPException(409,'此历史照片没有可确认的原图，仍可查看已有预览图')
        info=meta['original'];raw=read_file(info)
        if variant=='original-display' and (info.get('format') in DISPLAY_AS_PNG or info['mime'] in DISPLAY_MIME_FALLBACK):
            return display_png(raw),'image/png'
        return raw,info['mime']
    if meta and meta['preview']:return read_file(meta['preview']),'image/jpeg'
    if row['content']:
        # Immutable legacy fallback was already normalized by the old upload path.
        return bytes(row['content']),'image/jpeg'
    raise HTTPException(503,'预览图尚未生成成功，后台将重试；原图仍保留')


@bounded
def display_png(raw):
    with Image.open(BytesIO(raw)) as im:
        out=BytesIO();ImageOps.exif_transpose(im).convert('RGB').save(out,'PNG')
        if out.tell()>32*1024*1024:raise HTTPException(422,'全尺寸图片适配后过大，请使用预览版本')
        return out.getvalue()


def backfill_batch(limit=8):
    from app.services import qc_inspection_sheet as sheet, qc_workflow as wf
    path=Path(settings.qc_department_data_dir).resolve()/'_inspection_sheet/inspections.sqlite3'
    if not path.is_file():return 0
    done=0
    with sheet.store(True) as conn:
        rows=conn.execute('''SELECT p.*,e.factory,e.base FROM photos p JOIN entries e ON e.id=p.entry_id
          LEFT JOIN photo_assets a ON a.photo_id=p.id WHERE p.removed=0 AND
          (a.photo_id IS NULL OR (a.status='failed' AND a.retry_at<=?)) ORDER BY p.created_at,p.id LIMIT ?''',(time.time(),limit)).fetchall()
        for row in rows:
            old=metadata(conn,row['id'])
            try:
                if old:
                    raw=read_file(old['original']) if old['original'] else bytes(row['content'])
                    content,info=preview(raw);old['preview']={**info,'path':write_file(content)};old['error']=''
                    conn.execute("UPDATE photo_assets SET metadata=?,status='ready',attempts=attempts+1 WHERE photo_id=?",(json.dumps(old),row['id']))
                else:
                    raw=bytes(row['content']);original=False
                    # Only exact workflow attachment evidence can prove a historical original.
                    base=json.loads(row['base']);task=base.get('workflowId');origin=row['origin'] or ''
                    if task and origin.startswith(task+':'):
                        try:
                            candidate=wf.read_file(row['factory'],task,origin[len(task)+1:])['content']
                            if sha256(sheet.normalize_photo(candidate)).hexdigest()==row['digest']:
                                raw=candidate;original=True
                        except (HTTPException,OSError):pass
                    save(conn,row['id'],raw,'available' if original else 'unavailable-legacy')
                done+=1
            except Exception:
                if old:
                    conn.execute("UPDATE photo_assets SET attempts=attempts+1,retry_at=? WHERE photo_id=?",(time.time()+300,row['id']))
                else:
                    missing=dict(version=1,original=None,preview=None,originalStatus='unavailable-legacy',error='历史照片不可读，保留原记录等待恢复')
                    conn.execute("INSERT INTO photo_assets(photo_id,metadata,status,retry_at) VALUES(?,?,'failed',?)",(row['id'],json.dumps(missing),time.time()+300))
                log.warning('qc_photo_backfill_failed photo=%s',row['id'])
    return done


def clean_interrupted_files():
    """Only expired, unreferenced generated files; never remove retained photo evidence."""
    from app.services import qc_inspection_sheet as sheet
    if not root().exists():return
    with sheet.store(True) as conn:
        referenced=set()
        for row in conn.execute('SELECT metadata FROM photo_assets'):
            meta=json.loads(row[0])
            referenced.update(info['path'] for info in (meta.get('original'),meta.get('preview')) if info)
        for path in root().glob('*.bin'):
            if path.name not in referenced and not path.is_symlink() and path.stat().st_mtime<time.time()-86400:
                path.unlink()


async def worker():
    while True:
        try:
            await asyncio.to_thread(backfill_batch)
            await asyncio.to_thread(clean_interrupted_files)
        except asyncio.CancelledError:raise
        except Exception:log.exception('qc_photo_worker_failed')
        await asyncio.sleep(30)
