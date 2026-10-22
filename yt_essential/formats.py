"""Turn yt-dlp's raw format list into a short, human-friendly quality menu."""
from __future__ import annotations

from dataclasses import dataclass

from .parsing import format_size


@dataclass
class Quality:
    height: int
    fps: int | None
    ext: str
    codec: str
    size: int | None

    def label(self) -> str:
        parts = [f'{self.height}p']
        if self.fps and self.fps > 30:
            parts.append(f'{self.fps}fps')
        parts.append(f'{self.ext} ({self.codec})' if self.codec else self.ext)
        if self.size:
            parts.append(f'≈ {format_size(self.size)}')
        return '  ·  '.join(parts)


def short_codec(vcodec: str | None) -> str:
    v = (vcodec or '').lower()
    if v.startswith(('avc', 'h264')):
        return 'h264'
    if v.startswith(('hev', 'hvc', 'h265')):
        return 'h265'
    if v.startswith(('vp09', 'vp9')):
        return 'vp9'
    if v.startswith('vp8'):
        return 'vp8'
    if v.startswith('av01') or v == 'av1':
        return 'av1'
    return v.split('.')[0] if v and v != 'none' else ''


def _has_video(f: dict) -> bool:
    return f.get('vcodec') not in (None, 'none') and bool(f.get('height'))


def _has_audio(f: dict) -> bool:
    return f.get('acodec') not in (None, 'none')


def _size(f: dict) -> int | None:
    return f.get('filesize') or f.get('filesize_approx')


def has_video(info: dict) -> bool:
    """False only when we are sure the source is audio-only (e.g. SoundCloud)."""
    formats = info.get('formats') or []
    if not formats:
        return True
    return any(f.get('vcodec') != 'none' for f in formats)   # unknown codec -> assume video


def video_qualities(info: dict) -> list[Quality]:
    """One entry per resolution (highest first) describing what the selector will pick."""
    formats = info.get('formats') or []
    by_height: dict[int, list[dict]] = {}
    for f in formats:
        if _has_video(f):
            by_height.setdefault(int(f['height']), []).append(f)
    if not by_height:
        return []

    audio_sizes = [_size(f) for f in formats if _has_audio(f) and not _has_video(f) and _size(f)]
    best_audio = max(audio_sizes) if audio_sizes else 0

    result = []
    for height in sorted(by_height, reverse=True):
        # same preference as the format_sort used when downloading: h264 first, then bitrate
        best = max(by_height[height], key=lambda f: (
            short_codec(f.get('vcodec')) == 'h264', f.get('tbr') or 0))
        size = _size(best)
        if size and not _has_audio(best):
            size += best_audio
        result.append(Quality(
            height=height,
            fps=int(best['fps']) if best.get('fps') else None,
            ext=best.get('ext') or '?',
            codec=short_codec(best.get('vcodec')),
            size=size,
        ))
    return result
