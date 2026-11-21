import asyncio
from collections import Counter
import importlib.util
from pathlib import Path
import sys
import typing

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))
from legacy_python import transform
from legacy_support import union, zip_compat, removeprefix, removesuffix, to_thread, flattened_data


def test_annotations_preserve_pydantic_and_sqlalchemy_shapes():
    source = '''from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel
class Row(BaseModel):
    value: Decimal | None = None
    names: list[str] = []
def result(values: list[dict[str, int | None]]) -> tuple[str, ...]:
    return tuple(str(v) for v in values)
'''
    module = type(sys)('legacy_test_annotations')
    sys.modules[module.__name__] = module
    try:
        exec(transform(source), module.__dict__)
        row = module.Row(value='1.25', names=['A'])
        assert str(row.value) == '1.25' and row.names == ['A']
        hints = typing.get_type_hints(module.result)
        assert hints['values'] == typing.List[typing.Dict[str, typing.Optional[int]]]
        assert hints['return'] == typing.Tuple[str, ...]
    finally:
        sys.modules.pop(module.__name__)


def test_dictionary_merge_does_not_change_counter_set_or_flags():
    left = {'a': 1, 'b': 2}
    assert union(left, {'a': 3}) == {'a': 3, 'b': 2}
    assert left == {'a': 1, 'b': 2}
    assert union(Counter(a=2), Counter(a=1, b=4)) == Counter(a=2, b=4)
    assert union({1}, {2}) == {1, 2}
    assert union(1, 2) == 3


def test_strict_zip_rejects_both_mismatches_and_keeps_normal_truncation():
    assert list(zip_compat([1, 2], ['a', 'b'], strict=True)) == [(1, 'a'), (2, 'b')]
    assert list(zip_compat([1], [2, 3])) == [(1, 2)]
    assert list(zip_compat(strict=True)) == []
    for values in (([1], [2, 3]), ([1, 2], [3])):
        with pytest.raises(ValueError):
            list(zip_compat(*values, strict=True))


def test_legacy_helpers_preserve_empty_suffix_pixels_and_request_context():
    from contextvars import ContextVar
    from PIL import Image
    assert removeprefix('abc', 'ab') == 'c' and removeprefix('abc', 'd') == 'abc'
    assert removesuffix('abc', '') == 'abc' and removesuffix('abc', 'bc') == 'a'
    image = Image.new('L', (2, 1)); image.putdata([1, 22])
    assert flattened_data(image) == [1, 22]
    value = ContextVar('budget', default=None)
    value.set('request-local')
    assert asyncio.run(to_thread(value.get)) == 'request-local'


def test_calls_keep_evaluation_and_type_runtime_import_order():
    source = '''"""Module documentation."""
from __future__ import annotations
from decimal import Decimal
class Item:
    value: Decimal | None
calls = []
def side(value):
    calls.append(value)
    return value
combined = side({'left': 1}) | side({'right': 2})
prefix = 'prefix/value'.removeprefix('prefix/')
'''
    scope = {}
    exec(transform(source), scope)
    assert scope['combined'] == {'left': 1, 'right': 2}
    assert scope['calls'] == [{'left': 1}, {'right': 2}]
    assert scope['prefix'] == 'value'
