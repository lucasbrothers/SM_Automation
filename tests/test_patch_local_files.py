from contextlib import contextmanager
import sys
import pytest
from patch import local_files as local
from patch.manager import validate_options


@pytest.mark.parametrize('files', [[], ['/tmp/test.iso'], ['relative.deb'], ['/tmp/a.deb\x00'], 'a.deb'])
def test_invalid_paths(files):
    with pytest.raises(ValueError): local.validate_files(files)


def test_file_plan_options_and_duplicates():
    assert validate_options({'action':'plan','files':['/srv/a.deb','/srv/a.deb']}) == {'action':'plan','files':['/srv/a.deb'],'packages':[]}


def test_wrong_os_format_does_not_stage(monkeypatch):
    monkeypatch.setattr(local,'package_manager',lambda c:'apt')
    monkeypatch.setattr(local,'staged',lambda *a:pytest.fail('Must reject before staging'))
    with pytest.raises(ValueError,match='format'): local.make_plan(None,['/srv/a.rpm'],'direct')


def test_changed_state_cannot_install(monkeypatch):
    @contextmanager
    def staged(*a): yield '/var/tmp/root',[]
    monkeypatch.setattr(local,'staged',staged)
    monkeypatch.setattr(local,'package_manager',lambda c:'apt')
    monkeypatch.setattr(local,'resolve',lambda *a:('preview','changed','args'))
    monkeypatch.setattr(local,'run',lambda *a,**k:pytest.fail('Must not install'))
    with pytest.raises(ValueError,match='state'):
        local.apply_plan(None,{'manager':'apt','files':[{'path':'/a.deb','sha256':'x'}],'output':'preview','package_state':'old'},'sudo')


def test_unsigned_rpm_rejected(monkeypatch):
    monkeypatch.setattr(local,'run',lambda *a:'package: digests OK')
    with pytest.raises(ValueError,match='signature'):
        local.resolve(None,['/a.rpm'],'/var/tmp/root','sudo','dnf')


def test_apt_downgrade_is_checked(monkeypatch):
    commands=[]
    def execute(c,command,mode):
        commands.append(command)
        if command.startswith('apt-get'): return 'Inst demo [2.0] (1.0 local [amd64])'
        raise RuntimeError('downgrade')
    monkeypatch.setattr(local,'execute',execute)
    with pytest.raises(RuntimeError,match='downgrade'):
        local.resolve(None,['/a.deb'],'/var/tmp/root','direct','apt')
    assert 'dpkg --compare-versions 1.0 ge 2.0' in commands[-1]


def test_media_invalid_source_never_mounts(tmp_path,monkeypatch):
    from server import media
    monkeypatch.setattr(media,'ROOT',tmp_path/'mounts')
    monkeypatch.setattr(media.subprocess,'run',lambda *a,**k:pytest.fail('No mount'))
    with pytest.raises(ValueError):media.handle('media.mount',{'path':'/tmp/file.deb'})


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux SERVER no-follow file handling')
def test_media_rejects_symlink(tmp_path,monkeypatch):
    from server import media
    monkeypatch.setattr(media,'ROOT',tmp_path/'mounts')
    link=tmp_path/'a.iso';link.symlink_to(tmp_path/'missing')
    with pytest.raises(OSError):media.handle('media.mount',{'path':str(link)})


def test_media_unmounted_id_cannot_browse(tmp_path,monkeypatch):
    from server import media
    monkeypatch.setattr(media,'ROOT',tmp_path/'mounts')
    with pytest.raises(ValueError,match='not mounted'):
        media.handle('media.packages',{'id':'a'*32})


def test_media_requires_admin():
    from server.auth import authorize
    for role in ['operator','viewer']:
        with pytest.raises(ValueError,match='Permission denied'):
            authorize(role,'media.mount',{'path':'/tmp/file.iso'})


def test_gui_file_plan_and_edit_invalidates_review(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from desktop.main import Console
    app=QApplication.instance() or QApplication([])
    window=Console()
    monkeypatch.setattr(window,'has_readonly_account_patch_targets',lambda:False)
    submitted=[]
    monkeypatch.setattr(window,'start_job',lambda kind,options:submitted.append((kind,options)))
    window.patch_files.setText('/srv/a.deb | /srv/b.deb')
    window.plan_patches()
    assert submitted[0][1]['files']==['/srv/a.deb','/srv/b.deb']
    window.patch_plan_id='a'*32;window.patch_apply.setEnabled(True)
    window.patch_files.setText('/srv/other.deb')
    assert window.patch_plan_id is None and not window.patch_apply.isEnabled()
    window.close()


def test_apt_file_mode_disables_repositories():
    command=local.apt_command('/var/tmp/stage','/var/tmp/stage/a.deb',False)
    assert 'Dir::Etc::sourcelist=/dev/null' in command
    assert 'Dir::Etc::sourceparts=-' in command
    assert 'Dir::State::lists=/var/tmp/stage/lists' in command
    assert '--no-remove' in command
