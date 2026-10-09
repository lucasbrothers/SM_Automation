"""Read-only bounded Include traversal for the Linux SSH apply adapter."""
import shlex

SCAN_SCRIPT = r'''
import glob
import shlex
from pathlib import Path

def scan(filename, directory):
    root = Path(directory).resolve()
    seen = set()
    def under_root(path):
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
    def visit(path, depth):
        source = Path(path)
        if source.is_symlink():
            raise ValueError('Symlink SSH configuration is unsupported')
        target = source.resolve()
        if not under_root(target):
            raise ValueError('SSH Include must stay under configuration directory')
        if depth > 8 or len(seen) >= 1000:
            raise ValueError('SSH Include traversal limit exceeded')
        if target in seen:
            raise ValueError('Repeated or cyclic SSH Include is unsupported')
        seen.add(target)
        if target.stat().st_size > 1048576:
            raise ValueError('SSH configuration exceeds size limit')
        for line in target.read_text().splitlines():
            fields = shlex.split(line, comments=True)
            if not fields:
                continue
            key = fields[0].lower()
            if '=' in key:
                key, value = key.split('=', 1)
                fields = [key, value, *fields[1:]]
            if key == 'match':
                raise ValueError('Match configuration requires a dedicated conditional adapter')
            if key == 'include':
                for pattern in fields[1:]:
                    if any(c in pattern for c in ('$', '%', '~')):
                        raise ValueError('Unsupported SSH Include expansion')
                    candidate = Path(pattern)
                    if not candidate.is_absolute():
                        candidate = root / candidate
                    if not under_root(candidate.resolve()):
                        raise ValueError('SSH Include must stay under configuration directory')
                    for included in sorted(glob.glob(str(candidate))):
                        visit(included, depth + 1)
    visit(filename, 0)
'''


def scan_command():
    script = SCAN_SCRIPT + "\nscan('/etc/ssh/sshd_config', '/etc/ssh')\n"
    return ('(for interpreter in /usr/bin/python3 /usr/libexec/platform-python; do '
            '[ -x "$interpreter" ] || continue; exec "$interpreter" -c ' + shlex.quote(script) +
            "; done; echo 'SSH Include scan requires system Python 3' >&2; exit 1)")
