"""Completion checks must not reap the leader before descendant cleanup."""
import os
import subprocess
import sys
import time
from types import SimpleNamespace
import errno

import pytest
from app.services import customer_order_ocr as ocr


@pytest.mark.skipif(os.name == 'nt', reason='POSIX reserved leader regression')
def test_completion_observation_keeps_exited_child_unreaped():
    child = subprocess.Popen([sys.executable, '-c', 'pass'], start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        while not ocr._worker_exited(child):
            assert time.monotonic() < deadline
            time.sleep(.02)
        assert child.returncode is None
        # Darwin getpgid no longer sees zombies. wait() must still retrieve the
        # child's status, proving observation did not consume it.
        assert child.wait(timeout=1) == 0
    finally:
        ocr._stop_process_tree(child)
    assert child.returncode == 0


@pytest.mark.skipif(os.name == 'nt', reason='POSIX owned group regression')
def test_successful_leader_exit_still_stops_its_living_descendant(tmp_path):
    from test_customer_order_ocr_limits import _alive
    pidfile = tmp_path / 'child.pid'
    code = ('import subprocess,sys;from pathlib import Path;'
            'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);'
            'Path(sys.argv[1]).write_text(str(p.pid))')
    assert ocr._run_worker([sys.executable, '-c', code, str(pidfile)], ocr.OcrBudget()) == 0
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 3
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(.02)
    assert not _alive(pid)


def test_linux_waitid_keeps_wnowait_flag(monkeypatch):
    monkeypatch.setattr(os, 'waitid', lambda kind, pid, flags: seen.append((kind, pid, flags)) or object(), raising=False)
    for name, value in [('P_PID', 1), ('WEXITED', 4), ('WNOHANG', 1), ('WNOWAIT', 0x1000000)]:
        monkeypatch.setattr(os, name, value, raising=False)
    seen = []
    class Child:
        pid = 123
        def poll(self): raise AssertionError('Must not reap before cleanup')
    assert ocr._worker_exited(Child())
    assert seen == [(os.P_PID, 123, os.WEXITED | os.WNOHANG | os.WNOWAIT)]


def test_reaped_pid_is_never_signalled(monkeypatch):
    def unexpected(*args): raise AssertionError('A reaped PID must not be killed')
    monkeypatch.setattr(os, 'kill', unexpected)
    if hasattr(os, 'killpg'):
        monkeypatch.setattr(os, 'killpg', unexpected)
    ocr._stop_process_tree(SimpleNamespace(pid=123, returncode=0))


@pytest.mark.parametrize('error', [errno.ESRCH, errno.EPERM])
def test_kqueue_registration_error_is_not_mistaken_for_completion(monkeypatch, error):
    monkeypatch.delattr(os, 'waitid', raising=False)
    for name, value in [('KQ_FILTER_PROC', -5), ('KQ_EV_ADD', 1), ('KQ_NOTE_EXIT', 0x80000000), ('KQ_EV_ERROR', 0x4000)]:
        monkeypatch.setattr(ocr.select, name, value, raising=False)
    class Queue:
        def control(self, *args):
            return [SimpleNamespace(flags=0x4000, data=error, fflags=0)]
        def close(self): pass
    monkeypatch.setattr(ocr.select, 'kqueue', Queue, raising=False)
    monkeypatch.setattr(ocr.select, 'kevent', lambda *args, **kwargs: None, raising=False)
    if error == errno.ESRCH:
        assert ocr._worker_exited(SimpleNamespace(pid=123))
    else:
        with pytest.raises(OSError) as exc:
            ocr._worker_exited(SimpleNamespace(pid=123))
        assert exc.value.errno == errno.EPERM
