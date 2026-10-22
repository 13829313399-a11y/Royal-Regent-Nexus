"""Private stdin/stdout renderer. No application startup, credentials or DB access."""
import json
import sys
from types import SimpleNamespace

from fastapi import HTTPException
from cutting_export_workbook import package, render_workbook


def main():
    value = json.loads(sys.stdin.buffer.read())
    try:
        content, extension = package(value['report'], SimpleNamespace(**value['actor']),
            lambda report, user: render_workbook(report, user, value['title']))
        header = dict(extension=extension)
    except HTTPException as error:
        content = b''
        header = dict(status=error.status_code, error=error.detail)
    sys.stdout.buffer.write(json.dumps(header, ensure_ascii=False).encode('utf-8') + b'\n' + content)


if __name__ == '__main__':
    main()
