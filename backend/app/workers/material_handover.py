"""Private JSON IPC only; original uploads are never deserialized as executable objects."""
import json
import math
import os
import sys
import tempfile
import threading
import time
from pathlib import Path


def main():
    os.environ['DATABASE_URL'] = 'sqlite://'
    os.environ['SEED_DEFAULT_ACCOUNTS'] = 'false'
    os.environ['RR_CUSTOMER_ORDER_JOB_WORKER'] = '1'
    folder = Path(sys.argv[1])
    request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    printing = request.get('operation') == 'print'
    remaining = max(0, min(180, float(sys.argv[2]) - time.monotonic()))
    # The parent owns the print deadline/tree. Office waits stop early enough to
    # clean their isolated UNO processes before the parent's final hard cutoff.
    watchdog = threading.Timer(remaining + (10 if printing else 0), lambda: os._exit(124)); watchdog.daemon = True; watchdog.start()
    tempfile.tempdir = str(folder)
    for key in ('TMPDIR', 'TEMP', 'TMP'):
        os.environ[key] = str(folder)
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(remaining)), max(2, math.ceil(remaining) + 1)))
    from app.workers.customer_order_job import job_slot
    from app.services.material_handover_parser import parse
    from app.services.document_tools.document_ir import ToolError
    try:
        with job_slot(Path(sys.argv[3])):
            if printing:
                from app.services.material_handover_print import render
                output = render(request['name'], (folder / 'input.bin').read_bytes(), request['data'],
                    request['extraction'], request['code'], request['corner'], folder,
                    cancelled=lambda: time.monotonic() >= float(sys.argv[2])-45)
                (folder / 'output.pdf').write_bytes(output)
                result = {'value': {'prepared': True}}
            else:
                result = {'value': parse(request['name'], (folder / 'input.bin').read_bytes())}
    except ToolError as error:
        if error.code == 'LOCAL_OCR_UNAVAILABLE':
            from app.schemas.material_handover import HandoverData
            result = {'value': {'data': HandoverData().model_dump(mode='json'), 'warnings': [str(error)],
                'evidence': {}, 'raw_text': '', 'engine': 'manual-review-required'}}
        else:
            result = {'error': str(error), 'status': 503 if printing and error.code in ('OFFICE_UNAVAILABLE', 'UNO_UNAVAILABLE') else 422}
    except Exception:
        result = {'error': '无法准备原单打印，请检查文件打印区域、分页和字体' if printing else '无法完整读取单据，请检查文件是否损坏、加密或过于复杂', 'status': 422}
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
