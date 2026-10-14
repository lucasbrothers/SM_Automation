import sys
import pytest
from desktop.transfers import Transfers
from server.files import gui_transfer
pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='Linux filesystem integration')

class Client:
    def call(self,method,**params):
        try:return gui_transfer(method,params)
        except Exception as exc:raise RuntimeError(str(exc)) from exc


def test_recursive_upload_pause_restart_resume_download(tmp_path):
    source=tmp_path/'local'/'folder';source.mkdir(parents=True)
    (source/'nested').mkdir();(source/'empty').mkdir()
    (source/'zero').write_bytes(b'');(source/'nested'/'large').write_bytes(b'abcd'*800000)
    remote=tmp_path/'remote';remote.mkdir();download=tmp_path/'download';download.mkdir()
    state=tmp_path/'state.json';client=Client();paused=[]
    payload={'side':'local','files':[{'path':str(source),'directory':True}]}
    runner=Transfers(client,state)
    result=runner.run(payload,str(source.parent),str(remote),lambda text:paused.append(True),lambda:'pause' if paused else '')
    assert 'paused' in result and not (remote/'folder'/'nested'/'large').exists()
    runner=Transfers(client,state)
    result=runner.run(None,'','',lambda text:None,lambda:'',resume=True)
    assert ': Success' in result
    assert (remote/'folder'/'nested'/'large').read_bytes()==(source/'nested'/'large').read_bytes()
    assert (remote/'folder'/'empty').is_dir() and (remote/'folder'/'zero').read_bytes()==b''
    result=runner.run({'side':'remote','files':[{'path':str(remote/'folder'),'directory':True}]},str(download),str(remote),lambda text:None,lambda:'')
    assert ': Success' in result and (download/'folder'/'nested'/'large').read_bytes()==(source/'nested'/'large').read_bytes()


def test_changed_source_rejected_after_pause(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'x'*2000000);remote=tmp_path/'remote';remote.mkdir()
    runner=Transfers(Client(),tmp_path/'state');paused=[]
    runner.run({'side':'local','files':[{'path':str(source)}]},str(tmp_path),str(remote),lambda text:paused.append(True),lambda:'pause' if paused else '')
    source.write_bytes(b'y'*2000000)
    assert 'Original file changed' in runner.run(None,'','',lambda text:None,lambda:'',resume=True)
    runner.discard();assert not list(remote.iterdir())


def test_deleted_source_in_folder_does_not_report_complete(tmp_path):
    source=tmp_path/'folder';source.mkdir();item=source/'file';item.write_bytes(b'x'*2000000)
    remote=tmp_path/'remote';remote.mkdir();paused=[];runner=Transfers(Client(),tmp_path/'state')
    runner.run({'side':'local','files':[{'path':str(source)}]},str(tmp_path),str(remote),lambda text:paused.append(True),lambda:'pause' if paused else '')
    item.unlink()
    assert 'source files are missing' in runner.run(None,'','',lambda text:None,lambda:'',True)
    assert runner.state.get('job')
    runner.discard()
