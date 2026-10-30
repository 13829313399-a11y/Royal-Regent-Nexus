"""Imported photo copies are optimized without changing their workbook or identity."""
import base64
import hashlib
from io import BytesIO
import random
from zipfile import ZipFile

from PIL import Image
import pytest

from app.services.indonesia_master_images import prepare_photo, fits_image, IMAGE_LIMIT, DATA_URL_LIMIT
from app.services.indonesia_master_import import parse_material_book
from app.services.indonesia_material_excel import validate_image
from test_indonesia_master_template import rewrite, template_book, ET, S


def image_bytes(picture, format='PNG', **options):
    stream = BytesIO(); picture.save(stream, format, **options)
    return stream.getvalue()


def oversized(content):
    # Valid photo with oversized metadata/trailing content; no huge test allocation.
    return content + b' ' * max(0, IMAGE_LIMIT + 1 - len(content))


def decoded(data):
    return base64.b64decode(data.split(',', 1)[1])


@pytest.mark.parametrize('format', ['PNG', 'JPEG'])
def test_small_photos_keep_exact_original_bytes(format):
    original = image_bytes(Image.new('RGB', (80, 40), 'red'), format)
    data, evidence = prepare_photo(original)
    assert decoded(data) == original
    assert evidence['compressed'] is False
    assert validate_image(data)[2:] == (80, 40)


def test_real_pixel_payload_is_compressed_with_valid_output():
    original = image_bytes(Image.frombytes('RGB', (1000, 700), random.Random(7).randbytes(1000 * 700 * 3)))
    assert len(original) > IMAGE_LIMIT
    data, evidence = prepare_photo(original)
    assert evidence['source_bytes'] == len(original)
    assert evidence['compressed'] and evidence['stored_bytes'] < IMAGE_LIMIT
    assert len(data) <= DATA_URL_LIMIT
    assert validate_image(data)[2:] == (1000, 700)


@pytest.mark.parametrize('mode', ['RGBA', 'LA', 'P', 'RGB'])
def test_transparency_survives_compression_including_palette_zero(mode):
    if mode == 'RGBA':
        photo = Image.new(mode, (90, 60), (240, 0, 0, 0)); photo.putpixel((40, 30), (0, 180, 0, 255))
    elif mode == 'LA':
        photo = Image.new(mode, (90, 60), (240, 0)); photo.putpixel((40, 30), (180, 255))
    elif mode == 'P':
        photo = Image.new(mode, (90, 60), 0); photo.putpalette([240, 0, 0, 0, 180, 0] + [0] * 762)
        photo.info['transparency'] = 0; photo.putpixel((40, 30), 1)
    else:
        photo = Image.new(mode, (90, 60), (240, 0, 0)); photo.info['transparency'] = (240, 0, 0)
        photo.putpixel((40, 30), (0, 180, 0))
    data, info = prepare_photo(oversized(image_bytes(photo)))
    assert data.startswith('data:image/png;base64,') and info['compressed']
    with Image.open(BytesIO(decoded(data))) as result:
        result = result.convert('RGBA')
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((40, 30))[3] == 255


def test_resize_is_proportional_and_exif_orientation_is_applied_once():
    photo = Image.new('RGB', (2400, 1200), 'red')
    photo.paste('blue', (1200, 0, 2400, 1200))
    exif = Image.Exif(); exif[274] = 6
    data, info = prepare_photo(oversized(image_bytes(photo, 'JPEG', exif=exif)))
    assert info['source_dimensions'] == [2400, 1200]
    assert info['dimensions'] == [1024, 2048]
    with Image.open(BytesIO(decoded(data))) as result:
        assert result.getexif().get(274, 1) == 1
        assert result.getpixel((512, 200))[0] > 200
        assert result.getpixel((512, 1800))[2] > 200


def test_cmyk_compresses_to_compatible_rgb_jpeg():
    data, _ = prepare_photo(oversized(image_bytes(Image.new('CMYK', (80, 40), (0, 255, 255, 0)), 'JPEG')))
    with Image.open(BytesIO(decoded(data))) as result:
        assert result.mode == 'RGB' and result.format == 'JPEG'
        assert result.getpixel((20, 20))[0] > 200


@pytest.mark.parametrize('transparent', [False, True])
def test_16_bit_greyscale_preserves_midtones_and_transparency(transparent):
    pixels = b''.join((x * 257).to_bytes(2, 'little') for _ in range(8) for x in range(256))
    photo = Image.frombytes('I;16', (256, 8), pixels)
    options = {'transparency': 0} if transparent else {}
    data, _ = prepare_photo(oversized(image_bytes(photo, **options)))
    with Image.open(BytesIO(decoded(data))) as result:
        assert abs(result.getpixel((128, 4))[0] - 128) <= 2
        assert result.getpixel((255, 4))[0] >= 253
        if transparent:
            assert result.mode == 'RGBA' and result.getpixel((0, 4))[3] == 0
            assert result.getpixel((128, 4))[3] == 255


def test_data_url_limit_includes_base64_prefix():
    source = image_bytes(Image.new('RGB', (12, 12), 'green'))
    source += b' ' * (IMAGE_LIMIT - len(source))
    assert not fits_image(source, 'PNG')
    data, info = prepare_photo(source)
    assert info['compressed'] and len(data) <= DATA_URL_LIMIT


def test_source_limits_invalid_images_and_animation_are_not_silently_flattened(monkeypatch):
    from app.services import indonesia_master_images as images
    with pytest.raises((ValueError, OSError)):
        prepare_photo(b'not an image')
    original = image_bytes(Image.new('RGB', (100, 100), 'red'))
    monkeypatch.setattr(images, 'PIXEL_LIMIT', 100)
    with pytest.raises(ValueError, match='dimensions'):
        prepare_photo(original)
    monkeypatch.setattr(images, 'PIXEL_LIMIT', 16_000_000)
    first, second = Image.new('RGBA', (16, 16), 'red'), Image.new('RGBA', (16, 16), 'blue')
    animated = image_bytes(first, save_all=True, append_images=[second], duration=100)
    with pytest.raises(ValueError, match='animated'):
        prepare_photo(animated)
    monkeypatch.setattr(images, 'SOURCE_IMAGE_LIMIT', len(original)-1)
    with pytest.raises(ValueError, match='processing limit'):
        prepare_photo(original)


def test_corrupted_jpeg_scan_is_rejected_even_with_valid_header():
    original = image_bytes(Image.new('RGB', (100, 100), 'red'), 'JPEG')
    with pytest.raises(OSError):
        prepare_photo(original[:-20])


@pytest.mark.parametrize('wps', [False, True])
def test_both_excel_image_sources_compress_without_changing_original_workbook(wps):
    def change(parts):
        parts['xl/media/image1.png'] = oversized(parts['xl/media/image1.png'])
        if wps:
            root = ET.fromstring(parts['xl/worksheets/sheet1.xml'])
            for drawing in root.findall(S+'drawing'):
                root.remove(drawing)
            row = next(row for row in root.findall('.//'+S+'row') if row.get('r') == '4')
            cell = ET.SubElement(row, S+'c', r='T4'); ET.SubElement(cell, S+'f').text = '_xlfn.DISPIMG("PHOTO",1)'
            parts['xl/worksheets/sheet1.xml'] = ET.tostring(root)
            parts['xl/cellimages.xml'] = b'<cellImages xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><xdr:pic><xdr:nvPicPr><xdr:cNvPr name="PHOTO"/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="photo"/></xdr:blipFill></xdr:pic></cellImages>'
            parts['xl/_rels/cellimages.xml.rels'] = b'<Relationships><Relationship Id="photo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/></Relationships>'
    content = rewrite(template_book(), change)
    before = hashlib.sha256(content).hexdigest()
    row = next(row for row in parse_material_book(content, '照片.xlsx', product_codes=['40149'])['rows'] if row['source_row'] == 4)
    assert row['evidence']['image_data']['compressed']
    assert any('已自动压缩' in note for note in row['notes']) and not row['warnings']
    validate_image(row['source']['image_data'])
    assert hashlib.sha256(content).hexdigest() == before
    with ZipFile(BytesIO(content)) as archive:
        assert len(archive.read('xl/media/image1.png')) > IMAGE_LIMIT


def test_repeated_photo_is_charged_per_row(monkeypatch):
    from app.services import indonesia_master_workbook as reader
    source = template_book()
    def same_picture(parts):
        root = ET.fromstring(parts['xl/drawings/_rels/drawing1.xml.rels'])
        for item in root:
            item.set('Target', root[0].get('Target'))
        parts['xl/drawings/_rels/drawing1.xml.rels'] = ET.tostring(root)
    with ZipFile(BytesIO(source)) as archive:
        data, _ = prepare_photo(archive.read('xl/media/image1.png'))
    monkeypatch.setattr(reader, 'IMAGE_TOTAL_LIMIT', len(data) * 2)
    parsed = parse_material_book(rewrite(source, same_picture), '同图多行.xlsx', product_codes=['40149'])
    rows = [row for row in parsed['rows'] if row['source_row'] in (4, 5, 6, 7)]
    assert sum('image_data' in row['source'] for row in rows) == 2
    assert all(row['warnings'] for row in rows[2:])
