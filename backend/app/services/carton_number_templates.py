"""Bounded number-segment templates, not user-supplied regular expressions."""
import re


def parse_template(template):
    if not template.strip() or len(template) > 256 or re.search(r"\s", template):
        raise ValueError("格式不能为空、不能有空格，且最多 256 字")
    tokens = []
    for part in filter(None, re.split(r"(\{[^{}]*\})", template)):
        if part.startswith("{"):
            if not re.fullmatch(r"\{[1-9][0-9]*(,[1-9][0-9]*)*\}", part):
                raise ValueError("数字段请写成 {9} 或 {3,4}")
            lengths = sorted(set(int(n) for n in part[1:-1].split(",")))
            if len(lengths) > 16 or any(n > 128 for n in lengths):
                raise ValueError("每段允许位数须在 1–128 之间，最多 16 种")
            tokens.append(lengths)
        else:
            if "{" in part or "}" in part:
                raise ValueError("格式的大括号不完整")
            tokens.append(part.upper())
    if len(tokens) > 32 or sum(len(t) if isinstance(t, str) else max(t) for t in tokens) > 128:
        raise ValueError("格式过长，编号最多 128 字")
    return tokens


def matches_template(template, value):
    try:
        tokens = parse_template(template)
    except ValueError:
        return False
    value = value.upper()
    positions = {0}
    for token in tokens:
        following = set()
        for at in positions:
            if isinstance(token, str):
                if value.startswith(token, at):
                    following.add(at + len(token))
            else:
                for length in token:
                    segment = value[at:at + length]
                    if len(segment) == length and re.fullmatch(r"[0-9]+", segment):
                        following.add(at + length)
        positions = following
    return len(value) in positions
