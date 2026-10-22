"""Optional helper: images, posts and stories (Instagram, Pinterest, …) through gallery-dl.

gallery-dl is run as a subprocess (`python -m gallery_dl`) so its output can be parsed
and its API changes never break this app.
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
from pathlib import Path

# Sites where gallery-dl is the better tool than yt-dlp (images, stories, pins).
PREFERRED = {'instagram', 'pinterest'}

_LOG = re.compile(r'^\[[\w\-.]+\](?:\[[\w\-.]+\])*\[(error|warning)\]\s*(.*)$')
_AUTH_HINTS = ('authrequired', 'authentication', 'login', 'log in', 'sign in', 'cookies',
               '401', '403', 'forbidden', 'unauthorized', 'private', 'checkpoint', 'challenge')


def available() -> bool:
    try:
        import gallery_dl  # noqa: F401
        return True
    except ImportError:
        return False


def identify(url: str) -> tuple[str, str] | None:
    """(category, subcategory) of the gallery-dl extractor that handles this URL, or None."""
    try:
        from gallery_dl import extractor
        ex = extractor.find(url)
    except Exception:  # noqa: BLE001
        return None
    if ex is None:
        return None
    return ex.category, getattr(ex, 'subcategory', '') or ''


def prefers(url: str) -> bool:
    info = identify(url)
    return bool(info and info[0] in PREFERRED)


def needs_login(message: str) -> bool:
    m = (message or '').lower()
    return any(h in m for h in _AUTH_HINTS)


def _base_cmd(cookies_browser: str | None) -> list[str]:
    cmd = [sys.executable, '-m', 'gallery_dl']
    if cookies_browser:
        cmd += ['--cookies-from-browser', cookies_browser]
    return cmd


def _split(lines: list[str]) -> tuple[list[str], list[str]]:
    """Separate payload lines from error/warning log lines."""
    payload, problems = [], []
    for line in lines:
        m = _LOG.match(line)
        if m:
            if m.group(1) == 'error':
                problems.append(m.group(2))
        elif line.strip():
            payload.append(line.rstrip('\n'))
    return payload, problems


def count_items(url: str, cookies_browser: str | None = None) -> tuple[int, list[str]]:
    """How many files would be downloaded. Returns (count, error messages)."""
    r = subprocess.run(_base_cmd(cookies_browser) + ['-g', url], capture_output=True, text=True)
    payload, _ = _split(r.stdout.splitlines())
    _, problems = _split(r.stderr.splitlines())
    urls = [p for p in payload if not p.startswith('#')]
    return len(urls), problems


def download(url: str, outdir: Path, items: str | None = None, cookies_browser: str | None = None,
             on_file=None) -> tuple[list[Path], list[str]]:
    """Download straight into `outdir` (no sub-folders).

    `on_file(path, skipped)` is called for each file. Returns (files, error messages)."""
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = _base_cmd(cookies_browser) + ['-D', str(outdir)]     # exact folder: no site/author sub-folders
    if items:
        cmd += ['--range', items]
    cmd.append(url)
    files: list[Path] = []
    problems: list[str] = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        for raw in proc.stdout:                       # type: ignore[union-attr]
            line = raw.rstrip('\n')
            m = _LOG.match(line)
            if m:
                if m.group(1) == 'error':
                    problems.append(m.group(2))
                continue
            if not line.strip():
                continue
            skipped = line.startswith('# ')
            path = Path(line[2:] if skipped else line)
            files.append(path)
            if on_file:
                on_file(path, skipped)
    finally:
        proc.stdout.close()                           # type: ignore[union-attr]
        code = proc.wait()
    if code and not files and not problems:
        problems.append(f'gallery-dl exited with code {code}')
    return files, list(dict.fromkeys(problems))
