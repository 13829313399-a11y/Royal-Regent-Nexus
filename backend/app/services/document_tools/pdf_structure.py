"""Conservative PDF numeric typing and explicit continuation merging."""
import re
from decimal import Decimal, InvalidOperation


def type_cells(ir, options, issue):
    locale=options.get("numeric_locale","preserve_ambiguous")
    for table in ir.tables:
        for cell in table.cells:
            raw=cell.display_text.strip()
            if not raw or cell.resolution in {"unknown","unresolved"} or cell.source.method=="manual":
                continue
            if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}",raw):
                issue(ir,"DATE_AMBIGUOUS","日期地区语义未确定，保留原文",cell.source,cell.id)
                continue
            text=raw
            symbol=""
            if text[:1] in {"$","€","£","¥","￥"}:
                symbol,text=text[0],text[1:].strip()
            percent=text.endswith("%")
            if percent: text=text[:-1]
            negative=text.startswith("(") and text.endswith(")")
            if negative: text=text[1:-1]
            if not re.fullmatch(r"[-+]?\d[\d,.]*",text):
                continue
            digits=text.lstrip("+-").replace(",","").replace(".","")
            # Identifiers: keep leading zeros and precision-risk digit strings.
            if (len(text.lstrip("+-"))>1 and text.lstrip("+-").startswith("0") and not text.lstrip("+-").startswith(("0.","0,"))) or len(digits.lstrip("0"))>15:
                cell.value_kind="text"; cell.value=raw
                continue
            if locale=="preserve_ambiguous" and re.fullmatch(r"[-+]?\d{1,3}[,.]\d{3}",text):
                issue(ir,"NUMERIC_LOCALE_AMBIGUOUS","逗号或点号可能表示小数或千分位，已保留原字串",cell.source,cell.id)
                continue
            if locale=="comma_decimal":
                if text.count(",")>1 or ("." in text and not re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+(?:,\d+)?",text)):
                    issue(ir,"NUMERIC_FORMAT_UNRESOLVED","数字格式与所选地区不一致，保留原文",cell.source,cell.id); continue
                text=text.replace(".","").replace(",",".")
            else:
                if "," in text:
                    if not re.fullmatch(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?",text):
                        issue(ir,"NUMERIC_FORMAT_UNRESOLVED","数字分隔符无法可靠解释，保留原文",cell.source,cell.id); continue
                    text=text.replace(",","")
            try:
                value=Decimal(text)
            except InvalidOperation:
                continue
            if negative: value=-value
            decimals=len(text.split(".")[1]) if "." in text else 0
            if percent: value/=100
            cell.value_kind="percentage" if percent else "currency" if symbol else "decimal" if decimals else "integer"
            cell.value=str(value)
            cell.style["number_format"]=(f'"{symbol}"' if symbol else "")+"#,##0"+("."+"0"*decimals if decimals else "")+("%" if percent else "")


def merge_continuations(ir, issue):
    """Only adjacent page-edge tables with matching headers and geometry merge."""
    pages={p.page_index:p for p in ir.pages}
    kept=[]; removed=set()
    for table in ir.tables:
        if not kept:
            kept.append(table); continue
        previous=kept[-1]
        a,b=previous.source,table.source
        last_page=max(previous.source_pages) if previous.source_pages else a.page_index
        adjacent=last_page is not None and b.page_index==last_page+1
        def headers(t):
            return [(c.column,c.colspan,c.raw_text.strip()) for c in t.cells if c.row in t.header_rows]
        same=table.column_count==previous.column_count and headers(table)==headers(previous) and bool(headers(table))
        # Compare each elementary column's x geometry, not just overall width.
        def edges(t):
            return sorted({round(x,1) for c in t.cells if c.source.bbox_pt for x in (c.source.bbox_pt[0],c.source.bbox_pt[2])})
        ea,eb=edges(previous),edges(table)
        aligned=len(ea)==len(eb) and bool(ea) and all(abs(x-y)<=2 for x,y in zip(ea,eb))
        page_a=pages.get(last_page); page_b=pages.get(b.page_index)
        edge=bool(page_a and page_b and a.bbox_pt and b.bbox_pt and a.bbox_pt[3]>=page_a.height_pt*.78 and b.bbox_pt[1]<=page_b.height_pt*.22)
        # Units/notes between tables imply distinct context, so refuse automatic join.
        between=any(block.kind!="table" and block.text.strip() and block.source.page_index in {last_page,b.page_index} and block.source.bbox_pt and
            ((block.source.page_index==last_page and block.source.bbox_pt[1]>a.bbox_pt[3]) or
             (block.source.page_index==b.page_index and block.source.bbox_pt[3]<b.bbox_pt[1])) for block in ir.blocks) if a.bbox_pt and b.bbox_pt else True
        if adjacent and same and aligned and edge and not between:
            skip=len(table.header_rows)
            for cell in table.cells:
                if cell.row not in table.header_rows:
                    cell.row=previous.row_count+cell.row-skip
                    previous.cells.append(cell)
            previous.row_count+=table.row_count-skip
            previous.source_pages.extend(table.source_pages)
            previous.source=table.source.model_copy(deep=True)
            removed.add(table.id)
        else:
            if adjacent and same:
                issue(ir,"TABLE_CONTINUATION_CANDIDATE","表头相同但页边界、列位置或上下文不足，保留独立表供核验",table.source,table.id)
            kept.append(table)
    ir.tables=kept
    ir.blocks=[b for b in ir.blocks if b.table_id not in removed]
