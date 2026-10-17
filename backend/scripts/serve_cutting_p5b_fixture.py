"""Serve synthetic cutting/auth/warehouse APIs on a separate localhost port.

The business application database and its running services are never reused.
Bind the frontend to 127.0.0.2 to isolate cookies from the business 127.0.0.1.
This is not a production startup or full-application migration rehearsal.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18000)
    args = parser.parse_args()
    if not 18000 <= args.port <= 18099:
        parser.error('Only isolated acceptance ports 18000–18099 are allowed')
    root = Path(__file__).resolve().parents[2]
    output = root/'.tmp'/'cutting-p5b-browser'/uuid4().hex
    output.mkdir(parents=True,exist_ok=False)
    os.environ.update(DATABASE_URL='sqlite://',SEED_DEFAULT_ACCOUNTS='false',PYTHONUTF8='1')
    sys.path[:0] = [str(root/'backend'),str(root/'backend/tests')]
    import pytest
    import uvicorn
    from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_order
    from verify_cutting_p5b import source_state
    with pytest.MonkeyPatch.context() as patch:
        base = client.__wrapped__(output,patch)
        p = next(base)
        source = flow.__wrapped__(p)
        next(source)
        try:
            role_flow.__wrapped__(p,patch)
            prepare_order(p)
            manifest = {'created_at':datetime.now(timezone.utc).isoformat(),'source':source_state(),
                'database':str(output/'cutting.db'),'port':args.port,'identity':'v2',
                'scope':'synthetic auth/cutting/warehouse API; sales dispatch is fixture setup',
                'business_data_used':False,'formal_acceptance':'pending'}
            (output/'fixture.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'fixture':str(output),'port':args.port}),flush=True)
            uvicorn.run(p.app,host='127.0.0.1',port=args.port)
        finally:
            source.close()
            base.close()


if __name__ == '__main__':
    main()
