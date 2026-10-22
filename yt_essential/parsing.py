"""Pure helpers: item lists, time ranges, sizes. No I/O, easy to test."""
from __future__ import annotations

import re


class ItemsError(ValueError):
    """Human-readable problem with a playlist selection."""


class RangeError(ValueError):
    """Human-readable problem with a time range."""


_DASHES = str.maketrans({'–': '-', '—': '-', '−': '-', ';': ',', '،': ','})


def parse_items(spec: str, total: int | None = None) -> str:
    """'1, 3, 5-8' -> '1,3,5-8' (yt-dlp playlist_items syntax). Validates against `total`."""
    spec = (spec or '').translate(_DASHES).replace(' ', '')
    if not spec:
        raise ItemsError('nothing entered')
    out = []
    for tok in spec.split(','):
        if not tok:
            continue
        m = re.fullmatch(r'(\d+)(?:-(\d+)?)?', tok)
        if not m:
            raise ItemsError(f'"{tok}" is not a number or range')
        a = int(m.group(1))
        if '-' in tok:
            b = int(m.group(2)) if m.group(2) else total
            if b is None:
                raise ItemsError(f'"{tok}" is not a number or range')
            if a > b:
                raise ItemsError(f'range {tok} is backwards')
        else:
            b = a
        if a < 1 or (total is not None and b > total):
            raise ItemsError(f'{tok} is outside 1–{total if total is not None else "?"}')
        out.append(str(a) if a == b else f'{a}-{b}')
    if not out:
        raise ItemsError('nothing entered')
    return ','.join(out)


def _clock(text: str) -> float | None:
    """'1:30' / '1:02:30' / '0:01.5' -> seconds."""
    if not re.fullmatch(r'\d+(?::\d{1,2}){1,2}(?:[.,]\d+)?', text):
        return None
    parts = text.replace(',', '.').split(':')
    if any(float(p) >= 60 for p in parts[1:]):
        return None
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


def parse_moment(text: str, bare_unit: float = 60.0) -> float | None:
    """A point in time. With a colon it is clock time (M:SS or H:MM:SS); a bare number is
    multiplied by `bare_unit` (60 = minutes, 1 = seconds)."""
    text = (text or '').strip()
    if ':' in text:
        return _clock(text)
    if re.fullmatch(r'\d+(?:[.,]\d+)?', text):
        return float(text.replace(',', '.')) * bare_unit
    return None


def parse_range(text: str, duration: float | None = None) -> tuple[float, float | None]:
    """'0:30-1:45' (the documented form) plus shortcuts:
    '0-90' -> seconds when no colon is used anywhere; '0:00-1' / '0-1:00' -> a bare number
    next to clock time means minutes; '2:00-' -> to the end."""
    parts = (text or '').translate(_DASHES).split('-')
    if len(parts) != 2:
        raise RangeError('write it as start-end, for example 0:30-1:45')
    left, right = parts[0].strip(), parts[1].strip()
    unit = 60.0 if (':' in left or ':' in right) else 1.0
    start = parse_moment(left, unit) if left else 0.0
    end = parse_moment(right, unit) if right else None
    if start is None or (right and end is None):
        raise RangeError('could not read the time — try 0:30-1:45')
    if end is not None and end <= start:
        raise RangeError('the end must be later than the start')
    if duration:
        if start >= duration:
            raise RangeError(f'the start is past the end of the video ({format_duration(duration)})')
        if end is not None:
            end = min(end, duration)
    return start, end


def format_duration(seconds) -> str:
    if seconds is None:
        return '?'
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def format_size(n) -> str:
    if not n:
        return '?'
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit in ('B', 'KB') else f'{n:.1f} {unit}'
        n /= 1024
    return '?'
