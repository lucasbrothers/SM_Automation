"""Stage reviewed SERVER package files on an SSH CLIENT without repository downloads."""
import hashlib
import os
import re
import shlex
import stat
from contextlib import contextmanager
from pathlib import Path

from engine.remote import capture, privileged
from patch.manager import package_manager, execute


def validate_files(files):
    if not isinstance(files, list) or not 1 <= len(files) <= 50:
        raise ValueError('Choose 1–50 SERVER package files')
    if any(not isinstance(p, str) or not p.startswith('/') or '\x00' in p or Path(p).suffix not in {'.deb', '.rpm'} for p in files):
        raise ValueError('Use absolute Linux SERVER .deb / .rpm paths')
    return list(dict.fromkeys(files))


def run(client, command, mode, timeout=180):
    result = capture(client, privileged('set -eu; export LC_ALL=C; ' + command, mode), timeout=timeout, max_bytes=4*1024*1024)
    if result.exit_code:
        raise RuntimeError(result.stderr.strip() or result.stdout.decode(errors='replace') or 'Package operation failed')
    return result.stdout.decode(errors='replace')


@contextmanager
def staged(client, files, mode, expected=None):
    validate_files(files)
    if client._client is None:
        client.connect()
    temporary = client.execute('umask 077; mktemp -d /tmp/sm-patch-upload-XXXXXXXXXXXX').strip()
    if not re.fullmatch('/tmp/sm-patch-upload-[A-Za-z0-9]+', temporary):
        raise ValueError('Invalid staging directory')
    root = None
    try:
        records = []
        root = run(client, 'umask 077; mktemp -d /var/tmp/sm-patch-root-XXXXXXXXXXXX', mode).strip()
        if not re.fullmatch('/var/tmp/sm-patch-root-[A-Za-z0-9]+', root):
            raise ValueError('Invalid privileged staging directory')
        run(client, 'mkdir -p ' + shlex.quote(root+'/lists/partial'), mode)
        with client._client.open_sftp() as sftp:
            sftp.get_channel().settimeout(client.timeout)
            for index, path in enumerate(files):
                suffix = Path(path).suffix
                destination = f'{root}/package-{index}{suffix}'
                upload = f'{temporary}/package-{index}{suffix}'
                digest = hashlib.sha256()
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, 'rb') as source, sftp.open(upload, 'wx') as output:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        raise ValueError('Package source must be a regular file')
                    while block := source.read(1024*1024):
                        digest.update(block); output.write(block)
                record = {'path': path, 'sha256': digest.hexdigest()}
                if expected is not None and (index >= len(expected) or record != expected[index]):
                    raise ValueError('Package file changed since planning')
                records.append(record)
                run(client, 'cp -- ' + shlex.quote(upload) + ' ' + shlex.quote(destination) + '; chmod 600 ' + shlex.quote(destination) + '; echo ' + shlex.quote(digest.hexdigest() + '  ' + destination) + ' | sha256sum -c -', mode)
        if expected is not None and len(records) != len(expected):
            raise ValueError('Package selection changed')
        yield root, records
    finally:
        if root and re.fullmatch('/var/tmp/sm-patch-root-[A-Za-z0-9]+', root):
            run(client, 'rm -rf -- ' + shlex.quote(root), mode)
        client.execute('rm -rf -- ' + shlex.quote(temporary))


def resolve(client, files, root, mode, manager):
    paths = [f'{root}/package-{i}{Path(p).suffix}' for i,p in enumerate(files)]
    args = ' '.join(map(shlex.quote, paths))
    if manager == 'apt':
        output = execute(client, apt_command(root, args, True), mode)
        if any(line.startswith('Remv ') for line in output.splitlines()):
            raise ValueError('Package removals are not supported')
        # APT may allow explicit local downgrades during simulation; reject each one.
        for line in output.splitlines():
            match = re.match(r'Inst (\S+) \[([^]]+)\] \((\S+)', line)
            if match:
                _, installed, candidate = match.groups()
                execute(client, 'dpkg --compare-versions ' + shlex.quote(candidate) + ' ge ' + shlex.quote(installed) + " || { echo 'Package downgrades are not supported' >&2; exit 1; }", mode)
        state = execute(client, "dpkg-query -W -f='${Package} ${Architecture} ${Version} ${db:Status-Abbrev}\\n' | sort | sha256sum", mode).strip()
    else:
        # Native RPM verifies dependencies and rejects older versions. No repository access.
        for path in paths:
            signature = run(client, 'rpmkeys --checksig ' + shlex.quote(path), mode)
            if 'signatures OK' not in signature:
                raise ValueError('RPM must have a trusted package signature')
        output = run(client, 'rpm -U --test ' + args, mode)
        state = run(client, "rpm -qa --qf '%{NAME} %{ARCH} %{EPOCHNUM}:%{VERSION}-%{RELEASE}\\n' | sort | sha256sum", mode).strip()
    # Staging names vary per invocation; keep the preview comparable.
    return output.replace(root, '<staged>'), state, args


def apt_command(root, args, simulate):
    # Isolate APT from every repository and its metadata. Local DEBs still need
    # APT's file acquisition step, so --no-download cannot be used here.
    return ('apt-get ' + ('-s ' if simulate else '-y ') +
            '--no-remove -o Dpkg::Options::=--force-confold '
            '-o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=- '
            '-o Dir::State::lists=' + shlex.quote(root+'/lists') + ' install ' + args)


def make_plan(client, files, mode):
    manager = package_manager(client)
    suffix = '.deb' if manager == 'apt' else '.rpm'
    if any(Path(p).suffix != suffix for p in files):
        raise ValueError('Package file format does not match the CLIENT OS')
    with staged(client, files, mode) as (root, records):
        output, state, _ = resolve(client, files, root, mode, manager)
    return {'action':'plan', 'manager':manager, 'files':records, 'package_state':state,
            'output':output, 'packages':[], 'apply_supported':True,
            'note':'Local files only; dependencies must already exist or be included. No install during preview. DEB source trust must be checked by the administrator; SHA256 pins reviewed bytes.'}


def apply_plan(client, plan, mode):
    manager = package_manager(client)
    if manager != plan['manager']:
        raise ValueError('Package manager changed')
    files = [r['path'] for r in plan['files']]
    with staged(client, files, mode, plan['files']) as (root, _):
        preview, state, args = resolve(client, files, root, mode, manager)
        if state != plan['package_state'] or preview != plan['output']:
            raise ValueError('Package state or dependencies changed; create a fresh plan')
        command = ('export DEBIAN_FRONTEND=noninteractive; ' + apt_command(root,args,False) if manager == 'apt' else 'rpm -U ' + args)
        output = run(client, command, mode, timeout=900)
    return {'action':'apply', 'manager':manager, 'files':plan['files'], 'output':output,
            'reboot_required':None, 'note':'Local packages applied; no automatic reboot. Check services and reboot requirements.'}
