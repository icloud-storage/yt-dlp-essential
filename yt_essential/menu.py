"""The main menu (what `essn` shows with no arguments)."""
from __future__ import annotations

import sys
from pathlib import Path

from . import __version__, config, ui, updates
from .cli import run_download
from .engine import installed_browsers

class Restart(Exception):
    """Raised after an update so the app relaunches with the new versions."""


def _short_path(p: Path) -> str:
    s = str(p)
    home = str(Path.home())
    return '~' + s[len(home):] if s.startswith(home) else s


def _items(cfg: dict, checker: updates.UpdateCheck) -> list[tuple[str, str]]:
    ask = bool(cfg.get('ask_dir_each_time'))
    browser = cfg.get('cookies_browser')
    cur = checker.current
    parts = [f'{updates.DISPLAY.get(p, p)} {cur[p]}' for p, _ in updates.PACKAGES if cur.get(p)]
    update_desc = ' · '.join(parts) if parts else 'Check for updates'
    return [
        ('Download', 'Paste a link, get video or audio'),
        ('Folder', _short_path(config.base_download_dir(cfg))),
        ('Ask folder', 'On — choose a folder before each download' if ask else 'Off — always save to the folder above'),
        ('Cookies', browser.capitalize() if browser else 'Not set — asked only when needed'),
        ('Update', update_desc),
    ]


def _draw(sel: int, cfg: dict, checker: updates.UpdateCheck) -> None:
    out = ['\033[2J\033[H', '']
    for row in ui.logo_lines():
        out.append('  ' + row)
    out.append('')
    if checker.available:
        text = '  ·  '.join(f'{updates.DISPLAY.get(p, p)} {a} → {b}' for p, (a, b) in checker.updates.items())
        out.append('  ' + ui.yellow('↑ New version available: ') + ui.value(text) + ui.grey('   press U'))
        out.append('')
    items = _items(cfg, checker)
    width = max(len(label) for label, _ in items) + 3
    room = ui.cols() - width - 12
    for i, (label, desc) in enumerate(items):
        text = ui.shorten(desc, room)
        if i == sel:
            out.append(f'  {ui.accent("➤")} {ui.accent(f"{i + 1}. {label}".ljust(width + 3))}{ui.value(text)}')
        else:
            out.append(f'    {i + 1}. {label.ljust(width)}{ui.grey(text)}')
    out.append('')
    out.append('  ' + ui.grey('↑↓  |  Enter  |  U Update  |  V Version  |  Q Quit'))
    sys.stdout.write('\n'.join(out) + '\n')
    sys.stdout.flush()


def set_folder(cfg: dict) -> None:
    ui.reset()
    ui.refresh('Folder')
    ui.step('Current', str(config.base_download_dir(cfg)))
    ui.say('  ' + ui.grey('Enter = keep the default ~/Downloads/yt-essential. Audio and video get their own sub-folders.'))
    raw = ui.ask('New folder', str(config.default_download_dir()))
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        ui.fail(f'Cannot use this folder: {e}')
        ui.wait_key()
        return
    cfg['download_dir'] = None if path == config.default_download_dir() else str(path)
    config.save(cfg)


def set_cookie_browser(cfg: dict) -> None:
    ui.reset()
    ui.refresh('Cookies')
    browsers = installed_browsers()
    cur = cfg.get('cookies_browser')
    idx = ui.choose('Browser to take cookies from', ['None — ask only when needed'] + [b.capitalize() for b in browsers],
                    browsers.index(cur) + 2 if cur in browsers else 1)
    cfg['cookies_browser'] = None if idx == 0 else browsers[idx - 1]
    config.save(cfg)


def do_update(checker: updates.UpdateCheck) -> None:
    ui.reset()
    ui.refresh('Update')
    outdated: dict[str, tuple[str, str]] = {}
    with ui.task('Checking for updates'):
        reachable = False
        for pkg, _ in updates.PACKAGES:
            cur = checker.current.get(pkg)
            if not cur:
                continue
            latest = updates.latest_version(pkg, force=True)
            reachable = reachable or latest is not None
            if latest and updates.is_newer(latest, cur):
                outdated[pkg] = (cur, latest)
    if not reachable:
        ui.fail('Could not reach the update server — check your internet connection')
    elif not outdated:
        for pkg, _ in updates.PACKAGES:
            if checker.current.get(pkg):
                ui.step(updates.DISPLAY.get(pkg, pkg), f'{checker.current[pkg]} — up to date')
    else:
        for pkg, (cur, latest) in outdated.items():
            ui.step(updates.DISPLAY.get(pkg, pkg), f'{cur} → {latest}')
        with ui.task('Updating'):
            ok, tail = updates.upgrade()
        if not ok:
            ui.fail('Update failed')
            ui.say('  ' + ui.grey(tail.replace('\n', '\n  ')))
        else:
            after = updates.versions_after_upgrade()
            ui.say()
            for pkg, (cur, _) in outdated.items():
                ui.step('Updated', f'{updates.DISPLAY.get(pkg, pkg)} {cur} → {after.get(pkg, "?")}')
            ui.wait_key('Press any key to restart')
            raise Restart
    ui.wait_key()


def show_version() -> None:
    ui.reset()
    ui.refresh('Version')
    for pkg, _ in updates.PACKAGES:
        v = updates.installed_version(pkg)
        if v:
            ui.step(updates.DISPLAY.get(pkg, pkg), v)
    ui.step('Python', sys.version.split()[0])
    ui.wait_key()


def _plain_menu(cfg: dict, checker: updates.UpdateCheck) -> int:
    """Fallback when there is no real terminal (pipes, CI)."""
    while True:
        ui.say('essential')
        for i, (label, desc) in enumerate(_items(cfg, checker), 1):
            ui.say(f'  {i}) {label}: {desc}')
        ui.say('  0) Quit')
        raw = ui.ask('No.', '0')
        if raw == '0':
            return 0
        if raw.isdigit() and 1 <= int(raw) <= 5:
            if _act(int(raw) - 1, cfg, checker):
                continue
        else:
            ui.say('Please enter a number from the list.')


def _act(idx: int, cfg: dict, checker: updates.UpdateCheck) -> bool:
    """Run menu item idx. Returns True to stay in the menu."""
    try:
        if idx == 0:
            run_download(cfg)
        elif idx == 1:
            set_folder(cfg)
        elif idx == 2:
            cfg['ask_dir_each_time'] = not cfg.get('ask_dir_each_time')
            config.save(cfg)
        elif idx == 3:
            set_cookie_browser(cfg)
        elif idx == 4:
            do_update(checker)
    except ui.Abort:
        pass          # Esc inside a sub-screen = back to the menu
    return True


def run(cfg: dict) -> int:
    checker = updates.UpdateCheck()
    checker.start()
    if not ui.interactive():
        return _plain_menu(cfg, checker)
    sel = 0
    while True:
        kind, val = ui.menu_loop(lambda s: _draw(s, cfg, checker), 5, sel, keys='uv', poll=checker.changed)
        if kind == 'quit':
            return 0
        if kind == 'enter':
            sel = val
            _act(val, cfg, checker)
        elif val == 'u':
            _act(4, cfg, checker)
        elif val == 'v':
            show_version()
