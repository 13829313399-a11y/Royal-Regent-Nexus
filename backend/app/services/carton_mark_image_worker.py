"""Bounded local-only OCR subprocess; image text is reference evidence, never order data."""
import base64
import io
import json
import sys
from pathlib import Path


def main():
    import numpy as np
    from PIL import Image
    import rapidocr
    from rapidocr import RapidOCR
    models=Path(rapidocr.__file__).parent/"models"
    paths={"Det.model_path":models/"PP-OCRv6_det_small.onnx",
           "Rec.model_path":models/"PP-OCRv6_rec_small.onnx",
           "Cls.model_path":models/"ch_ppocr_mobile_v2.0_cls_mobile.onnx"}
    if not all(p.is_file() for p in paths.values()):raise ValueError("local models unavailable")
    params={key:str(path) for key,path in paths.items()}
    params.update({"EngineConfig.onnxruntime.intra_op_num_threads":2,
                   "EngineConfig.onnxruntime.inter_op_num_threads":2,"Global.log_level":"error"})
    engine=RapidOCR(params=params)
    images=json.loads(sys.stdin.buffer.read(9_000_000));result=[]
    for item in images[:12]:
        with Image.open(io.BytesIO(base64.b64decode(item["data"]))) as image:
            if image.width*image.height>4_000_000:raise ValueError("image too large")
            output=engine(np.asarray(image.convert("RGB")))
            lines=[] if output is None or output.txts is None else [
                dict(text=str(text)[:500],score=round(float(score),3)) for text,score in zip(output.txts,output.scores)]
            result.append(dict(id=item["id"],lines=lines[:60]))
    print("CARTON_OCR_RESULT="+json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
