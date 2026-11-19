"""Deterministic Python 3.8 build adapter; production source files stay unchanged.

Only annotations and explicit standard-library compatibility operations change.
Every source and transformed file hash is retained in the package manifest.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import shutil


class LegacyPython(ast.NodeTransformer):
    def __init__(self):
        self.annotation = 0

    def hint(self, node):
        if node is None:
            return None
        self.annotation += 1
        try:
            return self.visit(node)
        finally:
            self.annotation -= 1

    def visit_arg(self, node):
        node.annotation = self.hint(node.annotation)
        return node

    def visit_AnnAssign(self, node):
        node.annotation = self.hint(node.annotation)
        node.target = self.visit(node.target)
        node.value = self.visit(node.value) if node.value else None
        return node

    def visit_FunctionDef(self, node):
        node.returns = self.hint(node.returns)
        # generic_visit would process the already transformed return twice.
        result = node.returns
        node.returns = None
        self.generic_visit(node)
        node.returns = result
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Subscript(self, node):
        node = self.generic_visit(node)
        names = {'list': 'List', 'dict': 'Dict', 'tuple': 'Tuple', 'set': 'Set',
                 'frozenset': 'FrozenSet', 'type': 'Type'}
        if isinstance(node.value, ast.Name) and node.value.id in names:
            node.value = ast.Attribute(ast.Name('_legacy_typing', ast.Load()), names[node.value.id], ast.Load())
        return node

    def visit_BinOp(self, node):
        node = self.generic_visit(node)
        if not isinstance(node.op, ast.BitOr):
            return node
        if self.annotation:
            return ast.Subscript(ast.Attribute(ast.Name('_legacy_typing', ast.Load()), 'Union', ast.Load()),
                                 ast.Tuple([node.left, node.right], ast.Load()), ast.Load())
        return ast.Call(ast.Attribute(ast.Name('_legacy_support', ast.Load()), 'union', ast.Load()),
                        [node.left, node.right], [])

    def visit_Call(self, node):
        node = self.generic_visit(node)
        operation = None
        if isinstance(node.func, ast.Name) and node.func.id == 'zip' and any(k.arg == 'strict' for k in node.keywords):
            operation = 'zip_compat'
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in {'removeprefix', 'removesuffix', 'get_flattened_data'}:
                operation = {'get_flattened_data': 'flattened_data'}.get(node.func.attr, node.func.attr)
                node.args.insert(0, node.func.value)
            elif ast.unparse(node.func) == 'asyncio.to_thread':
                operation = 'to_thread'
        if operation:
            node.func = ast.Attribute(ast.Name('_legacy_support', ast.Load()), operation, ast.Load())
        return node

    def visit_ImportFrom(self, node):
        if node.module == 'zoneinfo':
            node.module = 'backports.zoneinfo'
        return node


def transform(source: str) -> str:
    tree = LegacyPython().visit(ast.parse(source))
    # Imports after module docstring and __future__ imports, before annotations.
    position = 0
    for index, statement in enumerate(tree.body):
        if ((index == 0 and isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
             and isinstance(statement.value.value, str)) or
                (isinstance(statement, ast.ImportFrom) and statement.module == '__future__')):
            position = index + 1
        else:
            break
    tree.body[position:position] = ast.parse('import typing as _legacy_typing\nimport legacy_support as _legacy_support').body
    output = ast.unparse(ast.fix_missing_locations(tree)) + '\n'
    ast.parse(output, feature_version=(3, 8))
    return output


def prepare(backend: Path):
    records = []
    for file in sorted(backend.rglob('*.py')):
        original = file.read_bytes()
        output = transform(original.decode('utf-8')).encode('utf-8')
        file.write_bytes(output)
        records.append({'path': file.relative_to(backend).as_posix(),
                        'source_sha256': sha256(original).hexdigest(), 'sha256': sha256(output).hexdigest()})
    shutil.copyfile(Path(__file__).with_name('legacy_support.py'), backend / 'legacy_support.py')
    manifest_path = backend / 'source-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    hashes = {item['path']: item for item in records}
    for entry in manifest['files']:
        if entry['target'] in hashes:
            record = hashes[entry['target']]
            if entry['target_sha256'] != record['source_sha256']:
                raise ValueError('Source changed before legacy adaptation: ' + entry['target'])
            entry['before_legacy_sha256'] = entry['target_sha256']
            entry['target_sha256'] = record['sha256']
            entry['legacy_adapter'] = 'Python 3.8 annotations and standard-library backports'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (backend / 'legacy-manifest.json').write_text(json.dumps({'files': records,
        'support_sha256': sha256((backend / 'legacy_support.py').read_bytes()).hexdigest()}, indent=2) + '\n')


if __name__ == '__main__':
    import sys
    prepare(Path(sys.argv[1]))
