"""Original/preview persistence, transaction failures, legacy recovery and export evidence."""
import base64,json,sqlite3,zipfile
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
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
    body=dict(revision=e['revision'],name='验货照片',content=base64.b64encode(raw).decode(),requestKey=key or uuid4().hex)
    return sheet.add_photo('huaxing',e['id'],body,ACTOR)


def upload_retained(e,raw):
    # Simulate the previous storage policy to verify existing original files.
    save=assets.save
    with patch.object(assets,'save',side_effect=lambda conn,pid,content,status,**kwargs:
            save(conn,pid,content,'available',**kwargs)):
        return upload(e,raw)


@pytest.mark.parametrize('fmt',['JPEG','PNG','WEBP','HEIF'])
def test_new_upload_preview_metadata_orientation(fmt):
    if fmt=='HEIF':
        from pillow_heif import register_heif_opener
        register_heif_opener()
    raw=image(fmt,6);e=upload(entry(),raw);p=e['photos'][0]['id']
    preview=sheet.read_photo('huaxing',e['id'],p)
    with Image.open(BytesIO(preview)) as im:
        assert max(im.size)<=1920 and not im.getexif()
        with Image.open(BytesIO(raw)) as source:
            oriented=ImageOps.exif_transpose(source);assert abs(im.width/im.height-oriented.width/oriented.height)<.01
    assert len(preview)<len(raw)
    with sheet.store() as conn:
        m=assets.metadata(conn,p);assert m['original'] is None
        assert conn.execute('SELECT length(content) FROM photos WHERE id=?',(p,)).fetchone()[0]==0
    assert len(e['photos'][0])==2  # File metadata never contaminates approved/revision payloads.


@pytest.mark.parametrize('fmt,mime',[
    ('MPO','image/jpeg'),('AVIF','image/avif'),('TIFF','image/tiff'),
    ('BMP','image/bmp'),('GIF','image/gif'),
])
def test_extended_formats_with_legacy_original_and_browser_readable_versions(fmt,mime):
    primary = Image.new('RGB',(320,240),'red')
    out = BytesIO()
    if fmt=='MPO':
        exif=Image.Exif()
        exif[274]=6
        primary.save(out,fmt,save_all=True,append_images=[Image.new('RGB',primary.size,'blue')],exif=exif)
    else:
        primary.save(out,fmt)
    raw=out.getvalue()
    saved=upload_retained(entry(),raw)
    photo=saved['photos'][0]
    assert sheet.photo_info('huaxing',saved['id']) == {'items':[{**photo,'originalAvailable':True}]}
    assert sheet.read_photo_version('huaxing',saved['id'],photo['id'],'original') == (raw,mime)
    preview,preview_mime=sheet.read_photo_version('huaxing',saved['id'],photo['id'])
    assert preview_mime=='image/jpeg'
    display,display_mime=sheet.read_photo_version('huaxing',saved['id'],photo['id'],'original-display')
    if fmt=='GIF':
        assert (display,display_mime)==(raw,mime)
    else:
        assert display_mime=='image/png'
    with Image.open(BytesIO(preview)) as preview_image, Image.open(BytesIO(display)) as displayed:
        assert preview_image.size==displayed.size==((240,320) if fmt=='MPO' else (320,240))
        r,g,b=preview_image.convert('RGB').getpixel((0,0))
        assert r>200 and g<30 and b<30
    with pytest.raises(HTTPException) as error:
        sheet.photo_info('huadeng',saved['id'])
    assert error.value.status_code==404


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


def test_photo_annotations_keep_original_and_follow_review_lock():
    current = entry()
    current = sheet.save('huaxing',current['id'],dict(revision=current['revision'],result='PASS',remark=''),ACTOR)
    current = upload(current,image(size=(300,200)))
    entry_id, photo_id = current['id'], current['photos'][0]['id']
    original = sheet.read_photo('huaxing',entry_id,photo_id)
    arrow = dict(type='arrow',x1=.1,y1=.2,x2=.8,y2=.6)
    circle = dict(type='circle',x1=.2,y1=.3,x2=.4,y2=.7)

    def save(marks, version=0, factory='huaxing', target=entry_id, review=False):
        return sheet.save_photo_annotations(factory,target,dict(photoId=photo_id,annotationVersion=version,annotations=marks),ACTOR,review)

    for bad in ({**arrow,'x2':float('nan')},{**arrow,'x2':True},{**circle,'x2':.2},{**arrow,'type':'text'}):
        with pytest.raises(HTTPException) as error:
            save([bad])
        assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        save([arrow],factory='huadeng')
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        save([arrow],target=entry('two')['id'])
    assert error.value.status_code == 404

    marked = save([arrow])
    assert save([arrow]) == marked
    assert marked['entry']['revision'] == current['revision']+1
    assert sheet.read_photo('huaxing',entry_id,photo_id) == original
    assert sheet.photo_info('huaxing',entry_id)['items'][0]['annotations'] == [arrow]
    assert sheet.audit('huaxing',entry_id)['items'][0]['changes']['photoMarks'] == {'before':0,'after':1}
    with pytest.raises(HTTPException) as error:
        save([circle])
    assert error.value.status_code == 409

    pending = sheet.submit('huaxing',entry_id,dict(revision=marked['entry']['revision']),ACTOR)
    with pytest.raises(HTTPException) as error:
        save([circle],version=1)
    assert error.value.status_code == 409
    reviewed = save([arrow,circle],version=1,review=True)
    stale = sheet.review_batch('huaxing','confirm',dict(entries=[dict(id=entry_id,revision=pending['revision'])],requestKey=uuid4().hex),ACTOR)
    assert stale['succeeded'] == 0
    approval = sheet.review_batch('huaxing','confirm',dict(entries=[dict(id=entry_id,revision=reviewed['entry']['revision'])],requestKey=uuid4().hex),ACTOR)
    assert approval['succeeded'] == 1
    with sheet.store() as conn:
        snapshot = json.loads(conn.execute('SELECT approved_snapshot FROM entry_details WHERE entry_id=?',(entry_id,)).fetchone()[0])
    assert snapshot['photos'][0]['annotations'] == [arrow,circle]
    from app.services import qc_dossier_read, qc_inspection_summary
    with qc_inspection_summary.store() as conn:
        summary_id = conn.execute('SELECT id FROM records WHERE factory=? AND source_key=?',('huaxing','entry:'+entry_id)).fetchone()[0]
    dossier = qc_dossier_read.detail('huaxing',summary_id)
    assert dossier['qc']['photos'][0]['annotations'] == [arrow,circle]
    assert next(event for event in dossier['changes'] if event['action']=='photo-annotations')['changes']['photoMarks'] == {'before':1,'after':2}
    with pytest.raises(HTTPException) as error:
        save([],version=2,review=True)
    assert error.value.status_code == 409


def test_preview_only_upload_retries_without_leaving_original_or_broken_photo(monkeypatch):
    e=entry();raw=image(size=(400,300));key=uuid4().hex
    with monkeypatch.context() as patch:
        patch.setattr(assets,'preview',lambda _:(_ for _ in ()).throw(OSError('simulated')))
        with pytest.raises(HTTPException,match='照片未上传'):
            upload(e,raw,key)
        assert not list(assets.root().glob('*'))
    saved=upload(e,raw,key)
    assert upload(e,raw,key)==saved
    p=saved['photos'][0]['id']
    assert sheet.read_photo('huaxing',e['id'],p)
    assert len(list(assets.root().glob('*.bin')))==1
    with sheet.store() as conn:
        meta=assets.metadata(conn,p)
        assert meta['originalStatus']=='preview-only' and meta['original'] is None
        assert meta['sourceSize']==len(raw)
        assert conn.execute('SELECT length(content) FROM photos WHERE id=?',(p,)).fetchone()[0]==0
    with pytest.raises(HTTPException,match='仅保留了预览图'):
        sheet.read_photo_version('huaxing',e['id'],p,'original')
    assert sheet.photo_info('huaxing',e['id'])['items'][0]['originalAvailable'] is False


def test_malformed_oversize_and_decode_limits():
    for raw in (b'<svg onload=bad()>',b'\xff\xd8broken',b'x'*(10*1024*1024+1)):
        with pytest.raises(HTTPException):assets.inspect(raw)
    out=BytesIO();Image.new('1',(6500,6500)).save(out,'PNG')
    with pytest.raises(HTTPException):assets.inspect(out.getvalue())


def test_preview_failure_retains_original_and_recovers_without_revision(monkeypatch):
    raw=image(size=(400,300));e=entry();real=assets.preview
    monkeypatch.setattr(assets,'preview',lambda _:(_ for _ in ()).throw(OSError('simulated')))
    e=upload_retained(e,raw);p=e['photos'][0]['id']
    assert sheet.read_photo_version('huaxing',e['id'],p,'original')[0]==raw
    with pytest.raises(HTTPException):sheet.read_photo('huaxing',e['id'],p)
    monkeypatch.setattr(assets,'preview',real)
    with sheet.store(True) as conn:conn.execute('UPDATE photo_assets SET retry_at=0')
    assert assets.backfill_batch()==1
    assert sheet.read_photo('huaxing',e['id'],p)
    with sheet.store() as conn:assert sheet.unpack(conn,sheet.get(conn,'huaxing',e['id']))==e


def test_preview_write_and_transaction_failure_leave_no_orphan(monkeypatch):
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
    e=upload_retained(entry(),image(size=(100,80)));p=e['photos'][0]['id']
    with sheet.store() as conn:m=assets.metadata(conn,p)
    (assets.root()/m['original']['path']).unlink()
    with pytest.raises(HTTPException) as exc:sheet.read_photo_version('huaxing',e['id'],p,'original')
    assert exc.value.status_code==503
    sheet.remove_photo('huaxing',e['id'],{'revision':e['revision'],'photoId':p},ACTOR)
    with pytest.raises(HTTPException):sheet.read_photo('huaxing',e['id'],p)


def test_excel_embeds_stored_previews_including_a_legacy_photo(db):
    e=issue(db,1,photos=2);data=monthly.query('huaxing',DAY)
    first=e['photos'][0]['id'];old=sheet.read_photo('huaxing',e['id'],first)
    with sheet.store(True) as conn:
        conn.execute('DELETE FROM photo_assets WHERE photo_id=?',(first,))
        conn.execute('UPDATE photos SET content=? WHERE id=?',(old,first))
    with zipfile.ZipFile(BytesIO(excel.render(data,'issues','huaxing'))) as book:
        assert book.testzip() is None
        for i,p in enumerate(e['photos'],1):
            assert book.read(f'xl/media/image{i}.jpeg')==sheet.read_photo('huaxing',e['id'],p['id'])
