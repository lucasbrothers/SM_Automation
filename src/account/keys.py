"""Validated public keys and descriptor-based Linux authorized_keys updates."""
import shlex

from cryptography.hazmat.primitives.serialization import load_ssh_public_key


def validate_public_key(value):
    if not isinstance(value, str) or len(value) > 16384 or any(ord(c) < 32 for c in value):
        raise ValueError("Provide one OpenSSH public key line")
    fields = value.strip().split()
    if len(fields) < 2 or fields[0] not in {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521"}:
        raise ValueError("Use an Ed25519, RSA or ECDSA public key without authorization options")
    normalized = " ".join(fields[:2])
    try:
        load_ssh_public_key(normalized.encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Invalid OpenSSH public key") from exc
    return normalized


SCRIPT = r'''
import json
import os
import pwd
import shlex
import stat
import sys
import uuid

username, action, key = sys.argv[1:]
account = pwd.getpwnam(username)
if account.pw_uid < 1000 or account.pw_uid == 65534:
    raise ValueError('Protected system account')
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
home = os.open(account.pw_dir, flags)
ssh = None
try:
    if os.fstat(home).st_uid != account.pw_uid:
        raise ValueError('Home must be owned by the account')
    try:
        ssh = os.open('.ssh', flags, dir_fd=home)
    except FileNotFoundError:
        if action == 'snapshot':
            print(json.dumps({'home': account.pw_dir, 'exists': False})); sys.exit(0)
        os.mkdir('.ssh', 0o700, dir_fd=home)
        ssh = os.open('.ssh', flags, dir_fd=home)
        os.fchown(ssh, account.pw_uid, account.pw_gid)
    if os.fstat(ssh).st_uid != account.pw_uid:
        raise ValueError('SSH directory must be owned by the account')
    data = b''
    metadata = {'home': account.pw_dir, 'exists': False, 'ssh_mode': stat.S_IMODE(os.fstat(ssh).st_mode)}
    try:
        file = os.open('authorized_keys', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=ssh)
    except FileNotFoundError:
        file = None
    if file is not None:
        try:
            info = os.fstat(file)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != account.pw_uid or info.st_size > 1048576:
                raise ValueError('authorized_keys must be a bounded, account-owned regular file with one link')
            with os.fdopen(file, 'rb', closefd=False) as stream:
                data = stream.read(1048577)
            if len(data) > 1048576:
                raise ValueError('authorized_keys exceeds size limit')
            metadata.update(exists=True, mode=stat.S_IMODE(info.st_mode), content=data.decode('utf-8'))
        finally:
            os.close(file)
    if action == 'snapshot':
        print(json.dumps(metadata)); sys.exit(0)
    if action != 'install':
        raise ValueError('Unsupported key operation')
    lines = data.decode('utf-8').splitlines()
    def same_key(line):
        parts = shlex.split(line, comments=True)
        return any(parts[index:index + 2] == key.split() for index in range(len(parts) - 1))
    present = any(same_key(line) for line in lines)
    if not present:
        name = '.sm-key-' + uuid.uuid4().hex
        temporary = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=ssh)
        try:
            with os.fdopen(temporary, 'wb', closefd=False) as stream:
                stream.write(data + (b'\n' if data and not data.endswith(b'\n') else b'') + key.encode('ascii') + b'\n')
                stream.flush(); os.fsync(temporary)
            os.fchown(temporary, account.pw_uid, account.pw_gid)
            os.replace(name, 'authorized_keys', src_dir_fd=ssh, dst_dir_fd=ssh)
        finally:
            os.close(temporary)
            try:
                os.unlink(name, dir_fd=ssh)
            except FileNotFoundError:
                pass
    else:
        file = os.open('authorized_keys', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=ssh)
        try:
            info = os.fstat(file)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != account.pw_uid:
                raise ValueError('authorized_keys changed concurrently')
            os.fchmod(file, 0o600)
        finally:
            os.close(file)
    os.fchmod(ssh, 0o700)
    print('Public key already present' if present else 'Public key installed')
finally:
    if ssh is not None:
        os.close(ssh)
    os.close(home)
'''


def key_command(username, action, key=""):
    return "python3 -c " + shlex.quote(SCRIPT) + " " + " ".join(shlex.quote(value) for value in (username, action, key))
