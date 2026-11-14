"""Preview shipping mail/document parsing locally. Reads files only; never writes a database.

Usage:
    python scripts/preview_shipping_mail.py <file> [<file> ...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.shipping_mail.pipeline import parse_shipping_document, parse_shipping_email  # noqa: E402


def main(paths: list[str]) -> int:
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            print(json.dumps({'file': raw_path, 'error': '文件不存在'}, ensure_ascii=False))
            continue
        data = path.read_bytes()
        if path.suffix.lower() == '.eml':
            result = parse_shipping_email(data, path.name)
            summary = {
                'file': path.name,
                'subject': result['subject'],
                'sender': result['sender'],
                'fields': result['fields'],
                'items': len(result['items']),
                'attachments': [
                    {'filename': item['filename'], 'kind': item['kind'], 'status': item['status']}
                    for item in result['attachments']
                ],
                'warnings': result['warnings'],
                'rules': [trace['rule_id'] for trace in result['rule_trace']],
            }
        else:
            result = parse_shipping_document(data, path.name)
            summary = {
                'file': path.name,
                'kind': result['kind'],
                'status': result['status'],
                'fields': result['fields'],
                'items': len(result['items']),
                'warnings': result['warnings'],
            }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
