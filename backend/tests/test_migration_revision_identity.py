"""Every published migration must have an unambiguous graph identity."""
import ast
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_unique_revisions_and_jp_follows_both_cutting_and_carton_branches():
    backend = Path(__file__).resolve().parents[1]
    revisions = {}
    for path in (backend / 'alembic/versions').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id == 'revision' for t in targets):
                revision = ast.literal_eval(node.value)
                assert revision not in revisions, f'{revision}: {revisions.get(revision)} and {path.name}'
                revisions[revision] = path.name
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    graph = ScriptDirectory.from_config(config)
    assert graph.get_heads() == ['20261021_0172']
    assert set(graph.get_revision('20261021_0172').down_revision) == {'20261020_0171', '20261021_0169'}
    assert graph.get_revision('20261021_0169').down_revision == '20261019_0167'
    assert set(graph.get_revision('20261020_0171').down_revision) == {'20261019_0170', '20261020_0168'}
    assert set(graph.get_revision('20261020_0168').down_revision) == {'20261017_0167', '20261019_0167'}
    assert graph.get_revision('20261019_0167').down_revision == '20261016_0166'
    ancestry = {node.revision for node in graph.walk_revisions()}
    assert {'20261015_0163', '20261016_0163', '20261016_0165', '20261016_0166'} <= ancestry
    assert 'cutting_internal_periods' in revisions['20261015_0163']
