"""The only module that talks to yt-dlp."""
from __future__ import annotations

import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError, download_range_func

from . import ui
from .parsing import format_size

AUDIO_CODECS = {'mp3': 'mp3', 'm4a': 'm4a', 'opus': 'opus', 'flac': 'flac', 'wav': 'wav'}

BROWSERS = [  # (yt-dlp key, macOS app name)
    ('safari', 'Safari'),
    ('chrome', 'Google Chrome'),
    ('firefox', 'Firefox'),
    ('brave', 'Brave Browser'),
    ('edge', 'Microsoft Edge'),
    ('chromium', 'Chromium'),
    ('opera', 'Opera'),
    ('vivaldi', 'Vivaldi'),
]

PRETTY_PLATFORMS = {
    'youtube': 'YouTube', 'vimeo': 'Vimeo', 'twitter': 'X (Twitter)', 'tiktok': 'TikTok',
    'instagram': 'Instagram', 'soundcloud': 'SoundCloud', 'twitch': 'Twitch', 'facebook': 'Facebook',
    'reddit': 'Reddit', 'bilibili': 'Bilibili', 'vk': 'VK', 'rutube': 'Rutube',
    'dailymotion': 'Dailymotion', 'odnoklassniki': 'OK.ru', 'bandcamp': 'Bandcamp',
    'telegram': 'Telegram', 'vkplay': 'VK Play', 'dzen': 'Дзен', 'kick': 'Kick',
}

_COOKIE_HINTS = (
    'sign in', 'log in', 'login', 'logged in', 'cookies', 'confirm you', 'not a bot',
    'private video', 'members-only', 'members only', 'age-restricted', 'confirm your age',
    'registered users', 'authentication', 'requires authorization', 'account', 'premium',
)


# ── small pure helpers ────────────────────────────────────────

def needs_cookies(message: str) -> bool:
    m = (message or '').lower()
    return any(h in m for h in _COOKIE_HINTS)


def pretty_platform(info: dict) -> str:
    raw = str(info.get('extractor') or info.get('extractor_key') or '')
    base = raw.split(':')[0].lower()
    if base == 'generic':
        return 'Unknown site (generic)'
    return PRETTY_PLATFORMS.get(base) or (base.capitalize() if base else '?')


def installed_browsers() -> list[str]:
    """Browser keys, installed ones first (macOS). Falls back to the full list elsewhere."""
    roots = [Path('/Applications'), Path.home() / 'Applications']
    found = [k for k, app in BROWSERS if any((r / f'{app}.app').exists() for r in roots)]
    rest = [k for k, _ in BROWSERS if k not in found]
    return found + rest if found else [k for k, _ in BROWSERS]


def clean_error(exc: BaseException) -> str:
    msg = re.sub(r'\x1b\[[0-9;]*m', '', str(exc))
    msg = re.sub(r'^(ERROR:\s*)+', '', msg.strip())
    return msg


# ── plan → yt-dlp options ─────────────────────────────────────

@dataclass
class Plan:
    outdir: Path                    # base folder (e.g. ~/Downloads/yt-essential)
    kind: str = 'video'             # 'video' | 'audio'
    container: str = 'mp4'          # video: mp4 | mkv | webm
    height: int | None = None       # None = best
    audio_fmt: str = 'mp3'
    audio_quality: str | None = None   # None = best, else kbps like '192'
    items: str | None = None        # playlist_items, e.g. '1,3,5-8'
    is_playlist: bool = False
    fragment: tuple[float, float | None] | None = None   # seconds (start, end)
    est_size: int | None = None     # expected size in bytes (for progress when yt-dlp can't tell)

    @property
    def target_dir(self) -> Path:
        return self.outdir / self.kind


def format_selector(height: int | None) -> str:
    if height:
        return f'bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b'
    return 'bv*+ba/b'


def output_template(plan: Plan) -> str:
    if plan.is_playlist:
        return '%(playlist_title|Playlist).120B/%(playlist_index)03d - %(title).150B.%(ext)s'
    suffix = ''
    if plan.fragment:
        s, e = plan.fragment
        suffix = f' [{int(s)}-{int(e)}s]' if e is not None else f' [from {int(s)}s]'
    return f'%(title).150B{suffix}.%(ext)s'


def build_download_opts(plan: Plan) -> dict:
    opts: dict = {
        'paths': {'home': str(plan.target_dir)},
        'outtmpl': {'default': output_template(plan)},
        'windowsfilenames': False,
        'noplaylist': not plan.is_playlist,
        'continuedl': True,
        'retries': 10,
        'fragment_retries': 10,
    }
    if plan.items:
        opts['playlist_items'] = plan.items
    if plan.is_playlist:
        opts['ignoreerrors'] = 'only_download'

    if plan.kind == 'audio':
        opts['format'] = 'bestaudio/best'
        pp = {'key': 'FFmpegExtractAudio', 'preferredcodec': AUDIO_CODECS.get(plan.audio_fmt, 'mp3')}
        if plan.audio_quality:
            pp['preferredquality'] = plan.audio_quality
        elif plan.audio_fmt == 'mp3':
            pp['preferredquality'] = '0'          # best VBR
        opts['postprocessors'] = [pp, {'key': 'FFmpegMetadata', 'add_metadata': True}]
    else:
        opts['format'] = format_selector(plan.height)
        sorts = {
            'mp4': ['res', 'vcodec:h264', 'acodec:m4a'],     # plays everywhere (QuickTime)
            'mkv': ['res'],                                  # any codec fits
            'webm': ['res', 'vcodec:vp9', 'acodec:opus'],
        }
        opts['format_sort'] = sorts.get(plan.container, sorts['mp4'])
        opts['merge_output_format'] = plan.container
        pps = []
        if plan.container in ('mp4', 'mkv'):
            pps.append({'key': 'FFmpegVideoRemuxer', 'preferedformat': plan.container})
        pps.append({'key': 'FFmpegMetadata', 'add_metadata': True})
        opts['postprocessors'] = pps

    if plan.fragment and not plan.is_playlist:
        s, e = plan.fragment
        opts['download_ranges'] = download_range_func([], [(s, e if e is not None else float('inf'))])
        opts['force_keyframes_at_cuts'] = True
    return opts


# ── session / runner ──────────────────────────────────────────

class _Logger:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def debug(self, msg):  # noqa: D401
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        msg = clean_error(msg)
        if msg not in self.warnings:
            self.warnings.append(msg)
            ui.note(msg)

    def error(self, msg):
        self.errors.append(clean_error(msg))


class _Progress:
    """One-line progress: spinner, bar, percent, sizes, speed, ETA. Fed by yt-dlp's hooks."""

    def __init__(self):
        self.frame = 0
        self.last_hook = 0.0
        self._lock = threading.Lock()

    def draw(self, frac, done, total, speed, eta, prefix='', approx=False):
        pct = f'{frac * 100:5.1f}%' if frac is not None else '   …  '
        size = format_size(done)
        if total:
            size += f' / {"≈ " if approx else ""}{format_size(total)}'
        speed_s = f'{format_size(speed)}/s' if speed else ''
        eta_s = f'ETA {int(eta) // 60:02d}:{int(eta) % 60:02d}' if eta is not None and eta >= 0 else ''
        spin = ui.accent(ui.SPINNER[self.frame % len(ui.SPINNER)])
        self.frame += 1
        line = f'  {spin} {prefix}{ui.bar(frac)} {pct}  {size}  {ui.grey(speed_s)}  {ui.grey(eta_s)}'
        with self._lock:
            sys.stdout.write('\r\033[2K' + line)
            sys.stdout.flush()

    def __call__(self, d: dict) -> None:
        if not ui.interactive():
            return
        self.last_hook = time.time()
        st = d.get('status')
        if st == 'downloading':
            done = d.get('downloaded_bytes') or 0
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            info = d.get('info_dict') or {}
            prefix = ''
            if info.get('playlist_index') and info.get('n_entries'):
                prefix = ui.grey(f'[{info["playlist_index"]}/{info["n_entries"]}] ')
            self.draw(done / total if total else None, done, total, d.get('speed'), d.get('eta'),
                      prefix, approx=not d.get('total_bytes'))
        elif st == 'finished':
            with self._lock:
                sys.stdout.write('\r\033[2K  ' + ui.grey('⠿ Processing…'))
                sys.stdout.flush()


class _GrowthWatcher(threading.Thread):
    """ffmpeg-based downloads (fragments, some HLS) give no progress events. This watches the
    files growing in the target folder and draws the same bar from that."""

    def __init__(self, progress: _Progress, directory: Path, est_size: int | None):
        super().__init__(daemon=True)
        self.progress, self.directory, self.est = progress, directory, est_size
        self.t0 = time.time()
        self.stop_event = threading.Event()
        self.samples: list[tuple[float, int]] = []

    def _bytes(self) -> int:
        total = 0
        try:
            for p in self.directory.rglob('*'):
                try:
                    st = p.stat()
                except OSError:
                    continue
                if p.is_file() and st.st_mtime >= self.t0 - 1:
                    total += st.st_size
        except OSError:
            pass
        return total

    def run(self):
        while not self.stop_event.wait(0.3):
            if time.time() - self.progress.last_hook < 1.5:
                continue                              # yt-dlp is reporting by itself
            now, done = time.time(), self._bytes()
            self.samples = [(t, b) for t, b in self.samples if now - t <= 3] + [(now, done)]
            speed = None
            if len(self.samples) > 1 and now > self.samples[0][0]:
                speed = max(0, (done - self.samples[0][1]) / (now - self.samples[0][0]))
            frac = eta = None
            if self.est:
                frac = min(0.99, done / self.est)
                if speed and self.est > done:
                    eta = (self.est - done) / speed
            self.progress.draw(frac, done, self.est, speed, eta, approx=True)

    def stop(self):
        self.stop_event.set()
        self.join(timeout=1)


class Session:
    """Holds per-run state (cookie browser chosen for this run)."""

    def __init__(self, cookies_browser: str | None = None):
        self.cookies_browser = cookies_browser
        self.unsupported = False

    def base_opts(self, logger: _Logger) -> dict:
        opts: dict = {
            'quiet': True,
            'noprogress': True,
            'logger': logger,
            'color': {'stdout': 'never', 'stderr': 'never'},
        }
        if self.cookies_browser:
            opts['cookiesfrombrowser'] = (self.cookies_browser,)
        if not shutil.which('deno') and shutil.which('node'):
            opts['js_runtimes'] = {'node': {}}
        return opts

    def probe(self, url: str, noplaylist: bool = False) -> dict:
        logger = _Logger()
        opts = self.base_opts(logger)
        opts.update({'skip_download': True, 'extract_flat': 'in_playlist', 'noplaylist': noplaylist})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            raise DownloadError(logger.errors[-1] if logger.errors else 'Unsupported URL')
        return info

    def resolve_entries(self, url: str) -> dict:
        """Flat-extract a nested section URL (used for channel tabs)."""
        return self.probe(url)

    def download(self, url: str, plan: Plan, on_file=None) -> tuple[list[Path], list[str]]:
        logger = _Logger()
        files: list[Path] = []
        opts = self.base_opts(logger)
        opts.update(build_download_opts(plan))
        progress = _Progress()
        opts['progress_hooks'] = [progress]

        def _got(p):
            files.append(Path(p))
            if on_file:
                on_file(Path(p))

        opts['post_hooks'] = [_got]
        plan.target_dir.mkdir(parents=True, exist_ok=True)
        watcher = _GrowthWatcher(progress, plan.target_dir, plan.est_size) if ui.interactive() else None
        if watcher:
            watcher.start()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except DownloadError as e:
            logger.errors.append(clean_error(e))
        finally:
            if watcher:
                watcher.stop()
        errors = [e for e in dict.fromkeys(logger.errors) if e]
        return files, errors


def ffmpeg_available() -> bool:
    return shutil.which('ffmpeg') is not None


def js_runtime_available() -> bool:
    return bool(shutil.which('deno') or shutil.which('node') or shutil.which('bun'))
