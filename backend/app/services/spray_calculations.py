"""Non-executing arithmetic family for legacy evidence, never a pay-policy DSL."""
import ast
from decimal import Decimal, localcontext


def arithmetic(formula: str, values: dict[str, Decimal]) -> Decimal:
    if len(formula) > 2048:
        raise ValueError("公式过长")
    tree = ast.parse(formula.lstrip("=").replace("$", ""), mode="eval")
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Decimal(ast.get_source_segment(formula.lstrip("=").replace("$", ""), node))
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -visit(node.operand) if isinstance(node.op, ast.USub) else visit(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
        raise ValueError("仅复算已识别的四则算术；未知函数或外链保留待核")
    with localcontext() as context:
        context.prec = 40
        return visit(tree)


def complete_sets(parts):
    if not parts:
        return 0
    return min(int(Decimal(qty) // Decimal(per_set)) for qty, per_set in parts)
