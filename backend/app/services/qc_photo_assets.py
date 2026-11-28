"""File-backed QC originals and previews. Photo IDs and approval snapshots stay stable."""
from collections import OrderedDict
from contextvars import ContextVar
from functools import wraps
from threading import BoundedSemaphore, Lock
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import asyncio
import json
import logging
import math
import os
import sqlite3
import time
import warnings
from uuid import uuid4
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
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
ANNOTATION_COORDS = ('x1', 'y1', 'x2', 'y2')
RENDER_CACHE_LIMIT = 64
RENDER_CACHE_BYTES = 16 * 1024 * 1024
_render_cache = OrderedDict()
_render_cache_bytes = 0
_render_cache_lock = Lock()


def valid_annotations(annotations):
    if not isinstance(annotations, list):
        return []
    valid = []
    for mark in annotations[:40]:
        if not isinstance(mark, dict) or mark.get('type') not in ('arrow', 'circle'):
            continue
        coords = [mark.get(key) for key in ANNOTATION_COORDS]
        if not all(type(value) in (int, float) and 0 <= value <= 1 for value in coords):
            continue
        x1, y1, x2, y2 = coords
        if (x1, y1) == (x2, y2) or (mark['type'] == 'circle' and (x1 == x2 or y1 == y2)):
            continue
        valid.append(dict(type=mark['type'], **dict(zip(ANNOTATION_COORDS, map(float, coords)))))
    return valid


def decode_annotations(value):
    try:
        return valid_annotations(json.loads(value)) if value else []
    except (ValueError, TypeError, RecursionError):
        return []


def has_annotation_table(conn):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='photo_annotations'"
    ).fetchone() is not None


def entry_photos_sql(conn):
    if has_annotation_table(conn):
        return """SELECT p.*, m.annotations FROM photos p
            LEFT JOIN photo_annotations m ON m.photo_id=p.id
            WHERE p.entry_id=? AND p.removed=0 ORDER BY p.created_at,p.id"""
    return """SELECT *, NULL AS annotations FROM photos
        WHERE entry_id=? AND removed=0 ORDER BY created_at,id"""


def render_annotated(content, annotations, *, mime, quality):
    """Render a derivative only; the caller has already checked access and revision."""
    marks = valid_annotations(annotations)
    if not marks:
        return content, mime
    key = (sha256(content).digest(), json.dumps(marks, sort_keys=True, separators=(',', ':')), quality)
    with _render_cache_lock:
        if key in _render_cache:
            _render_cache.move_to_end(key)
            return _render_cache[key]
    return _render_cached(key, content, marks, quality)


@bounded
def _render_cached(key, content, marks, quality):
    global _render_cache_bytes
    # A different request may have populated the entry while we waited for a slot.
    with _render_cache_lock:
        if key in _render_cache:
            _render_cache.move_to_end(key)
            return _render_cache[key]
    try:
        with Image.open(BytesIO(content)) as original:
            if original.width * original.height > 40_000_000:
                raise HTTPException(422, '单张照片最多 4000 万像素，请缩小尺寸后重试')
            source_format = original.format
            ImageOps.exif_transpose(original, in_place=True)
            base = original.convert('RGBA')
        with base, _annotation_overlay(base.size, marks) as overlay:
            with Image.alpha_composite(base, overlay) as composed:
                image = composed.convert('RGB')
        with image:
            result = _encode_annotated(image, source_format, quality)
    except (OSError, ValueError, EOFError, Image.DecompressionBombError):
        raise HTTPException(422, '无法读取照片以合成标注') from None
    size = len(result[0])
    if size <= RENDER_CACHE_BYTES:
        with _render_cache_lock:
            previous = _render_cache.pop(key, None)
            if previous is not None:
                _render_cache_bytes -= len(previous[0])
            _render_cache[key] = result
            _render_cache_bytes += size
            while len(_render_cache) > RENDER_CACHE_LIMIT or _render_cache_bytes > RENDER_CACHE_BYTES:
                _, (evicted, _) = _render_cache.popitem(last=False)
                _render_cache_bytes -= len(evicted)
    return result


def _annotation_overlay(size, marks):
    width, height = size
    scale = 2 if max(size) <= 2400 else 1
    stroke = max(2.0, min(size) * .006) * scale
    overlay = Image.new('RGBA', (width * scale, height * scale))
    draw = ImageDraw.Draw(overlay)
    # Match qc-photo-shapes.js: normalization, centered strokes and round arrow ends.
    for thickness, color in ((stroke + max(2 * scale, stroke * .35), (40, 7, 6, 180)),
                             (stroke, (248, 59, 56, 255))):
        line_width = max(1, round(thickness))
        half = line_width / 2
        for mark in marks:
            x1, x2 = (mark[key] * width * scale for key in ('x1', 'x2'))
            y1, y2 = (mark[key] * height * scale for key in ('y1', 'y2'))
            if mark['type'] == 'circle':
                draw.ellipse((min(x1, x2) - half, min(y1, y2) - half,
                              max(x1, x2) + half, max(y1, y2) + half),
                             outline=color, width=line_width)
                continue
            angle = math.atan2(y2 - y1, x2 - x1)
            head = min(stroke * 5.5, math.hypot(x2 - x1, y2 - y1) * .5)
            start, tip = (x1, y1), (x2, y2)
            wings = [(x2 - head * math.cos(angle + offset), y2 - head * math.sin(angle + offset))
                     for offset in (.65, -.65)]
            for endpoint in (start, *wings):
                draw.line((endpoint, tip), fill=color, width=line_width)
            for x, y in (start, tip, *wings):
                draw.ellipse((x - half, y - half, x + half, y + half), fill=color)
    return overlay.resize(size, Image.Resampling.LANCZOS) if scale > 1 else overlay


def _encode_annotated(image, source_format, quality):
    if quality == 'original' and source_format in DISPLAY_AS_PNG | {'PNG'}:
        output = BytesIO()
        image.save(output, 'PNG', optimize=True)
        if output.tell() <= 32 * 1024 * 1024:
            return output.getvalue(), 'image/png'
    qualities = (settings.qc_photo_preview_quality,) if quality == 'preview' else (92,)
    if quality == 'preview' and settings.qc_photo_preview_quality >= 70:
        qualities = range(settings.qc_photo_preview_quality, 69, -5)
    for jpeg_quality in qualities:
        output = BytesIO()
        image.save(output, 'JPEG', quality=jpeg_quality, subsampling=0, optimize=True, exif=b'')
        if quality != 'preview' or output.tell() <= settings.qc_photo_preview_target_bytes:
            break
    return output.getvalue(), 'image/jpeg'


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
