"""An evidence-reader sharing race must never disable controlled shutdown."""
from pathlib import Path
from types import SimpleNamespace
import json,sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cutting_probe_io as io


def test_replace_sharing_failure_preserves_last_good_then_recovers(tmp_path,monkeypatch):
    path=tmp_path/'diagnostics.partial.json';assert io.write_snapshot(path,{'version':1})
    replace=Path.replace
    def blocked(self,target):raise PermissionError('injected Windows sharing denial')
    monkeypatch.setattr(Path,'replace',blocked)
    assert io.write_snapshot(path,{'version':2}) is False
    assert json.loads(path.read_text())=={'version':1}
    assert json.loads(path.with_name(path.name+'.pending').read_text())=={'version':2}
    monkeypatch.setattr(Path,'replace',replace)
    assert io.write_snapshot(path,{'version':3})
    assert json.loads(path.read_text())=={'version':3}


def test_stop_remains_available_after_failed_capture(tmp_path,monkeypatch):
    monkeypatch.setattr(io,'write_snapshot',lambda *args:False)
    diagnostic=SimpleNamespace(snapshot=lambda:{'requests':[]})
    assert io.control_tick(tmp_path,diagnostic,0,10)==(False,10,True)
    (tmp_path/'stop').touch()
    diagnostic.snapshot=lambda:(_ for _ in ()).throw(AssertionError('Capture ran during stop'))
    assert io.control_tick(tmp_path,diagnostic,10,20)==(True,10,False)


def test_serialization_and_disk_errors_are_not_mislabeled_as_sharing(tmp_path,monkeypatch):
    with pytest.raises(TypeError):io.write_snapshot(tmp_path/'bad.json',object())
    monkeypatch.setattr(Path,'write_text',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError,match='disk full'):io.write_snapshot(tmp_path/'bad.json',{})


def test_reduced_checkpoint_frequency_still_prioritizes_stop(tmp_path,monkeypatch):
    written=[];monkeypatch.setattr(io,'write_snapshot',lambda *args:written.append(True) or True)
    diagnostic=SimpleNamespace(snapshot=lambda:{})
    assert io.control_tick(tmp_path,diagnostic,0,10,interval=30)==(False,0,False)
    assert not written
    assert io.control_tick(tmp_path,diagnostic,0,30,interval=30)==(False,30,False)
    assert len(written)==1
    (tmp_path/'stop').touch()
    assert io.control_tick(tmp_path,diagnostic,30,31,interval=30)==(True,30,False)
    assert len(written)==1


@pytest.mark.skipif(sys.platform!='win32',reason='Native Windows sharing contract')
@pytest.mark.parametrize('filename',['diagnostics.partial.json','progress.json'])
def test_native_windows_open_reader_does_not_lose_last_good_evidence(tmp_path,filename):
    path=tmp_path/filename;io.write_snapshot(path,{'version':1})
    with path.open('rb') as reader:
        assert not io.write_snapshot(path,{'version':2})
        assert json.load(reader)=={'version':1}
    assert io.write_snapshot(path,{'version':3})
    assert json.loads(path.read_text())=={'version':3}
