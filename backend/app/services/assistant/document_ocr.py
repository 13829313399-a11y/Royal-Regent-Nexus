"""Local OCR in the disposable parser only; no model download or remote OCR."""
import base64
import hashlib
from importlib.util import find_spec
from importlib.metadata import version
from io import BytesIO
import math
import os
from pathlib import Path

MAX_IMAGE_PIXELS = 10_000_000
MAX_OCR_PAGES = 20
MAX_PREVIEW_BYTES = 20 * 1024 * 1024
MAX_REGIONS = 1000
MODELS = {'Det': 'PP-OCRv6_det_small.onnx', 'Cls': 'ch_ppocr_mobile_v2.0_cls_mobile.onnx',
          'Rec': 'PP-OCRv6_rec_small.onnx'}


class OcrError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def local_models():
    spec = find_spec('rapidocr')
    root = Path(spec.origin).parent / 'models' if spec and spec.origin else None
    if root is None or any(not (root / name).is_file() for name in MODELS.values()):
        raise OcrError('ocr_unavailable')
    return {key: root / name for key, name in MODELS.items()}


class LocalOcr:
    def __init__(self, previews):
        self.previews, self.preview_bytes, self.pages = previews, 0, 0
        self.engine = None
        self.identity = None

    def initialize(self):
        if self.engine is not None:
            return
        models = local_models()  # Explicit existing paths bypass RapidOCR's downloader.
        for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            os.environ[key] = '1'
        try:
            import cv2
            from rapidocr import RapidOCR
            cv2.setNumThreads(1)
            params = {f'{key}.model_path': str(path) for key, path in models.items()}
            params.update({'EngineConfig.onnxruntime.intra_op_num_threads': 1,
                           'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                           'EngineConfig.onnxruntime.enable_cpu_mem_arena': False,
                           'Global.log_level': 'error', 'Global.text_score': 0,
                           'Det.limit_side_len': 736, 'Det.limit_type': 'max', 'Rec.rec_batch_num': 1})
            self.engine = RapidOCR(params=params)
            hashes = {}
            for key, path in models.items():
                with path.open('rb') as source:
                    hashes[key] = hashlib.file_digest(source, 'sha256').hexdigest()
            self.identity = f"RapidOCR/{version('rapidocr')}/onnx-cpu;" + ';'.join(f'{k}:{v}' for k,v in hashes.items())
        except MemoryError:
            raise
        except Exception:
            raise OcrError('ocr_unavailable') from None

    def recognize(self, image, page, add):
        self.pages += 1
        if self.pages > MAX_OCR_PAGES:
            raise OcrError('ocr_page_limit')
        self.initialize()
        import numpy as np
        from PIL import Image
        # The preview and OCR share these exact pixels and top-left coordinates.
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        image = image.convert('RGB')
        target = BytesIO()
        image.save(target, format='PNG')
        raw = target.getvalue()
        self.preview_bytes += len(raw)
        if self.preview_bytes > MAX_PREVIEW_BYTES:
            raise OcrError('ocr_preview_limit')
        self.previews[str(page)] = base64.b64encode(raw).decode('ascii')
        try:
            output = self.engine(np.asarray(image))
        except MemoryError:
            raise
        except Exception:
            raise OcrError('ocr_failed') from None
        texts = list(output.txts or []) if output is not None else []
        if len(texts) > MAX_REGIONS:
            raise OcrError('ocr_region_limit')
        for index, text in enumerate(texts):
            box, score = output.boxes[index], float(output.scores[index])
            x0, y0 = max(0., float(min(p[0] for p in box))), max(0., float(min(p[1] for p in box)))
            x1, y1 = min(float(image.width), float(max(p[0] for p in box))), min(float(image.height), float(max(p[1] for p in box)))
            if not all(math.isfinite(n) for n in (x0,y0,x1,y1,score)) or x1 <= x0 or y1 <= y0 or not 0 <= score <= 1:
                raise OcrError('ocr_invalid_result')
            bbox = dict(x=x0/image.width, y=y0/image.height, width=(x1-x0)/image.width,
                        height=(y1-y0)/image.height, coordinate_system='normalized_0_1')
            reasons = ['requires_original_review']
            if score < .85:
                reasons.append('low_signal')
            if any(c in text for c in '?？�'):
                reasons.append('ambiguous_characters')
            add(text, dict(kind='ocr_region', page=page, region=index+1, bbox=bbox),
                dict(format='ocr', engine=self.identity, signal_score=score, uncertain=True, uncertainty_reasons=reasons,
                     coverage='图像识别候选；评分不是正确率，数值与模糊字符必须对照原页核实。'))
        if not texts:
            add('本页未识别出可用文字，请查看原页核对。',
                dict(kind='ocr_region', page=page, region=1,
                     bbox=dict(x=0,y=0,width=1,height=1,coordinate_system='normalized_0_1')),
                dict(format='ocr', engine=self.identity, signal_score=None, uncertain=True,
                     uncertainty_reasons=['no_text_detected'], coverage='没有识别结果不代表本页没有内容。'))


def image_document(raw, extension):
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        image = Image.open(BytesIO(raw))
        if image.format != (('PNG' if extension == '.png' else 'JPEG')):
            raise OcrError('image_signature')
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise OcrError('image_pixel_limit')
        if getattr(image, 'n_frames', 1) != 1:
            raise OcrError('image_frames_unsupported')
        image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
            rgba = image.convert('RGBA')
            paper = Image.new('RGBA', rgba.size, 'white')
            return Image.alpha_composite(paper, rgba).convert('RGB')
        return image.convert('RGB')
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise OcrError('image_pixel_limit') from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise OcrError('image_signature') from None


def pdf_page_image(pdf, index):
    page = pdf[index]
    try:
        width, height = page.get_size()
        if not all(math.isfinite(n) and 0 < n <= 100_000 for n in (width,height)):
            raise OcrError('pdf_invalid')
        bitmap = page.render(scale=min(2., 1600/max(width,height)))
        try:
            return bitmap.to_pil().convert('RGB')
        finally:
            bitmap.close()
    finally:
        page.close()
