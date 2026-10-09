"""Resolve cached RHEL DNF plans and apply prepared, verified local RPMs."""
import json
import shlex

from engine.remote import capture, privileged


SCRIPT = r'''
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import dnf
import dnf.rpm
import hawkey
import rpm

def identity(package):
    return package.name, package.arch

def version(package):
    return str(package.epoch), package.version, package.release

def record(package):
    checksum = package.chksum
    return {'name': package.name, 'architecture': package.arch, 'version': package.evr,
            'repository': package.reponame,
            'checksum': [checksum[0], checksum[1].hex()] if checksum else None}

def verify_cached_package(package):
    path = Path(package.localPkg())
    if not path.is_absolute():
        raise ValueError('Cached RPM path must be absolute')
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('RPM cache must use root-owned directories without group/world write access')
    file = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(file)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('RPM must be a root-owned regular file without group/world write access')
        checksum = package.chksum
        if not checksum:
            raise ValueError('RPM repository checksum is missing')
        algorithm = hawkey.chksum_name(checksum[0])
        if algorithm not in ('sha256', 'sha384', 'sha512'):
            raise ValueError('RPM requires a SHA-256 or stronger repository checksum')
        digest = hashlib.new(algorithm)
        with os.fdopen(file, 'rb', closefd=False) as stream:
            while True:
                chunk = stream.read(1048576)
                if not chunk:
                    break
                digest.update(chunk)
        if digest.digest() != checksum[1]:
            raise ValueError('Cached RPM checksum does not match reviewed metadata')
    finally:
        os.close(file)

def commit_transaction(base, expected, plan):
    for field in ('pins', 'operations', 'rpm_state'):
        if expected.get(field) != plan[field]:
            raise ValueError('RPM state or dependencies changed since planning; create a new plan')
    installs = list(base.transaction.install_set) if base.transaction else []
    for package in installs:
        verify_cached_package(package)
        status, message = base.package_signature_check(package)
        if status != 0:
            raise ValueError('RPM signature verification failed: ' + str(message))
    if installs:
        base.do_transaction()
    return {'action': 'apply', 'manager': 'dnf', 'pins': plan['pins'],
            'applied': len(installs), 'reboot_required': None,
            'note': 'Used prepared signed RPMs only; no download or automatic reboot. Review reboot and service restart needs during maintenance'}

def resolve(specs, apply_plan=None):
    with dnf.Base() as base:
        base.conf.read()
        base.conf.cacheonly = True
        base.conf.best = True
        base.conf.gpgcheck = True
        base.conf.substitutions['releasever'] = dnf.rpm.detect_releasever('/')
        base.read_all_repos()
        for repo in base.repos.iter_enabled():
            repo.skip_if_unavailable = False
            repo.gpgcheck = True
        if hasattr(base, 'fill_sack_from_repos_in_cache'):
            base.fill_sack_from_repos_in_cache(load_system_repo=True)
        else:
            base.fill_sack(load_system_repo=True)
        all_installed = list(base.sack.query().installed())
        state = sorted((p.name, p.arch, p.evr) for p in all_installed)
        state_hash = hashlib.sha256(json.dumps(state, separators=(',', ':')).encode()).hexdigest()
        packages, pins, identities = [], [], set()
        for spec in specs:
            name, separator, requested = spec.partition('=')
            architecture = None
            if ':' in name:
                name, architecture = name.rsplit(':', 1)
            query = base.sack.query().installed().filter(name=name)
            if architecture:
                query = query.filter(arch=architecture)
            old = list(query)
            if len(old) != 1:
                raise ValueError('Select one installed version and architecture using name:arch: ' + name)
            old = old[0]
            if identity(old) in identities:
                raise ValueError('Duplicate selected RPM identity')
            identities.add(identity(old))
            available = base.sack.query().available().filter(name=name, arch=old.arch).upgrades()
            if requested:
                candidates = [p for p in available if p.evr == requested or p.evr == '0:' + requested]
                if old.evr == requested or old.evr == '0:' + requested:
                    candidate = old
                elif not candidates:
                    raise ValueError('Requested RPM upgrade is unavailable: ' + spec)
                else:
                    candidate = sorted(candidates, key=lambda p: p.reponame)[0]
            else:
                candidates = list(available.latest())
                candidate = sorted(candidates, key=lambda p: p.reponame)[0] if candidates else old
            if candidate is not old:
                base.package_upgrade(candidate)
            pins.append(name + ':' + old.arch + '=' + candidate.evr)
            packages.append({'name': name + ':' + old.arch, 'architecture': old.arch,
                             'installed': old.evr, 'candidate': candidate.evr})
        base.resolve(allow_erasing=False)
        installs = list(base.transaction.install_set) if base.transaction else []
        removes = list(base.transaction.remove_set) if base.transaction else []
        for old in removes:
            replacements = [p for p in installs if identity(p) == identity(old)]
            if not replacements or not all(rpm.labelCompare(version(p), version(old)) > 0 for p in replacements):
                raise ValueError('RPM plan contains removal, replacement or downgrade')
        operations = sorted([{'action': 'install', **record(p)} for p in installs] +
                            [{'action': 'replace_old', 'name': p.name, 'architecture': p.arch, 'version': p.evr} for p in removes],
                            key=lambda item: (item['action'], item['name'], item['architecture'], item['version']))
        plan = {'action': 'plan', 'manager': 'dnf', 'pins': pins, 'packages': packages,
                'operations': operations, 'rpm_state': state_hash, 'apply_supported': True,
                'output': json.dumps(operations, indent=2),
                'note': 'Cache-only DNF resolution; nothing installed or downloaded. Apply requires prepared signed RPMs in root-owned cache directories'}
        return commit_transaction(base, apply_plan, plan) if apply_plan is not None else plan
'''


def execute(client, packages, mode, expected=None):
    payload = json.dumps({"packages": packages, "expected": expected}, separators=(",", ":"))
    script = SCRIPT + "\nrequest = json.loads(sys.argv[1])\nresult = resolve(request['packages'], request['expected'])\nprint('\\nSM_AUTOMATION_RESULT=' + json.dumps(result))\n"
    command = "for interpreter in /usr/libexec/platform-python /usr/bin/python3; do "
    command += '[ -x "$interpreter" ] || continue; "$interpreter" -c "import dnf" >/dev/null 2>&1 || continue; '
    command += 'exec "$interpreter" -c ' + shlex.quote(script) + " " + shlex.quote(payload) + "; done; "
    command += "echo 'RHEL planning requires system Python DNF bindings' >&2; exit 1"
    response = capture(client, privileged(command, mode), timeout=900 if expected is not None else 180, max_bytes=4 * 1024 * 1024)
    if response.exit_code:
        raise RuntimeError(response.stderr.strip() or "DNF plan resolution failed")
    output = response.stdout.decode("utf-8", errors="replace")
    prefix, separator, payload = output.rpartition("\nSM_AUTOMATION_RESULT=")
    if not separator:
        raise ValueError("DNF did not return a structured result; inspect Linux job history")
    result = json.loads(payload)
    if expected is not None:
        result["output"] = prefix.strip()
    result["warnings"] = response.stderr
    return result


def make_plan(client, packages, mode):
    return execute(client, packages, mode)


def apply_plan(client, plan, mode):
    if not plan.get("apply_supported"):
        raise ValueError("Regenerate the RHEL patch plan with the current adapter")
    return execute(client, plan["pins"], mode, expected=plan)
