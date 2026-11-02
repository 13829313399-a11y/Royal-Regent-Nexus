"""Bounded optimization of imported photos; never write to the source workbook."""
import base64
from io import BytesIO
import warnings

from PIL import Image, ImageOps

SOURCE_IMAGE_LIMIT = 32 * 1024 * 1024
IMAGE_LIMIT = 1_500_000
PIXEL_LIMIT = 16_000_000
DATA_URL_LIMIT = 2_000_000


def fits_image(content, image_format):
    prefix = f'data:image/{"png" if image_format == "PNG" else "jpeg"};base64,'
    return len(content) <= IMAGE_LIMIT and len(prefix) + 4 * ((len(content) + 2) // 3) <= DATA_URL_LIMIT


def pixel_copy(original, transparent):
    mode = 'RGBA' if transparent else 'RGB'
    if original.mode != 'I' and not original.mode.startswith('I;16'):
        return original.convert(mode)
    # PNG's 16-bit greyscale samples need scaling; convert('RGB') clips at 255.
    with original.convert('I') as integer:
        with integer.point([round(value / 257) for value in range(65536)], 'L') as grey:
            picture = grey.convert(mode)
        if transparent:
            key = original.info.get('transparency')
            with integer.point([0 if value == key else 255 for value in range(65536)], 'L') as alpha:
                picture.putalpha(alpha)
    return picture


def prepare_photo(content):
    if not content or len(content) > SOURCE_IMAGE_LIMIT:
        raise ValueError('source image exceeds processing limit')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as original:
            image_format, dimensions = original.format, original.size
            if image_format not in {'PNG', 'JPEG'} or original.width * original.height > PIXEL_LIMIT:
                raise ValueError('unsupported format or dimensions')
            if getattr(original, 'n_frames', 1) != 1:
                raise ValueError('animated images cannot be flattened')
            original.verify()
        compressed = not fits_image(content, image_format)
        stored, output_format, output_dimensions = content, image_format, dimensions
        with Image.open(BytesIO(content)) as original:
            original.load()  # Also reject truncated small JPEGs; verify() alone is insufficient.
            if compressed:
                with ImageOps.exif_transpose(original) as oriented:
                    transparent = 'A' in oriented.getbands() or 'transparency' in oriented.info
                    with pixel_copy(oriented, transparent) as picture:
                        picture.info.clear()  # Keep pixels/alpha, not bulky EXIF or text metadata.
                        picture.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                        output_format = 'PNG' if transparent else 'JPEG'
                        while True:
                            for quality in ([None] if transparent else [90, 82, 74]):
                                output = BytesIO()
                                options = dict(compress_level=6) if transparent else dict(quality=quality, optimize=True)
                                picture.save(output, format=output_format, **options)
                                stored = output.getvalue()
                                if fits_image(stored, output_format):
                                    break
                            if fits_image(stored, output_format):
                                output_dimensions = picture.size
                                break
                            edge = max(picture.size)
                            if edge <= 512:
                                raise ValueError('image cannot fit output limits')
                            next_edge = max(512, int(edge * .75))
                            picture.thumbnail((next_edge, next_edge), Image.Resampling.LANCZOS)
    mime = 'png' if output_format == 'PNG' else 'jpeg'
    data = f'data:image/{mime};base64,' + base64.b64encode(stored).decode('ascii')
    if len(data) > DATA_URL_LIMIT or output_dimensions[0] * output_dimensions[1] > PIXEL_LIMIT:
        raise ValueError('invalid optimized image')
    evidence = dict(compressed=compressed, source_bytes=len(content), stored_bytes=len(stored),
                    source_dimensions=list(dimensions), dimensions=list(output_dimensions),
                    source_format=image_format, format=output_format)
    return data, evidence
