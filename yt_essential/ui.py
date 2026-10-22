"""Minimal full-screen terminal UI (mole-style): colours, keys, spinner, selectable lists."""
from __future__ import annotations

import codecs
import os
import select
import shutil
import sys
import threading
import time
from contextlib import contextmanager

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - Windows
    termios = tty = None

SPINNER = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
_FONT = {
    'E': ['█████', '█    ', '████ ', '█    ', '█████'],
    'S': ['█████', '█    ', '█████', '    █', '█████'],
    'N': ['█   █', '██  █', '█ █ █', '█  ██', '█   █'],
    'T': ['█████', '  █  ', '  █  ', '  █  ', '  █  '],
    'I': ['███', ' █ ', ' █ ', ' █ ', '███'],
    'A': [' ███ ', '█   █', '█████', '█   █', '█   █'],
    'L': ['█    ', '█    ', '█    ', '█    ', '█████'],
}
LOGO = [' '.join(_FONT[c][r] for c in 'ESSENTIAL') for r in range(5)]
LOGO_SHADES = (159, 117, 75, 39, 33)      # light → deep blue, top to bottom


class Abort(Exception):
    """User pressed Esc / q / Ctrl+C / Ctrl+D."""


# ── terminal basics ───────────────────────────────────────────

def interactive() -> bool:
    return bool(termios and sys.stdin.isatty() and sys.stdout.isatty())


def _color() -> bool:
    return sys.stdout.isatty() and 'NO_COLOR' not in os.environ


def _c(code: str, s: str) -> str:
    return f'\033[{code}m{s}\033[0m' if _color() else s


def bold(s): return _c('1', s)
def dim(s): return _c('2', s)
def green(s): return _c('38;5;80', s)          # ticks (soft teal)
def yellow(s): return _c('38;5;179', s)        # warnings
def red(s): return _c('38;5;167', s)
def accent(s): return _c('1;38;5;117', s)      # light blue, bold
def blue(s): return _c('1;38;5;75', s)
def value(s): return _c('38;5;117', s)         # values next to a ✓
def grey(s): return _c('38;5;245', s)
def keycap(s): return _c('38;5;75', s)         # key letters in hints


def bar_row(text: str, width: int) -> str:
    """A selected row: white text on a deep-blue bar."""
    pad = text.ljust(width)
    return f'\033[48;5;24;38;5;231;1m{pad}\033[0m' if _color() else f'> {pad}'


def hints(*pairs: tuple[str, str]) -> str:
    """('↑↓','move'), ('q','quit') -> keycap-style hint line."""
    return '   '.join(f'{keycap(k)} {grey(v)}' for k, v in pairs)


def logo_lines() -> list[str]:
    if cols() < 62:
        return [bold(blue('ESSENTIAL'))]
    return [_c(f'38;5;{shade}', row) for row, shade in zip(LOGO, LOGO_SHADES)]


def cols() -> int:
    return max(40, shutil.get_terminal_size((100, 30)).columns)


def rows() -> int:
    return max(12, shutil.get_terminal_size((100, 30)).lines)


def shorten(text: str, width: int) -> str:
    text = ' '.join(str(text).split())
    return text if len(text) <= width else text[:max(1, width - 1)] + '…'


def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def clear_line() -> None:
    if interactive():
        _w('\r\033[2K')


@contextmanager
def fullscreen():
    """Alternate screen: wipes the terminal view, restores it on exit."""
    if not interactive() or getattr(fullscreen, 'active', False):
        yield
        return
    fullscreen.active = True
    _w('\033[?1049h\033[2J\033[H\033[?25l')
    try:
        yield
    finally:
        _w('\033[?25h\033[?1049l')
        fullscreen.active = False


@contextmanager
def _cursor(visible: bool):
    if interactive():
        _w('\033[?25h' if visible else '\033[?25l')
    try:
        yield
    finally:
        if interactive():
            _w('\033[?25l' if getattr(fullscreen, 'active', False) else '\033[?25h')


@contextmanager
def no_echo():
    """While busy: hide typed characters and drop anything typed ahead (so stray Enters
    can't auto-answer the next prompt)."""
    if not interactive():
        yield
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~(termios.ECHO | termios.ICANON)
    try:
        termios.tcsetattr(fd, termios.TCSANOW, new)
        yield
    finally:
        termios.tcflush(fd, termios.TCIFLUSH)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ── keys ──────────────────────────────────────────────────────

def read_key(timeout: float | None = None) -> str | None:
    """Return 'up','down','left','right','enter','esc', a single char, or None on timeout."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        if not select.select([fd], [], [], timeout)[0]:
            return None
        data = os.read(fd, 1)
        if data == b'\x1b':
            if select.select([fd], [], [], 0.04)[0]:
                seq = os.read(fd, 1)
                if seq in (b'[', b'O'):               # read exactly one escape sequence, no more
                    while select.select([fd], [], [], 0.04)[0]:
                        b = os.read(fd, 1)
                        seq += b
                        if 0x40 <= b[0] <= 0x7e:
                            break
                return {b'[A': 'up', b'[B': 'down', b'[C': 'right', b'[D': 'left',
                        b'OA': 'up', b'OB': 'down', b'OC': 'right', b'OD': 'left'}.get(seq, 'other')
            return 'esc'
        if data in (b'\r', b'\n'):
            return 'enter'
        if data == b'\x04':
            raise EOFError
        if data[0] >= 0x80:                       # swallow the rest of a UTF-8 char
            os.read(fd, 3) if select.select([fd], [], [], 0.01)[0] else None
            return 'other'
        return data.decode('ascii', 'ignore')
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def wait_key(message: str = 'Press any key to continue', extra: str = '') -> str:
    """Show a dim hint and wait. Returns the key pressed ('' when not interactive)."""
    if not interactive():
        return ''
    _w('\n  ' + (extra and extra + '   ') + grey(message) + '\n')
    try:
        return read_key() or ''
    except (EOFError, KeyboardInterrupt):
        raise Abort from None


# ── session lines (the ✓ list shown on top of the screen) ─────

_lines: list[str] = []


def reset() -> None:
    _lines.clear()


def header(crumb: str = '') -> str:
    return f'\n  {bold(blue("ESSENTIAL"))}' + (f' {grey("›")} {grey(crumb)}' if crumb else '') + '\n'


def refresh(crumb: str = '') -> None:
    """Clear the screen and redraw the compact header plus everything done so far."""
    if not interactive():
        return
    _w('\033[2J\033[H')
    print(header(crumb))
    for line in _lines:
        print(line)


LABEL_W = 10


def _fmt_done(label: str, val: str = '', mark: str | None = None) -> str:
    mark = mark if mark is not None else green('✓')
    line = f'  {mark} {label}'
    if val:
        line += f' {grey("·")} {value(shorten(val, cols() - len(label) - 8))}'
    return line


def step(label: str, val: str = '') -> None:
    line = _fmt_done(label, val)
    _lines.append(line)
    clear_line()
    print(line)


def note(text: str) -> None:
    line = f'  {yellow("!")} {yellow(shorten(text, cols() - 6))}'
    _lines.append(line)
    clear_line()
    print(line)


def fail(text: str) -> None:
    line = f'  {red("✗")} {red(shorten(text, cols() - 6))}'
    _lines.append(line)
    clear_line()
    print(line, file=sys.stdout)


def say(msg: str = '') -> None:
    print(msg)


def dump_session() -> None:
    """Print the finished session to the normal screen so it stays in the scrollback."""
    print()
    for line in _lines:
        print(line)
    print()


# ── spinner / tasks ───────────────────────────────────────────

class task:
    """`with ui.task('Analyzing link'): ...` — animated spinner, cleared on exit."""

    def __init__(self, text: str):
        self.text = text
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self):
        i = 0
        while not self._stop.is_set():
            _w(f'\r\033[2K  {accent(SPINNER[i % len(SPINNER)])} {self.text}')
            i += 1
            self._stop.wait(0.08)

    def __enter__(self):
        self._noecho = no_echo()
        self._noecho.__enter__()
        if interactive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            print(f'  … {self.text}')
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
            _w('\r\033[2K')
        self._noecho.__exit__(*exc)
        return False


_spin = [0]


def progress_line(fraction: float | None, text: str = '') -> None:
    """One in-place progress line: spinner, bar, text."""
    if not interactive():
        return
    _spin[0] += 1
    _w(f'\r\033[2K  {accent(SPINNER[_spin[0] % len(SPINNER)])} {bar(fraction)} {text}')


def bar(fraction: float | None, width: int = 24) -> str:
    if fraction is None:
        return dim('─' * width)
    n = max(0, min(width, int(round(fraction * width))))
    return _c('38;5;75', '━' * n) + dim('─' * (width - n))


# ── prompts ───────────────────────────────────────────────────

def _read_line(prompt: str) -> str:
    """Tiny line editor: typing, Backspace, paste, UTF-8; Esc cancels (raises Abort)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    decoder = codecs.getincrementaldecoder('utf-8')('ignore')
    buf: list[str] = []

    def draw() -> None:
        _w(f'\r\033[2K{prompt}{"".join(buf)}')

    try:
        tty.setcbreak(fd)
        draw()
        while True:
            chunk = os.read(fd, 4096)
            if not chunk or chunk == b'\x04':
                raise EOFError
            if chunk == b'\x1b':
                raise Abort
            if chunk.startswith(b'\x1b'):          # arrow keys etc. — ignore
                continue
            for ch in decoder.decode(chunk):
                if ch in '\r\n':
                    _w('\r\033[2K')
                    return ''.join(buf)
                if ch in '\x7f\x08':
                    if buf:
                        buf.pop()
                elif ch >= ' ':
                    buf.append(ch)
            draw()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f' {grey("[" + default + "]")}' if default else ''
    text = f'  {accent("›")} {prompt}{suffix}: '
    try:
        if interactive():
            with _cursor(True):
                raw = _read_line(text).strip()
        else:
            raw = input(text).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise Abort from None
    return raw or (default or '')


def choose(title: str, options: list[str], default: int = 1) -> int:
    """Arrow-key list (numbers also work). Returns a 0-based index."""
    n = len(options)
    if not interactive():
        print(f'\n  {title}')
        for i, opt in enumerate(options, 1):
            print(f'   {"*" if i == default else " "}{i}) {opt}')
        while True:
            raw = ask('No.', str(default))
            if raw.isdigit() and 1 <= int(raw) <= n:
                return int(raw) - 1
            print('  Please enter a number from the list.')

    sel = default - 1
    width = min(cols() - 6, max(len(o) for o in options) + 8, 76)
    height = n + 2

    def draw(first: bool) -> None:
        if not first:
            _w(f'\033[{height}A')
        _w('\r\033[J')
        print(f'  {bold(title)}')
        for i, opt in enumerate(options):
            text = shorten(opt, width - 6)
            if i == sel:
                print(f'  {accent("➤")} {accent(f"{i + 1}. {text}")}')
            else:
                print(f'    {i + 1}. {text}')
        print('  ' + grey('↑↓ select  |  Enter confirm  |  Esc cancel'))

    with _cursor(False):
        draw(True)
        while True:
            try:
                key = read_key()
            except (EOFError, KeyboardInterrupt):
                raise Abort from None
            if key in ('up', 'k'):
                sel = (sel - 1) % n
            elif key in ('down', 'j'):
                sel = (sel + 1) % n
            elif key == 'enter':
                break
            elif key in ('esc', 'q'):
                _w(f'\033[{height}A\r\033[J')
                raise Abort
            elif key and key.isdigit() and n <= 9 and 1 <= int(key) <= n:
                sel = int(key) - 1
                break
            else:
                continue
            draw(False)
    _w(f'\033[{height}A\r\033[J')
    return sel


def confirm(prompt: str, default: bool = True) -> bool:
    if interactive():
        return choose(prompt, ['Yes', 'No'], 1 if default else 2) == 0
    while True:
        raw = ask(f'{prompt} (y/n)', 'y' if default else 'n').lower()
        if raw in ('y', 'yes'):
            return True
        if raw in ('n', 'no'):
            return False
        print('  Please answer y or n.')


# ── main-menu loop ────────────────────────────────────────────

def menu_loop(draw, n: int, sel: int = 0, keys: str = '', poll=None):
    """Redraws via draw(sel). Returns ('enter', idx) | ('key', char) | ('quit', None)."""
    with _cursor(False):
        while True:
            draw(sel)
            while True:
                try:
                    key = read_key(0.2)
                except (EOFError, KeyboardInterrupt):
                    return ('quit', None)
                if key is None:
                    if poll and poll():
                        break
                    continue
                if key in ('up', 'k'):
                    sel = (sel - 1) % n
                elif key in ('down', 'j'):
                    sel = (sel + 1) % n
                elif key == 'enter':
                    return ('enter', sel)
                elif key in ('esc', 'q', 'Q'):
                    return ('quit', None)
                elif key.isdigit() and 1 <= int(key) <= n:
                    return ('enter', int(key) - 1)
                elif key.lower() in keys:
                    return ('key', key.lower())
                else:
                    continue
                break
