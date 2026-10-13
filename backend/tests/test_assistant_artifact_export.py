"""CSV must preserve the same table cells users see, without exporting code."""
import csv
from io import StringIO
import pytest


def test_table_csv_preserves_escaped_pipes_quotes_and_formula_protection():
    from app.services.assistant.artifacts import render
    value, media = render('| 名称 | 描述 |\n| --- | :---: |\n| A | 左\\|右 |\n| B | =危险,"引号" |\n| C | 末尾\\\\ |\n', 'table', '表格', [], 'csv')
    rows = list(csv.reader(StringIO(value.lstrip('\ufeff'))))
    assert media == 'text/csv'
    assert rows[:4] == [['名称','描述'],['A','左|右'],['B', '\'=危险,"引号"'], ['C', '末尾\\']]


def test_table_csv_uses_only_real_table_blocks_and_keeps_empty_cells():
    from app.services.assistant.artifacts import render
    content = '普通说明 | 不是表格\n\n```txt\n| 假 | 表 |\n| --- | --- |\n| 不 | 导出 |\n```\n\n| 名称 | 描述 |\n| --- | --- |\n| A | |\n| B | 说明 | 多余列 |\n'
    value, _ = render(content, 'table', '表格', [], 'csv')
    rows = list(csv.reader(StringIO(value.lstrip('\ufeff'))))
    assert rows[:3] == [['名称','描述'],['A',''],['B','说明']]
    assert '不' not in value and '不是表格' not in value


def test_table_csv_rejects_content_without_a_table_instead_of_returning_empty_success():
    from app.services.assistant.artifacts import render
    from app.services.assistant.errors import AssistantError
    with pytest.raises(AssistantError) as error:
        render('普通说明 | 不是表格', 'table', '表格', [], 'csv')
    assert error.value.detail['code'] == 'format_unavailable'


def test_table_csv_accepts_short_separators_supported_by_the_message_renderer():
    from app.services.assistant.artifacts import table_rows
    assert table_rows('| A | B |\n| - | :-: |\n| x | y |') == [['A', 'B'], ['x', 'y']]
