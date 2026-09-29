"""Local file benchmark; fixtures are supplied explicitly and never committed."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.document_tools.image_translation import convert_image_translation
from app.services.document_tools import image_translation as image_engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--pages', default='all')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original_run = image_engine.run_node
    def capture_layout(pages, options, work, progress, cancelled):
        records = original_run(pages,options,work,progress,cancelled)
        (work/'layout-records.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
        return records
    image_engine.run_node = capture_layout
    args.output.mkdir(parents=True, exist_ok=True)
    for name, source in [('image',args.image), ('pdf',args.pdf)]:
        if source is None:
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        started = time.monotonic()
        try:
            result = convert_image_translation(source, {'translation_direction':'en_to_zh', 'translation_engine':'offline', 'page_selection':args.pages},
                args.output / name, lambda *a: print(name, *a, flush=True), lambda:False)
            report = result.ir.model_dump(mode='json')
            report['summary'] = result.summary
        except Exception as exc:
            report = {'error':str(exc), 'error_type':type(exc).__name__}
        report['elapsed_seconds'] = time.monotonic()-started
        report['original_sha256'] = digest
        report['original_unchanged'] = digest == hashlib.sha256(source.read_bytes()).hexdigest()
        (args.output / f'{name}-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name, 'DONE', report.get('error','ok'), flush=True)
        if 'error' in report:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
