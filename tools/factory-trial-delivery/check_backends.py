"""Run standalone suites in separate processes so their app modules cannot mix."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def run(arguments, environment):
    subprocess.run([sys.executable, '-B', *arguments], cwd=ROOT, env=environment, check=True)


if __name__ == '__main__':
    environment = os.environ.copy()
    environment.pop('PYTHONPATH', None)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    with tempfile.TemporaryDirectory(prefix='order-trial-check-') as temporary:
        backend = str(Path(temporary) / 'backend')
        run(['tools/customer-order-trial/prepare_backend.py', backend], environment)
        run(['-m', 'pytest', '-q', 'tools/customer-order-trial/tests'], {**environment, 'PYTHONPATH': backend})
        run(['-m', 'pytest', '-q', 'tools/huakang-b-jp-trial/tests'], environment)
        run(['-m', 'pytest', '-q', 'tools/factory-trial-delivery/tests'], environment)
