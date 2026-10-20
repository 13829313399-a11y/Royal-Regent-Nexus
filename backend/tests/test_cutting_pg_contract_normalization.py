import runpy
from pathlib import Path
import pytest


normalize = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'alembic' / 'versions' / '20261017_0167_reconcile_cutting_jp_collision.py'))['_equivalent_pg_check']

def test_observed_array_deparsing_equivalence_preserves_all_values():
    a="action::text = ANY (ARRAY['save'::character varying::text, 'submit'::character varying::text])"
    b="action::text = ANY (ARRAY['save'::character varying, 'submit'::character varying]::text[])"
    assert normalize(a)==normalize(b)=="action::text = ANY (ARRAY['save'::text, 'submit'::text])"

@pytest.mark.parametrize('value',["action::text = ANY (ARRAY['a'::character varying(1), 'b'::character varying(1)]::text[])","action::text = ANY (ARRAY['a'::character varying, NULL]::text[])","action::text = ANY (ARRAY[source::character varying]::text[])","action::text = ANY (ARRAY['a'::character varying])","action::text = ANY (ARRAY['a'::character varying]::integer[])","action::text = 'a'::character varying::text"])

def test_unknown_or_non_equivalent_expressions_remain_exact(value):
    assert normalize(value) == value

def test_escaped_literal_values_and_order_are_preserved():
    a="action::text = ANY (ARRAY['a''b'::character varying, 'c'::character varying]::text[])"
    assert normalize(a)=="action::text = ANY (ARRAY['a''b'::text, 'c'::text])"
    assert normalize(a)!=normalize(a.replace("'c'","'d'"))
    assert normalize(a)!=normalize("action::text = ANY (ARRAY['c'::character varying, 'a''b'::character varying]::text[])")

def test_array_like_text_inside_a_literal_is_never_rewritten():
    value="description::text = 'action::text = ANY (ARRAY[''save''::character varying]::text[])'"
    assert normalize(value)==value

def test_embedded_cast_text_is_preserved_byte_for_byte():
    literal="'ARRAY[''save''::character varying]::text[]'"
    value="action::text = ANY (ARRAY["+literal+"::character varying]::text[])"
    assert normalize(value)=="action::text = ANY (ARRAY["+literal+"::text])"
