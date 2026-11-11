"""Original/preview persistence, transaction failures, legacy recovery and export evidence."""
import base64,json,sqlite3,zipfile
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import pytest
from PIL import Image, ImageOps
from fastapi import HTTPException
from app.services import qc_photo_assets as assets, qc_inspection_sheet as sheet
from app.services import qc_monthly_templates as monthly, qc_monthly_excel as excel
from test_qc_inspection_sheet import source,pushed_candidates,isolated
from test_qc_workflow import ACTOR
from test_customer_order_ledger import engine,db
from test_qc_monthly_templates import issue,DAY


def image(fmt='JPEG',orientation=1,size=(2400,1600)):
    im=Image.effect_noise(size,25).convert('RGB');out=BytesIO();exif=Image.Exif();exif[274]=orientation;exif[270]='private metadata'
    im.save(out,fmt,exif=exif);return out.getvalue()


def entry(n='one'):
    return next(e for e in sheet.sync('huaxing',pushed_candidates([source(n)]))['items'] if e['sourceId']==n)


def upload(e,raw,key=None):
    return sheet.add_photo('huaxing',e['id'],dict(revision=e['revision'],name='验货照片',content=base64.b64encode(raw).decode(),requestKey=key or uuid4().hex),ACTOR)


@pytest.mark.parametrize('fmt',['JPEG','PNG','WEBP','HEIF'])
def test_original_exact_preview_metadata_orientation(fmt):
    if fmt=='HEIF':
        from pillow_heif import register_heif_opener
        register_heif_opener()
    raw=image(fmt,6);e=upload(entry(),raw);p=e['photos'][0]['id']
    original,mime=sheet.read_photo_version('huaxing',e['id'],p,'original');assert original==raw and mime==assets.inspect(raw)['mime']
    preview=sheet.read_photo('huaxing',e['id'],p)
    with Image.open(BytesIO(preview)) as im:
        assert max(im.size)<=1920 and not im.getexif()
        with Image.open(BytesIO(raw)) as source:
            oriented=ImageOps.exif_transpose(source);assert abs(im.width/im.height-oriented.width/oriented.height)<.01
    assert len(preview)<len(raw)
    with sheet.store() as conn:
        m=assets.metadata(conn,p);assert m['original']['sha256']==sha256(raw).hexdigest()
        assert conn.execute('SELECT length(content) FROM photos WHERE id=?',(p,)).fetchone()[0]==0
    assert len(e['photos'][0])==2  # File metadata never contaminates approved/revision payloads.


def test_duplicate_retry_revision_and_factory_boundaries():
    e=entry();raw=image(size=(300,200));key=uuid4().hex;got=upload(e,raw,key)
    assert upload(e,raw,key)==got
    with pytest.raises(HTTPException) as exc:upload(e,image('PNG',size=(100,200)),key)
    assert exc.value.status_code==409
    with pytest.raises(HTTPException):sheet.read_photo_version('huadeng',got['id'],got['photos'][0]['id'],'original')
    other=entry('two')
    with pytest.raises(HTTPException):sheet.read_photo_version('huaxing',other['id'],got['photos'][0]['id'],'original')
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:upload(e,raw,key),range(2)))
    assert all(r==got for r in results)


def test_malformed_oversize_and_decode_limits():
    for raw in (b'<svg onload=bad()>',b'\xff\xd8broken',b'x'*(10*1024*1024+1)):
        with pytest.raises(HTTPException):assets.inspect(raw)
    out=BytesIO();Image.new('1',(6500,6500)).save(out,'PNG')
    with pytest.raises(HTTPException):assets.inspect(out.getvalue())


def test_preview_failure_retains_original_and_recovers_without_revision(monkeypatch):
    raw=image(size=(400,300));e=entry();real=assets.preview
    monkeypatch.setattr(assets,'preview',lambda _:(_ for _ in ()).throw(OSError('simulated')))
    e=upload(e,raw);p=e['photos'][0]['id']
    assert sheet.read_photo_version('huaxing',e['id'],p,'original')[0]==raw
    with pytest.raises(HTTPException):sheet.read_photo('huaxing',e['id'],p)
    monkeypatch.setattr(assets,'preview',real)
    with sheet.store(True) as conn:conn.execute('UPDATE photo_assets SET retry_at=0')
    assert assets.backfill_batch()==1
    assert sheet.read_photo('huaxing',e['id'],p)
    with sheet.store() as conn:assert sheet.unpack(conn,sheet.get(conn,'huaxing',e['id']))==e


def test_original_failure_and_transaction_failure_leave_no_orphan(monkeypatch):
    e=entry();raw=image(size=(100,100));real=assets.write_file
    monkeypatch.setattr(assets,'write_file',lambda _:(_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(HTTPException):upload(e,raw)
    monkeypatch.setattr(assets,'write_file',real)
    monkeypatch.setattr(sheet,'changed',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('rollback')))
    with pytest.raises(RuntimeError):upload(e,raw)
    assert not list(assets.root().glob('*'))
    with sheet.store() as conn:assert conn.execute('SELECT count(*) FROM photos').fetchone()[0]==0


def test_legacy_blob_idempotent_migration_no_fabricated_original():
    e=entry();raw=sheet.normalize_photo(image(size=(500,300)));pid=uuid4().hex
    with sheet.store(True) as conn:
        conn.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,0,?)',(pid,e['id'],'旧照片',raw,sha256(raw).hexdigest(),'legacy','2020'))
    assert assets.backfill_batch()==1;assert assets.backfill_batch()==0
    assert sheet.read_photo('huaxing',e['id'],pid)
    with pytest.raises(HTTPException) as exc:sheet.read_photo_version('huaxing',e['id'],pid,'original')
    assert exc.value.status_code==409
    with sheet.store() as conn:
        assert conn.execute('SELECT content FROM photos WHERE id=?',(pid,)).fetchone()[0]==raw
        assert sheet.get(conn,'huaxing',e['id'])['revision']==e['revision']


def test_removed_photo_and_missing_file_are_not_readable():
    e=upload(entry(),image(size=(100,80)));p=e['photos'][0]['id']
    with sheet.store() as conn:m=assets.metadata(conn,p)
    (assets.root()/m['original']['path']).unlink()
    with pytest.raises(HTTPException) as exc:sheet.read_photo_version('huaxing',e['id'],p,'original')
    assert exc.value.status_code==503
    sheet.remove_photo('huaxing',e['id'],{'revision':e['revision'],'photoId':p},ACTOR)
    with pytest.raises(HTTPException):sheet.read_photo('huaxing',e['id'],p)


def test_excel_embeds_selected_bytes_and_preserves_cells_and_anchors(db):
    e=issue(db,1,photos=2);data=monthly.query('huaxing',DAY)
    def parts(quality):
        raw=excel.render(data,'issues','huaxing',quality)
        with zipfile.ZipFile(BytesIO(raw)) as z:return {n:z.read(n) for n in z.namelist()}
    preview=parts('preview');original=parts('original')
    for n in preview:
        if n.startswith('xl/worksheets/') or n=='xl/styles.xml' or n=='xl/drawings/drawing1.xml':assert preview[n]==original[n]
    for i,p in enumerate(e['photos'],1):
        assert original[f'xl/media/image{i}.png']==sheet.read_photo_version('huaxing',e['id'],p['id'],'original')[0]
        assert preview[f'xl/media/image{i}.jpeg']==sheet.read_photo('huaxing',e['id'],p['id'])
    payload=dict(date=DAY,customer='',template='issues',sourceRevision=data['sourceRevision'],versions=excel.versions(data))
    assert excel.photo_options('huaxing',payload)['missingOriginals']==0
    # Simulate a retained historical normalized blob, with no claim of original existence.
    p=e['photos'][0]['id'];old=sheet.read_photo('huaxing',e['id'],p)
    with sheet.store(True) as conn:
        conn.execute('DELETE FROM photo_assets WHERE photo_id=?',(p,));conn.execute('UPDATE photos SET content=? WHERE id=?',(old,p))
    assert excel.photo_options('huaxing',payload)['missingOriginals']==1
    with pytest.raises(HTTPException):excel.render(data,'issues','huaxing','original')
    assert excel.render(data,'issues','huaxing','original',True)
    payload['sourceRevision']='stale'
    with pytest.raises(HTTPException):excel.photo_options('huaxing',payload)


def test_original_and_preview_sizes_do_not_shift_excel_anchors(db,monkeypatch):
    issue(db,1,photos=1);data=monthly.query('huaxing',DAY)
    raw=image(size=(3000,2000));small=assets.preview(raw)[0]
    monkeypatch.setattr(excel,'_photo',lambda factory,entry,photo,quality,fallback:raw if quality=='original' else small)
    def drawing(quality):
        with zipfile.ZipFile(BytesIO(excel.render(data,'issues','huaxing',quality))) as book:
            return book.read('xl/drawings/drawing1.xml')
    assert drawing('preview')==drawing('original')


def test_excel_missing_original_file_fails_then_recovers(db):
    e=issue(db,1,photos=1);data=monthly.query('huaxing',DAY)
    with sheet.store() as conn:meta=assets.metadata(conn,e['photos'][0]['id'])
    path=assets.root()/meta['original']['path'];raw=path.read_bytes();path.unlink()
    with pytest.raises(HTTPException) as exc:excel.render(data,'issues','huaxing','original',True)
    assert exc.value.status_code==503  # Consent covers legacy absence, never a corrupted/lost real original.
    path.write_bytes(raw)
    assert excel.render(data,'issues','huaxing','original').startswith(b'PK')
    payload=dict(date=DAY,customer='',template='issues',sourceRevision=data['sourceRevision'],versions=excel.versions(data),photoQuality=[])
    with pytest.raises(HTTPException) as exc:excel.photo_options('huaxing',payload)
    assert exc.value.status_code==422
