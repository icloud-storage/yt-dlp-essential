"""Check PyPI for newer yt-dlp / gallery-dl (cached, never blocks the UI)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from importlib import metadata

from . import REPO, __version__, config

SELF = 'yt-dlp-essential'
SELF_ZIP = f'https://github.com/{REPO}/archive/refs/heads/main.zip'     # no git needed
SELF_VERSION_URL = f'https://raw.githubusercontent.com/{REPO}/main/yt_essential/__init__.py'

# (package name, pip requirement)
PACKAGES = [(SELF, SELF_ZIP), ('yt-dlp', 'yt-dlp[default]'), ('gallery-dl', 'gallery-dl')]
DISPLAY = {SELF: 'essential'}
CACHE_TTL = 6 * 3600


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r'\d+', v or ''))


def is_newer(new: str, current: str) -> bool:
    return bool(new) and parse_version(new) > parse_version(current)


def parse_self_version(text: str) -> str | None:
    m = re.search(r'''__version__\s*=\s*['"]([^'"]+)['"]''', text or '')
    return m.group(1) if m else None


def installed_version(pkg: str = 'yt-dlp') -> str | None:
    if pkg == SELF:
        return __version__
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        pass
    # running from a source checkout (no dist-info): ask the module itself
    try:
        mod = __import__(pkg.replace('-', '_') + '.version', fromlist=['__version__'])
        return mod.__version__
    except Exception:  # noqa: BLE001
        return None


def fetch_latest(pkg: str, timeout: float = 4.0) -> str | None:
    try:
        if pkg == SELF:       # the version number in the main branch on GitHub
            req = urllib.request.Request(SELF_VERSION_URL, headers={'User-Agent': 'yt-dlp-essential'})
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
                return parse_self_version(r.read().decode('utf-8', 'replace'))
        req = urllib.request.Request(f'https://pypi.org/pypi/{pkg}/json', headers={'User-Agent': 'yt-dlp-essential'})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
            return json.load(r)['info']['version']
    except Exception:  # noqa: BLE001 — offline, DNS, JSON: all mean "unknown"
        return None


def latest_version(pkg: str = 'yt-dlp', force: bool = False) -> str | None:
    cache = config.config_dir() / 'update-check.json'
    try:
        data = json.loads(cache.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    entry = data.get(pkg)
    if not force and isinstance(entry, dict):
        try:
            if time.time() - entry['checked'] < CACHE_TTL and entry.get('latest'):
                return entry['latest']
        except (KeyError, TypeError):
            pass
    latest = fetch_latest(pkg)
    if latest:
        data[pkg] = {'checked': time.time(), 'latest': latest}
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data), encoding='utf-8')
        except OSError:
            pass
    return latest


class UpdateCheck(threading.Thread):
    """Runs in the background. `.updates` maps package -> (current, latest) for outdated ones."""

    def __init__(self):
        super().__init__(daemon=True)
        self.current = {p: installed_version(p) for p, _ in PACKAGES}
        self.updates: dict[str, tuple[str, str]] = {}
        self.done = False
        self._reported = False

    @property
    def available(self) -> bool:
        return bool(self.updates)

    def run(self):
        for pkg, _ in PACKAGES:
            cur = self.current.get(pkg)
            if not cur:
                continue
            latest = latest_version(pkg)
            if latest and is_newer(latest, cur):
                self.updates[pkg] = (cur, latest)
        self.done = True

    def changed(self) -> bool:
        """True once, when the result arrives (so the UI redraws)."""
        if self.done and not self._reported:
            self._reported = True
            return self.available
        return False


def upgrade() -> tuple[bool, str]:
    """pip install -U the installed packages into the current environment."""
    reqs = [req for pkg, req in PACKAGES if installed_version(pkg)]
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--upgrade', *reqs],
                       capture_output=True, text=True)
    tail = '\n'.join((r.stderr or r.stdout).strip().splitlines()[-3:])
    return r.returncode == 0, tail


def versions_after_upgrade() -> dict[str, str]:
    code = ('import json,importlib.metadata as m;out={}\n'
            'for p in %r:\n'
            '    try: out[p]=m.version(p)\n'
            '    except Exception: pass\n'
            'print(json.dumps(out))' % [p for p, _ in PACKAGES])
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {}
