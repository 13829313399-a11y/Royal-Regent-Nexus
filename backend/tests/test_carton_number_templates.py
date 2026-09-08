import pytest
from pydantic import ValidationError
from app.schemas.carton_master import NumberRule
from app.services.carton_number_templates import matches_template


@pytest.mark.parametrize('value,expected', [
    ('SC700149169/600', True), ('sc700143393/1600', True),
    ('SC700149169/60', False), ('SC700149169/60000', False),
    ('SC70014916/600', False), ('SX700149169/600', False),
    ('SC700149169/６００', False), ('SC700149169/600x', False),
])
def test_variable_suffix(value, expected):
    assert matches_template('SC{9}/{3,4}', value) is expected


@pytest.mark.parametrize('template', ['', 'A{0}', 'A{3-4}', 'A{3,}', 'A{3', 'A{129}', 'A{128}', '{1,128}{1}', 'A {3}'])
def test_reject_invalid_templates(template):
    with pytest.raises(ValidationError):
        NumberRule(templates=[template], frozen=True)


def test_discrete_widths_literals_and_snapshot_contract():
    assert not matches_template('SC{9}/{3,5}', 'SC700149169/1600')
    assert matches_template('A.{2}+{1}', 'A.12+3')
    assert not matches_template('A.{2}+{1}', 'Ax12+3')
    assert matches_template('{1,2}{1,2}', '123')
    with pytest.raises(ValidationError):
        NumberRule(templates=['{9}'])
    with pytest.raises(ValidationError):
        NumberRule(frozen=True)
    with pytest.raises(ValidationError):
        NumberRule(templates=['{9}'] * 21, frozen=True)
