from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.services.document_tools.document_ir import SourceAnchor, ToolError
from app.services.document_tools.qwen_ocr import parse_html_tables, recognize, request_contract


def config(protocol='dashscope'):
    return SimpleNamespace(document_tools_qwen_api_key=SecretStr('test-placeholder'),document_tools_qwen_base_url='https://example.invalid/api/v1' if protocol=='dashscope' else 'https://example.invalid/compatible-mode/v1',
        document_tools_qwen_protocol=protocol,document_tools_qwen_ocr_model='qwen3.5-ocr',document_tools_qwen_layout_model='qwen3-vl-plus')


def test_dashscope_real_task_contract():
    endpoint,body=request_contract(config(),b'png')
    assert endpoint=='https://example.invalid/api/v1/services/aigc/multimodal-generation/generation'
    assert body['parameters']['ocr_options']=={'task':'table_parsing'}
    assert body['parameters']['max_tokens']==16384  # Verified workspace service limit.
    assert 'messages' in body['input']


def test_openai_contract_has_no_dashscope_parameters():
    endpoint,body=request_contract(config('openai'),b'png')
    assert endpoint.endswith('/chat/completions')
    assert 'ocr_options' not in body and 'parameters' not in body
    assert body['messages'][0]['content'][0]['type']=='image_url'


@pytest.mark.parametrize('protocol', ['dashscope', 'openai'])
@pytest.mark.parametrize('task,layout', [('table', False), ('text', False), ('text', True)])
def test_flash_visual_transcription_avoids_ocr_only_parameters(protocol, task, layout):
    settings = config(protocol)
    settings.document_tools_qwen_ocr_model = 'qwen3.8-flash'
    settings.document_tools_qwen_layout_model = 'qwen3.8-flash'
    _, body = request_contract(settings, b'png', task=task, layout=layout)
    assert body['model'] == 'qwen3.8-flash'
    parameters = body.get('parameters', body)
    assert parameters['enable_thinking'] is False
    assert parameters['max_tokens'] == 16384
    assert 'ocr_options' not in parameters
    messages = body.get('input', body)['messages']
    assert 'enable_rotate' not in messages[0]['content'][0]
    assert '不补全数字' in messages[0]['content'][-1]['text']


@pytest.mark.parametrize('protocol', ['dashscope', 'openai'])
def test_rename_prompt_is_opt_in_and_does_not_change_conversion_prompt(protocol):
    from app.services.document_tools.qwen_ocr import PROMPT
    _, custom = request_contract(config(protocol), b'png', task='text', layout=True, prompt='rename-only')
    _, original = request_contract(config(protocol), b'png')
    messages = lambda body: body.get('input', body)['messages']
    assert messages(custom)[0]['content'][-1]['text'] == 'rename-only'
    assert messages(original)[0]['content'][-1]['text'] == PROMPT
    assert custom['model'] == 'qwen3-vl-plus'


def test_html_merges_unknown_blank_precise_region():
    tables=parse_html_tables('<table><tr><th colspan="2">A</th><th>B</th></tr><tr><td rowspan="2">00123</td><td></td><td>[无法辨认]</td></tr><tr><td>12.50</td><td>2</td></tr></table>',SourceAnchor(page_index=2,bbox_pt=[1,2,80,90],anchor_precision='region'))
    t=tables[0]
    assert (t.row_count,t.column_count)==(3,3)
    assert t.cells[0].colspan==2 and t.cells[2].rowspan==2
    assert t.cells[3].raw_text=='' and t.cells[3].resolution!='unknown'
    assert t.cells[4].resolution=='unknown'
    assert all(c.source.anchor_precision=='region' for c in t.cells)


@pytest.mark.parametrize('html',['<table><tr><td>1</td></tr>','<table><tr><td colspan="bad">A</td></tr></table>','<table><tr><td>A</td><td>B</td></tr><tr><td>C</td></tr></table>'])
def test_malformed_or_missing_cells_rejected(html):
    with pytest.raises(ToolError): parse_html_tables(html,SourceAnchor())


class Response:
    def __init__(self,status=200,finish='stop'):
        self.status_code=status; self.finish=finish
    def json(self):
        return {'output':{'choices':[{'finish_reason':self.finish,'message':{'content':[{'text':'<table><tr><td>00123</td></tr></table>'}]}}]},'usage':{'input_tokens':123,'output_tokens':20}}


class Client:
    def __init__(self,responses): self.responses=iter(responses); self.calls=0
    def post(self,*args,**kwargs): self.calls+=1; return next(self.responses)


def test_usage_and_bounded_transient_retry():
    client=Client([Response(503),Response()])
    result=recognize(config(),b'png',client=client)
    assert client.calls==2 and result['usage']['input_tokens']==123 and result['attempts']==2


def test_truncation_and_auth_never_retry():
    for response in [Response(200,'length'),Response(401)]:
        client=Client([response])
        with pytest.raises(ToolError): recognize(config(),b'png',client=client)
        assert client.calls==1
