"""Publishing a GUI upload must not expose incomplete files or overwrite targets."""
import base64
import sys
import uuid
import pytest
from server.files import gui_transfer
pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='Linux SERVER filesystem APIs')


def test_upload_publish_and_existing_file_preservation(tmp_path):
    stage=tmp_path/('.sm-upload-'+uuid.uuid4().hex);target=tmp_path/'complete.bin'
    gui_transfer('file.upload',{'path':str(stage),'offset':0,'content':base64.b64encode(b'first').decode()})
    assert not target.exists()
    with pytest.raises(ValueError,match='incomplete'):
        gui_transfer('file.commit',{'path':str(stage),'target':str(target),'size':999})
    gui_transfer('file.upload',{'path':str(stage),'offset':5,'content':base64.b64encode(b'second').decode(),'final':True})
    target.write_bytes(b'existing')
    with pytest.raises(FileExistsError):
        gui_transfer('file.commit',{'path':str(stage),'target':str(target),'size':11})
    assert target.read_bytes()==b'existing'
    target.unlink()
    gui_transfer('file.commit',{'path':str(stage),'target':str(target),'size':11})
    assert target.read_bytes()==b'firstsecond' and not stage.exists()


def test_abort_only_pending_upload_and_preserves_finished_file(tmp_path):
    finished=tmp_path/'complete.bin';finished.write_bytes(b'keep')
    with pytest.raises(ValueError):gui_transfer('file.abort',{'path':str(finished)})
    stage=tmp_path/('.sm-upload-'+uuid.uuid4().hex);stage.write_bytes(b'partial')
    gui_transfer('file.abort',{'path':str(stage)})
    assert not stage.exists() and finished.read_bytes()==b'keep'
