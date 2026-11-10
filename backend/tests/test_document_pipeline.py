import hashlib
import json

from PIL import Image

from app.core.config import settings
from app.services.document_tools import document_pipeline as pipeline, general_translation as g, local_ocr


def block(source,**values):
    return g.ReadingBlock(id='b1',source=source,bbox=[10,10,500,200],**values)


def test_private_source_cache_is_scoped_fingerprinted_and_explicitly_refreshable(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'document_tools_storage_dir',str(tmp_path/'storage'))
    monkeypatch.setattr(pipeline,'translation_connection',lambda:('https://provider.invalid','mimo','secret-test-key'))
    monkeypatch.setattr(local_ocr,'recognize',lambda *args:[])
    source=tmp_path/'source.png';Image.new('RGB',(100,100),'white').save(source)
    calls=[]
    def read(*args):
        calls.append(1)
        return g.ReadingPage(complete=True,blocks=[block('Novel source text')]),{'literal':True}
    monkeypatch.setattr(g,'read_page',read)
    owner=lambda value:hashlib.sha256(value.encode()).hexdigest()
    options={'translation_engine':'online','_source_cache_scope':owner('owner-a/source-a')}
    first=pipeline.source_page({'input':str(source)},options,lambda:False)
    second=pipeline.source_page({'input':str(source)},options,lambda:False)
    assert not first[2]['source_cache_hit'] and second[2]['source_cache_hit'] and len(calls)==1
    pipeline.source_page({'input':str(source)},{**options,'_source_cache_scope':owner('owner-b/source-b')},lambda:False)
    assert len(calls)==2
    pipeline.source_page({'input':str(source)},{**options,'refresh_source':True},lambda:False)
    assert len(calls)==3
    monkeypatch.setattr(settings,'document_tools_translation_model','a-different-model')
    pipeline.source_page({'input':str(source)},options,lambda:False)
    assert len(calls)==4
    assert all('secret-test-key' not in path.read_text(encoding='utf-8') for path in (tmp_path/'storage').rglob('*.json'))


def test_shared_clause_is_verified_once_without_copying_a_missing_tail(tmp_path,monkeypatch):
    first='Ear is thinner at top and tapers outward to a rounded bottom'
    tail='bottom of ear aligns with the bottom of the snout'
    readings=[g.ReadingPage(complete=True,blocks=[block(first+' – '+tail)]),
              g.ReadingPage(complete=True,blocks=[block(first+' – '+tail)]),
              g.ReadingPage(complete=True,blocks=[block(first)])]
    pages=[]
    for i in range(3):
        path=tmp_path/f'p{i}.png';Image.new('RGB',(100,100),'white').save(path);pages.append({'input':str(path)})
    translated=[];verified=[]
    def translate(reading,*args):
        for b in reading.blocks:
            translated.append(b.source)
            b.translation='耳朵顶部较薄，向外逐渐变宽至圆润底部' if b.source==first else '耳朵底部与吻部底部对齐'
    def review(image,reading,*args):
        verified.extend(b.source for b in reading.blocks)
        return {'complete':True,'issues':[]}
    monkeypatch.setattr(g,'repair_reading',translate);monkeypatch.setattr(g,'review_semantics',review)
    units=pipeline.translate_units(readings,pages,{'translation_engine':'online'},pipeline.Context(),lambda:False,
        lambda *args:None,[{'calls':[]} for _ in pages])
    assert len(units)==2 and translated.count(first)==1 and verified.count(first)==1
    assert readings[0].blocks[0].translation==readings[1].blocks[0].translation
    assert readings[2].blocks[0].translation=='耳朵顶部较薄，向外逐渐变宽至圆润底部'
    assert '吻部' not in readings[2].blocks[0].translation


def test_formal_table_notation_and_descriptive_product_names_have_distinct_outputs():
    context=pipeline.Context(entities=[pipeline.Entity(source='Maj',kind='code'),
        pipeline.Entity(source='Chocolate Digestives',kind='product',translation='巧克力消化饼（Chocolate Digestives）')])
    notation=block('Maj');pipeline._entity_setup(notation,context)
    product=block('Chocolate Digestives');pipeline._entity_setup(product,context)
    ordinary=block('COLLAR',kind='code');pipeline._entity_setup(ordinary,context)
    assert g.retained(notation) and notation.translation=='Maj'
    assert not g.retained(product) and '巧克力消化饼' in product.translation
    assert not g.retained(ordinary)


def test_semantic_edit_cannot_replace_a_correct_fraction_with_a_changed_value(monkeypatch):
    reading=g.ReadingPage(complete=True,blocks=[block('Seam allowance 3/16',translation='缝份 3/16')])
    monkeypatch.setattr(g,'request_json',lambda *args:{'complete':True,'issues':[
        {'id':'b1','translation':'缝份 31/6','uncertain':False,'note':'校对'}]})
    g.review_semantics(Image.new('RGB',(10,10)),reading,{},lambda:False,[])
    assert reading.blocks[0].translation=='缝份 3/16' and reading.blocks[0].uncertain


def test_does_not_treat_descriptions_of_names_or_markings_as_opaque_codes():
    context=pipeline.Context(entities=[
        pipeline.Entity(source='NorthPoint Design Team',kind='brand'),
        pipeline.Entity(source='Chest "Comfort"',kind='code',translation='胸前“Comfort”字样'),
        pipeline.Entity(source='Young Dogs',kind='product',translation='幼犬（Young Dogs）'),
    ])
    context.entities=pipeline.normalize_entities(context,'northpoint design team; chest "comfort"; young dogs')
    heading=block('NorthPoint Design Team',kind='brand');pipeline._entity_setup(heading,context)
    marking=block('Chest "Comfort"',kind='code');pipeline._entity_setup(marking,context)
    product=block('Style Name: Young Dogs',translation='款名：Young Dogs')
    pipeline._entity_setup(product,context);pipeline.expand_product_field(product,context,'en_to_zh')
    assert heading.preserved_terms==['NorthPoint'] and not g.retained(heading)
    assert marking.preserved_terms==['Comfort'] and marking.translation=='胸前“Comfort”字样'
    assert product.translation=='款名：幼犬（Young Dogs）'


def test_only_the_duplicated_appended_clause_is_removed():
    current=block('Eyes have the same line weight throughout',translation='眼睛的线条粗细始终一致——末端圆润，且略带弧度')
    following=block('rounded at the ends and slightly curved',translation='两端呈圆形并略带弧度')
    pipeline.remove_repeated_clause(current,following,'en_to_zh')
    assert current.translation=='眼睛的线条粗细始终一致'
    current=block('Eyes have the same line weight throughout — 3 mm',translation='眼睛的线条粗细始终一致——末端圆润 3 mm')
    pipeline.remove_repeated_clause(current,following,'en_to_zh')
    assert current.translation.endswith('3 mm')


def test_only_a_measured_wrapped_line_inside_same_table_cell_is_joined():
    def cell(id,text,group,bbox):
        return g.ReadingBlock(id=id,source=text,kind='table-cell',group=group,bbox=bbox,line_boxes=[bbox])
    reading=g.ReadingPage(complete=True,blocks=[
        cell('1','Chocolate','row:s1/column:style',[90,100,260,125]),
        cell('2','Digestives','row:s1/column:style',[80,123,270,149]),
        cell('3','Scottish','row:s2/column:style',[90,151,260,176]),
    ])
    with Image.new('RGB',(200,200),'white') as image:g.merge_wrapped_cells(reading,image)
    assert [b.source for b in reading.blocks]==['Chocolate Digestives','Scottish']
    assert reading.blocks[0].bbox==[80,100,270,149]


def test_repeated_original_is_not_removed_when_it_contains_a_required_name():
    assert g.remove_redundant_source('RIGHT SLEEVE','右袖（RIGHT）','en_to_zh')=='右袖'
    assert g.remove_redundant_source('Right sleeve AB123','右袖（AB123）','en_to_zh')=='右袖（AB123）'
    assert g.remove_redundant_source('Comfort label','标记（Comfort label）','en_to_zh',['Comfort'])=='标记（Comfort label）'


def test_paired_captions_keep_their_physical_column_in_the_complete_translation():
    def label(id,text,bbox):
        return g.ReadingBlock(id=id,source=text,translation='图注',kind='caption',
            group='swatches',bbox=bbox,line_boxes=[bbox])
    reading=g.ReadingPage(complete=True,blocks=[
        label('a','First sample',[30,40,110,60]),
        label('b','Second sample',[240,40,320,60]),
        label('c','Cotton fabric',[31,63,132,83]),
        label('d','Linen fabric',[242,63,337,83]),
    ])
    with Image.new('RGB',(1000,1000),'white') as image:
        regions=g.build_regions(reading,[],image,{'translation_engine':'online'})
        assert [r['reviewNotes'][-1][-2:] for r in regions]==['左列','右列','左列','右列']
        reading.blocks[-1].bbox=[242,110,337,130]
        assert not g.paired_column_notes(reading,image)


def test_inconsistent_shape_is_sent_for_review_before_painting():
    source='The panel is narrower at the top and tapers outward to a round base'
    wrong='裁片顶部较窄，向外逐渐变细，底部为圆形'
    correct='裁片顶部较窄，向外逐渐加宽至圆形底部'
    assert any('形状方向' in problem for problem in g.translation_problems(source,wrong,'en_to_zh'))
    assert not g.translation_problems(source,correct,'en_to_zh')


def test_incomplete_semantic_batch_rechecks_its_two_halves_only(tmp_path,monkeypatch):
    path=tmp_path/'page.png';Image.new('RGB',(100,100),'white').save(path)
    reading=g.ReadingPage(complete=True,blocks=[g.ReadingBlock(id=f'p{i}',source=s,
        translation='',bbox=[10,10,500,200]) for i,s in enumerate(('Floor','Wall','Ceiling','Stairs'))])
    monkeypatch.setattr(g,'repair_reading',lambda batch,*a:[setattr(b,'translation','构件') for b in batch.blocks])
    sizes=[]
    def audit(image,batch,*args):
        sizes.append(len(batch.blocks))
        return {'complete':len(batch.blocks)==2,'issues':[]}
    monkeypatch.setattr(g,'review_semantics',audit)
    pipeline.translate_units([reading],[{'input':str(path)}],{'translation_engine':'online'},
        pipeline.Context(),lambda:False,lambda *a:None,[{'calls':[]}])
    assert sizes==[4,2,2]
    assert reading.complete and all(not b.uncertain for b in reading.blocks)
