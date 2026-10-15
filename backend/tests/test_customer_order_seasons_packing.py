"""SEASONS outer-pack evidence; inner packs must never become carton packs."""
import pytest

from app.services.huaxing_order_legacy import shixin_schedule as parser


@pytest.mark.parametrize('text,expected', [
    ('-12 PCS PER INNER;\nPacking: Inner: 12PCS Outer Type: CARTON Outer: 288P', '288'),
    ('Packing: Inner: 12PCS Outer: 288PC', '288'),
    ('Packing: Inner: 12PCS Outer: 288PCS', '288'),
    ('Outer Type: CTN QTY: 48PCS', '48'),
    ('OUTER QTY: 48 PCS', '48'),
    ('Outer: 1,440 PCS', '1440'),
    ('3. 12/288装，12个装一内箱', '288'),
    ('12／288裝，12個裝一內箱', '288'),
    ('12/288装\nOuter:288P', '288'),
    ('288 PCS PER OUTER CARTON\n12 PCS PER INNER', '288'),
    ('288 PCS PER MASTER CARTON\n12 PCS PER INNER', '288'),
    ('12 PCS PER CARTON', ''),
    ('Packing: Inner: 12 PCS PER CARTON Outer: 288PCS', '288'),
    ('Packing: Outer: 288PCS\nInner Carton: 12 PCS PER CARTON', '288'),
    ('12 PCS PER INNER\nInner: 12PCS', ''),
    ('3.1/2装，一套装个胶袋', ''),
    ('SHIPDATE:2026/12/18\nPRODUCT SIZE:3.875 X 0.625 INCH', ''),
    ('Outer: 288Pounds', ''),
    ('Outer: 28,8P', ''),
    ('Outer: 2.5PCS', ''),
    ('Outer: 0PCS', ''),
    ('Outer: 2PCS\n外箱贴纸：0/1装的号码才需要贴', '2'),
    ('外箱贴纸：0/1装的号码才需要贴', ''),
    ('外箱貼紙：0/1裝的號碼才需要貼', ''),
    ('Packing: Outer: 2PCS\n其他号码12/288装', '2'),
])
def test_supported_pack_tokens_and_no_inner_or_unrelated_number_fallback(text, expected):
    assert parser._packing_from_block(text)[0] == expected


@pytest.mark.parametrize('text', [
    '12/288装\nOuter:240PCS',
    'Outer: 288P\nOuter: 240PCS',
    'Outer:288PCS\n240PCS PER MASTER CARTON',
])
def test_conflicting_explicit_outer_packs_require_original_review(text):
    with pytest.raises(ValueError, match='外箱装箱数.*冲突'):
        parser._packing_from_block(text)


def test_packaging_description_is_preserved():
    pack, description = parser._packing_from_block('Packing: Inner: 12PCS Outer: 288P')
    assert pack == '288'
    assert description == 'Packing: Inner: 12PCS Outer: 288P'
