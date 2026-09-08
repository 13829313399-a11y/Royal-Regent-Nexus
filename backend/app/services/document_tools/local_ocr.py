"""Local OCR candidates with image-to-visible-page coordinate provenance."""
import threading
from functools import lru_cache

from .document_ir import ToolError

_lock = threading.Lock()


@lru_cache(maxsize=1)
def get_engine():
    from rapidocr import RapidOCR
    return RapidOCR()


def recognize(image, bbox_pt):
    import numpy as np
    try:
        with _lock:
            output = get_engine()(np.asarray(image.convert("RGB")))
    except Exception:
        raise ToolError("LOCAL_OCR_UNAVAILABLE", "本地 OCR 模型未就绪或识别失败，请检查模型安装") from None
    if output is None or output.txts is None:
        return []
    sx, sy = (bbox_pt[2]-bbox_pt[0])/image.width, (bbox_pt[3]-bbox_pt[1])/image.height
    result = []
    for points, text, score in zip(output.boxes, output.txts, output.scores):
        xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
        result.append({"text": text, "bbox_pt": [bbox_pt[0]+min(xs)*sx,bbox_pt[1]+min(ys)*sy,
                        bbox_pt[0]+max(xs)*sx,bbox_pt[1]+max(ys)*sy], "signal_score": float(score)})
    return result


def recover_tables(image, lines, bbox_pt, page_index, prefix):
    """Recover scanned ruled grids from observed lines, including merged cells.

    No table is invented when no closed grid is present. Content-bearing cells
    without OCR are unknown; visually blank cells remain distinct.
    """
    import cv2
    import numpy as np
    from .document_ir import Cell, SourceAnchor, Table
    gray=np.asarray(image.convert("L"))
    binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,15)
    horizontal=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((1,max(20,image.width//25)),np.uint8))
    vertical=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((max(20,image.height//35),1),np.uint8))
    grid=cv2.bitwise_or(horizontal,vertical)
    contours,hierarchy=cv2.findContours(grid,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    sx,sy=(bbox_pt[2]-bbox_pt[0])/image.width,(bbox_pt[3]-bbox_pt[1])/image.height
    groups={}
    for i,contour in enumerate(contours):
        parent=int(hierarchy[0][i][3])
        if parent<0:
            continue
        x,y,w,h=cv2.boundingRect(contour)
        if w<max(15,image.width*.025) or h<12 or cv2.contourArea(contour)<w*h*.85:
            continue
        groups.setdefault(parent,[]).append((x,y,x+w,y+h))
    results=[]
    def cluster(values):
        clusters=[]
        for value in sorted(values):
            if clusters and value-clusters[-1][-1]<8:
                clusters[-1].append(value)
            else:
                clusters.append([value])
        return [sum(c)/len(c) for c in clusters]
    for cells in groups.values():
        if len(cells)<4:
            continue
        xs=cluster([x for rect in cells for x in (rect[0],rect[2])]); ys=cluster([y for rect in cells for y in (rect[1],rect[3])])
        if len(xs)<3 or len(ys)<3:
            continue
        table_id=f"{prefix}-local-grid{len(results)}"
        def anchor(rect):
            return SourceAnchor(page_index=page_index,bbox_pt=[bbox_pt[0]+rect[0]*sx,bbox_pt[1]+rect[1]*sy,bbox_pt[0]+rect[2]*sx,bbox_pt[1]+rect[3]*sy],method="local_ocr",anchor_precision="cell")
        table=Table(id=table_id,row_count=len(ys)-1,column_count=len(xs)-1,source_pages=[page_index],header_rows=[0],source=anchor([xs[0],ys[0],xs[-1],ys[-1]]))
        occupied=set()
        for rect in sorted(cells,key=lambda r:(r[1],r[0])):
            c,cend=[min(range(len(xs)),key=lambda i:abs(xs[i]-x)) for x in (rect[0],rect[2])]
            r,rend=[min(range(len(ys)),key=lambda i:abs(ys[i]-y)) for y in (rect[1],rect[3])]
            if rend<=r or cend<=c:
                continue
            source=anchor(rect); box=source.bbox_pt
            matching=[line for line in lines if box[0]<=(line["bbox_pt"][0]+line["bbox_pt"][2])/2<=box[2] and box[1]<=(line["bbox_pt"][1]+line["bbox_pt"][3])/2<=box[3]]
            text="\n".join(line["text"] for line in sorted(matching,key=lambda l:(l["bbox_pt"][1],l["bbox_pt"][0])))
            x0,y0,x1,y1=rect
            inner=binary[y0+4:y1-4,x0+4:x1-4]
            content_without_ocr=not text and inner.size>0 and np.count_nonzero(inner)>max(12,inner.size*.001)
            # A remaining digit next to a solid occlusion is only a partial
            # candidate. Large solid ink must not turn e.g. 12.50 into numeric 1.
            solid_occlusion=False
            if inner.size:
                kernel=max(5,int(min(inner.shape)*.1))
                dark=(gray[y0+4:y1-4,x0+4:x1-4]<80).astype(np.uint8)*255
                solid=cv2.morphologyEx(dark,cv2.MORPH_OPEN,np.ones((kernel,kernel),np.uint8))
                solid_occlusion=np.count_nonzero(solid)>inner.size*.06
            unknown=content_without_ocr or solid_occlusion
            table.cells.append(Cell(id=f"{table_id}-r{r}c{c}",row=r,column=c,rowspan=rend-r,colspan=cend-c,raw_text=text or ("[无法辨认]" if unknown else ""),
                display_text="[无法辨认]" if unknown else text,value=None if unknown else text,
                resolution="unknown" if unknown else "needs_review" if text else "resolved",source=source,
                candidates=[text] if unknown and text else []))
            occupied.update((rr,cc) for rr in range(r,rend) for cc in range(c,cend))
        if len(occupied)==table.row_count*table.column_count:
            results.append(table)
    return results
