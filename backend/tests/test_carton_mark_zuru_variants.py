"""Independent minimal source fixtures for paired and split-column layouts."""
import io

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from pypdf import PdfReader

from app.services.carton_mark_zuru import extract_zuru, prepare_records
from app.services.carton_supplier_mark_pdf import prepare_pdf
from test_carton_mark_zuru import original


def workbook(cells):
    book=Workbook();sheet=book.active
    for location,value in cells.items():sheet[location]=value
    stream=io.BytesIO();book.save(stream);book.close();return stream.getvalue()


def archibrand(other_item=False, side_quantity="50PCS"):
    cells={}
    for start,item in ((1,"0077770GQ2"),(23,"009574")) if other_item else ((1,"0077770GQ2"),):
        for offset, label in ((0,"FRONT MARK:"),(10,"SIDE MARK:")):
            cells[f"B{start+offset}"]=label
            cells[f"B{start+offset+1}"]="ARCHIBRAND, S.A. de C.V"
            for delta,label,value in ((2,"ITEM NO.:",item),(3,"ITEM DESCRIPTION:","PETS ALIVE-MOMMY & BABY SURPRISE-SERIES 1-MOMMY CAPYBARA & BABY SURPRISE"),
                    (4,"CTN QTY:","50PCS" if offset==0 else side_quantity),(5,"CTN NUMBER: /","49")):
                cells[f"B{start+offset+delta}"]=label
                if value:cells[f"D{start+offset+delta}"]=value
            if offset==0:cells[f"B{start+offset+6}"]="MADE IN CHINA"
    return workbook(cells)


def anko(weight="3.18 KGS",dims="45.10 X 23.20 X 40.30 CMS"):
    return workbook(dict(A1="OUTER CARTON MAIN MARK (2 SIDES PRINTING)",B1="OUTER CARTON SIDE MARK (2 SIDES PRINTING)",
        A2="ITEM#92120TQ1",A3="ANKO",A4="NZ",A5="Dept No. 087",A6="Order No.21894319",A7="*Keycode 43569786",
        A8="Description RB AXOLOTLCORNS SURP",A9="Qty Issue Pack 12 PCS Only",A10="Qty Shipper Pack 12 PCS Only",A11="Carton No. of 5",
        B3="Made in China",B4="GRS.WT "+weight,B5="D: "+dims))


def test_archibrand_pairs_faces_and_selects_only_exact_sku_with_long_description():
    data=archibrand(other_item=True,side_quantity="")
    records=extract_zuru("source.xlsx",data)
    assert [r["fields"]["item"] for r in records]==["0077770GQ2","009574"]
    source=original(excel_bytes=data,item_no="009574")
    content,count,_=prepare_pdf(source)
    text=PdfReader(io.BytesIO(content)).pages[0].extract_text()
    assert count==1 and "009574" in text and "0077770GQ2" not in text
    assert "ARCHIBRAND" in text and "SURPRISE" in text and "50PCS" in text
    assert text.count("MADE IN CHINA")==1
    assert text.count("CTN NUMBER")==2


@pytest.mark.parametrize("side_quantity",["12PCS","#N/A"])
def test_archibrand_rejects_conflicting_or_errored_faces(side_quantity):
    with pytest.raises(HTTPException):extract_zuru("source.xlsx",archibrand(side_quantity=side_quantity))


def test_anko_split_columns_preserve_leading_zeros_and_sscc_review_guide():
    data=anko();record,_=prepare_records(original(excel_bytes=data,item_no="92120",source_item="92120TQ1"))
    assert record["fields"]["department"]=="087" and record["fields"]["keycode"]=="43569786"
    source=original(excel_bytes=data,item_no="92120",source_item="92120TQ1")
    content,count,notes=prepare_pdf(source);text=PdfReader(io.BytesIO(content)).pages[0].extract_text()
    assert count==1 and "Dept No. 087" in text and "92120TQ1" not in text # source SKU remains provenance, as reference body omits it
    assert "3.18 KGS" in text and "45.10 X 23.20 X 40.30 CMS" in text
    assert "SSCC LABEL" in text and "4 x 4 inch" in text and any("实际印刷尺寸" in n for n in notes)
    assert "Qty Issue Pack 12 PCS Only" in text and "Qty Shipper Pack 12 PCS Only" in text


@pytest.mark.parametrize("weight,dims",[("9.51 KGS","45.10 X 23.20 X 40.30 CMS"),("3.18 KGS","100 X 100 X 14 CM"),("3.18 LB","10 X 20 X 30 CM"),("#N/A","10 X 20 X 30 CM"),("3..18 KGS","10 X 20 X 30 CM"),("3.18 KGS","10 X . X 30 CM")])
def test_anko_unknown_units_formula_errors_and_missing_heavy_handling_artwork_block(weight,dims):
    with pytest.raises(HTTPException):prepare_records(original(excel_bytes=anko(weight,dims),item_no="92120TQ1"))


def test_anko_exact_handling_threshold_does_not_round_up():
    record,_=prepare_records(original(excel_bytes=anko("9.5 KGS","100 X 100 X 13 CM"),item_no="92120TQ1"))
    assert record["fields"]["gross_weight"]=="9.5 KGS"


@pytest.mark.parametrize("profile",["archibrand","anko"])
@pytest.mark.parametrize("mode,pages",[("front_only",1),("separate_pages",2)])
def test_new_profiles_respect_existing_front_and_separate_page_modes(profile,mode,pages):
    data=archibrand() if profile=="archibrand" else anko()
    source=original(excel_bytes=data,item_no="0077770GQ2" if profile=="archibrand" else "92120TQ1")
    source["layout"]["config"]["mode"]=mode
    content,count,_=prepare_pdf(source)
    assert count==len(PdfReader(io.BytesIO(content)).pages)==pages
