"""Resolve pinned RHEL DNF plans without installing or downloading packages."""
import json
import shlex

from engine.remote import capture, privileged


SCRIPT = r'''
import hashlib
import json
import sys
import dnf
import dnf.rpm
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

def resolve(specs):
    with dnf.Base() as base:
        base.conf.read()
        base.conf.cacheonly = True
        base.conf.best = True
        base.conf.substitutions['releasever'] = dnf.rpm.detect_releasever('/')
        base.read_all_repos()
        for repo in base.repos.iter_enabled():
            repo.skip_if_unavailable = False
        if hasattr(base, 'fill_sack_from_repos_in_cache'):
            base.fill_sack_from_repos_in_cache(load_system_repo=True)
        else:
            base.fill_sack(load_system_repo=True)
        all_installed = list(base.sack.query().installed())
        state = sorted((p.name, p.arch, p.evr) for p in all_installed)
        state_hash = hashlib.sha256(json.dumps(state, separators=(',', ':')).encode()).hexdigest()
        packages, pins = [], []
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
        return {'action': 'plan', 'manager': 'dnf', 'pins': pins, 'packages': packages,
                'operations': operations, 'rpm_state': state_hash, 'apply_supported': False,
                'output': json.dumps(operations, indent=2),
                'note': 'Cache-only DNF resolution. RPM application adapter is still pending; nothing installed or downloaded'}
'''


def make_plan(client, packages, mode):
    payload = json.dumps(packages, separators=(",", ":"))
    script = SCRIPT + "\nprint(json.dumps(resolve(json.loads(sys.argv[1]))))\n"
    command = "for interpreter in /usr/libexec/platform-python /usr/bin/python3; do "
    command += '[ -x "$interpreter" ] || continue; "$interpreter" -c "import dnf" >/dev/null 2>&1 || continue; '
    command += 'exec "$interpreter" -c ' + shlex.quote(script) + " " + shlex.quote(payload) + "; done; "
    command += "echo 'RHEL planning requires system Python DNF bindings' >&2; exit 1"
    response = capture(client, privileged(command, mode), timeout=180, max_bytes=4 * 1024 * 1024)
    if response.exit_code:
        raise RuntimeError(response.stderr.strip() or "DNF plan resolution failed")
    return json.loads(response.stdout)
