import json

import httpx
import pytest
from pydantic import SecretStr

from app.services.carton_mark_ai_pilot import (Evidence,FIELDS,PilotError,load_template,
    request_plan,validate_plan,render_review,select_mapping_evidence)


def inputs():
    entries=[Evidence(id="header",kind="reference_pdf",location="page:1/line:1",text="4500218355 15784")]
    texts={"recipient":"ZUMIEZ INC.","customer_po":"00484860","article":"00415647",
           "product":"FUGGLER BADDIE","quantity":"12 PCS","carton_total":"42","country":"CHINA"}
    fields={"contract":{"source_id":"header","value":"4500218355"},
            "item":{"source_id":"header","value":"15784"}}
    for key,value in texts.items():
        entries.append(Evidence(id=key,kind="current_excel" if key not in {"quantity","carton_total"} else "reference_pdf",
                                location="SM!D1",text=value))
        fields[key]={"source_id":key,"value":value}
    return entries,{"template_id":"zumiez-review-v1","layout_variant":"reference","fields":fields}


def test_leading_zeros_and_explicit_reference_supplement_provenance():
    entries,raw=inputs()
    _,values,proof=validate_plan(json.dumps(raw),entries,load_template(),{"customer_po":"00484860"})
    assert values["customer_po"]=="00484860" and values["article"]=="00415647"
    assert proof["quantity"]["kind"]=="reference_pdf" and proof["country"]["kind"]=="current_excel"


def test_only_necessary_field_lines_and_explicit_fallbacks_are_sent():
    rows=[("current_excel","PO NUMBER: 00484860"),("current_excel","Remark: internal supplier note"),
          ("reference_pdf","4500218355 15784"),("reference_pdf","QUANTITY : 12 PCS"),
          ("reference_pdf","CTN QTY: / 42 CTNS"),("reference_pdf","old logo printing instructions"),
          ("reference_pdf","PO NUMBER: 11111111")]
    evidence=[Evidence(id=str(i),kind=k,location="test",text=t) for i,(k,t) in enumerate(rows)]
    assert [e.id for e in select_mapping_evidence(evidence)]==["0","2","3","4"]


@pytest.mark.parametrize("change",["invented","source","schema","variant","template","null","identity"])
def test_invalid_source_or_model_contract_is_rejected(change):
    entries,raw=inputs()
    if change=="invented":raw["fields"]["quantity"]["value"]="13 PCS"
    elif change=="source":raw["fields"]["quantity"]["source_id"]="unknown"
    elif change=="schema":raw["execute"]="change order"
    elif change=="variant":raw["layout_variant"]="execute-python"
    elif change=="template":raw["template_id"]="different"
    elif change=="null":raw["fields"]["quantity"]=None
    else:raw["fields"]["contract"]["value"]="450021835"
    with pytest.raises(PilotError):validate_plan(json.dumps(raw),entries,load_template())


def test_pdf_cannot_silently_replace_excel_value_even_when_it_is_valid_source_text():
    entries,raw=inputs()
    entries.append(Evidence(id="old",kind="reference_pdf",location="page:1",text="OLD PRODUCT"))
    raw["fields"]["product"]={"source_id":"old","value":"OLD PRODUCT"}
    with pytest.raises(PilotError,match="Excel"):
        validate_plan(json.dumps(raw),entries,load_template(),{"product":"FUGGLER BADDIE"})


def test_duplicate_json_and_missing_fields_are_rejected():
    entries,raw=inputs()
    bad=json.dumps(raw).replace('"layout_variant": "reference"','"layout_variant": "reference", "layout_variant": "reference"')
    with pytest.raises(PilotError):validate_plan(bad,entries,load_template())
    del raw["fields"]["country"]
    with pytest.raises(PilotError):validate_plan(json.dumps(raw),entries,load_template())


def connection(**changes):
    return {"base_url":"https://api.deepseek.com","model":"deepseek-flash",
            "api_key":SecretStr("PRIVATE_TEST_SECRET"),"protocol":"openai",**changes}


def test_shared_compatible_connection_returns_bounded_json_and_usage():
    entries,raw=inputs();requests=[]
    def handler(request):
        requests.append(request)
        body=json.loads(request.content)
        assert body["model"]=="deepseek-flash" and body["response_format"]=={"type":"json_object"}
        assert body["thinking"]=={"type":"disabled"}
        assert body["max_tokens"]==3500 and not body["stream"]
        assert "PRIVATE_TEST_SECRET" not in request.content.decode()
        return httpx.Response(200,json={"id":"response-1","model":"deepseek-v4.1-flash-1017",
            "usage":{"total_tokens":123},"choices":[{"finish_reason":"stop","message":{"content":json.dumps(raw)}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        text,receipt=request_plan(entries,load_template(),connection(),client=client)
    assert len(requests)==1 and str(requests[0].url)=="https://api.deepseek.com/chat/completions"
    assert receipt["usage"]["total_tokens"]==123
    validate_plan(text,entries,load_template())


@pytest.mark.parametrize("status",[302,401,402,429,503])
def test_provider_failures_do_not_retry_or_expose_secret_or_response(status):
    entries,_=inputs();calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status,text="PRIVATE_TEST_SECRET",headers={"location":"https://other.invalid"})
    with httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False) as client:
        with pytest.raises(PilotError) as error:request_plan(entries,load_template(),connection(),client=client)
    assert len(calls)==1 and "PRIVATE_TEST_SECRET" not in str(error.value)


def test_incomplete_response_is_not_accepted_and_http_url_never_receives_key():
    entries,_=inputs();calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={"choices":[{"finish_reason":"length","message":{"content":"{}"}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PilotError):request_plan(entries,load_template(),connection(),client=client)
        with pytest.raises(PilotError):request_plan(entries,load_template(),connection(base_url="http://unsafe.invalid"),client=client)
    assert len(calls)==1


def test_wrong_reference_cannot_reuse_fixed_artwork():
    with pytest.raises(PilotError,match="参考稿不匹配"):
        render_review(b"wrong file",load_template(),{}, {},api_verified=True)
