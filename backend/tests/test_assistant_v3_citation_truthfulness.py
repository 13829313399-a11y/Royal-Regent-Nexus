"""Offline citation eligibility is not a semantic verification score."""
from app.services.assistant.evidence import RunContent


def material(eligible=True):
    return dict(kind='file', source_id='file-source', run_id='run', title='Synthetic range',
                file_ref=dict(kind='document',id='file'), locator=dict(kind='document'),
                extracted_at='2026-10-26T00:00:00+00:00', citation_eligible=eligible,
                citation_aliases={'chat-0':'1'}, provider_ref='1',step_id='chat-0')


def test_ineligible_material_cannot_bind_even_if_it_has_an_old_alias():
    content=RunContent('run')
    content.add_source(material(False))
    content.append('text','Quoted fact [ref_1] and unknown [ref_99].','chat-0')
    content.terminal('completed')
    assert all(c['resolution']=='unresolved' and c['source_ids']==[] for c in content.evidence['citations'])
    assert content.evidence['sources'][0]['source_id']=='file-source'  # Range remains inspectable.


def test_later_ineligibility_removes_the_existing_binding():
    content=RunContent('run')
    content.add_source(material())
    content.append('text','A registered reference [ref_1].','chat-0')
    assert content.evidence['citations'][0]['resolution']=='resolved'
    content.add_source(material(False))
    content.terminal('completed')
    assert content.evidence['citations'][0]['source_ids']==[]
    assert content.evidence['citations'][0]['resolution']=='unresolved'


def test_registered_references_preserve_conflicting_excerpts_without_claiming_semantic_verification():
    content=RunContent('run','on')
    content.web('search-0',[
        dict(index=1,url='https://example.org/first',title='First report',snippet='Same scope, same date: 120 boxes.'),
        dict(index=2,url='https://example.org/second',title='Correction',snippet='Same scope, same date: 100 boxes; first report differs.'),
    ])
    content.citation_context('chat-0')
    answer='The reports conflict: 120 [ref_1] versus 100 [ref_2]; do not choose a confirmed total.'
    content.append('text',answer,'chat-0');content.terminal('completed')
    assert content.parts[0]['text']==answer
    assert [s['excerpt'] for s in content.evidence['sources']]==[
        'Same scope, same date: 120 boxes.','Same scope, same date: 100 boxes; first report differs.']
    assert all(c['resolution']=='resolved' for c in content.evidence['citations'])
    assert all(set(c)=={'binding_id','part_id','marker','source_ids','resolution'} for c in content.evidence['citations'])
    assert all(s['evidence_level']=='search_result' for s in content.evidence['sources'])


def test_plain_numeric_and_other_step_references_are_never_guessed():
    content=RunContent('run')
    content.add_source(material())
    content.append('text','Plain [1] and another step [ref_1], unknown [ref_999], code `[ref_2]`.','chat-1')
    content.terminal('completed')
    assert [c['marker'] for c in content.evidence['citations']]==['[ref_1]','[ref_999]']
    assert all(c['resolution']=='unresolved' for c in content.evidence['citations'])
