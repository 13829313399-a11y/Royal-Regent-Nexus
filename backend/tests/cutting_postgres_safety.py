"""Reject non-dedicated database names before constructing a test engine."""
from sqlalchemy.engine import make_url


def dedicated_postgres_url(value):
    url = make_url(value)
    name = url.database or ''
    if url.query or url.get_backend_name() != 'postgresql' or not (name == 'cutting_test' or name.startswith('cutting_test_')):
        raise ValueError('只允许专用 cutting_test 或 cutting_test_ 开头的 PostgreSQL 测试库')
    return url
