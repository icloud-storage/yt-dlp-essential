"""`essn` — entry point and the guided download flow."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, config, gallery, ui
from .engine import (
    Plan, Session, clean_error, ffmpeg_available, installed_browsers,
    js_runtime_available, needs_cookies, pretty_platform,
)
from .formats import has_video, video_qualities
from .parsing import ItemsError, RangeError, format_duration, parse_items, parse_range

PLAYLIST_HEIGHTS = [None, 1080, 720, 480]   # None = best
CONTAINERS = [('mp4', 'MP4 — plays everywhere'), ('mkv', 'MKV — keeps any codec'), ('webm', 'WebM — open web format')]
AUDIO_FORMATS = [('mp3', 'MP3 — works everywhere'), ('m4a', 'M4A / AAC — best for Apple devices'),
                 ('opus', 'Opus — small and modern'), ('flac', 'FLAC — lossless'), ('wav', 'WAV — uncompressed')]
AUDIO_QUALITIES = [(None, 'Best available'), ('320', '320 kbps'), ('192', '192 kbps'), ('128', '128 kbps')]
LOSSLESS = {'flac', 'wav'}
IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'avif', 'heic', 'tiff'}
GALLERY_KINDS = {'stories': 'stories', 'story': 'stories', 'pinit': 'pin'}
HELP = f"""essential {__version__} — simple video and audio downloader

  essn            open the menu
  essn <link>     analyze a link and download
  essn --help     this help
  essn --version  version"""


# ── input helpers ─────────────────────────────────────────────

def normalize_url(raw: str) -> str | None:
    raw = (raw or '').strip().strip('"\'<>')
    if not raw or ' ' in raw:
        return None
    if '://' not in raw:
        if '.' not in raw.split('/')[0]:
            return None
        raw = 'https://' + raw
    p = urlparse(raw)
    return raw if p.scheme in ('http', 'https') and p.netloc else None


def video_and_list(url: str) -> bool:
    q = parse_qs(urlparse(url).query)
    return 'v' in q and 'list' in q


# ── cookies ───────────────────────────────────────────────────

def offer_cookies(session: Session, cfg: dict) -> bool:
    """Say that cookies are needed and offer to extract them. True if a browser was chosen."""
    ui.note('Cookies are required for this link (login, age check or bot check)')
    if not ui.confirm('Extract cookies from your browser automatically?', True):
        return False
    browsers = installed_browsers()
    saved = cfg.get('cookies_browser')
    default = browsers.index(saved) + 1 if saved in browsers else 1
    idx = ui.choose('Which browser are you logged in with?', [b.capitalize() for b in browsers], default)
    session.cookies_browser = browsers[idx]
    cfg['cookies_browser'] = browsers[idx]
    config.save(cfg)
    ui.step('Cookies', browsers[idx].capitalize())
    ui.note('macOS may ask for permission (Keychain, or Full Disk Access for Safari) — allow it')
    return True


def probe_with_cookies(session: Session, cfg: dict, url: str, noplaylist: bool = False):
    tried_cookies = session.cookies_browser is not None
    while True:
        try:
            with ui.task('Analyzing link'):
                return session.probe(url, noplaylist=noplaylist)
        except (ui.Abort, KeyboardInterrupt):
            raise
        except Exception as e:  # noqa: BLE001 — yt-dlp raises many types
            msg = clean_error(e)
            if 'unsupported url' in msg.lower():
                session.unsupported = True
                if not (gallery.available() and gallery.identify(url)):
                    ui.fail('This site or link is not supported (or has no downloadable media)')
                return None
            if needs_cookies(msg):
                if tried_cookies:
                    ui.fail(msg)
                    ui.note(f'Still failing with cookies — make sure you are logged in to the site in '
                            f'{(session.cookies_browser or "?").capitalize()}')
                    return None
                if offer_cookies(session, cfg):
                    tried_cookies = True
                    continue
            ui.fail(msg)
            return None


# ── choices ───────────────────────────────────────────────────

def choose_fragment(info: dict):
    """Returns (start, end|None) in seconds, or None for the whole video."""
    if info.get('is_live'):
        ui.note('Live stream — it will be downloaded from the start')
        return None
    if ui.choose('Whole video or a fragment?', ['Whole video', 'Fragment only'], 1) == 0:
        ui.step('Range', 'whole video')
        return None
    ui.say('  ' + ui.grey('Time range, for example  0:30-1:45'))
    while True:
        text = ui.ask('Range')
        try:
            start, end = parse_range(text, info.get('duration'))
        except RangeError as e:
            ui.note(str(e))
            continue
        end_txt = format_duration(end) if end is not None else 'end'
        ui.step('Range', f'{format_duration(start)} → {end_txt}')
        return start, end


def choose_media(info: dict | None, plan: Plan, qualities=None, audio_only: bool = False) -> None:
    """Mode → format → quality. `info` is None for playlists (generic quality presets)."""
    if audio_only:
        plan.kind = 'audio'
    else:
        plan.kind = 'video' if ui.choose('What to download?', ['Video + Audio', 'Only Audio'], 1) == 0 else 'audio'
    ui.step('Mode', 'Video + Audio' if plan.kind == 'video' else 'Only Audio')

    if plan.kind == 'video':
        idx = ui.choose('Format', [label for _, label in CONTAINERS], 1)
        plan.container = CONTAINERS[idx][0]
        ui.step('Format', plan.container.upper())
        if qualities:
            options = [f'Best available  ({qualities[0].label()})'] + [q.label() for q in qualities]
            idx = ui.choose('Quality', options, 1)
            chosen = qualities[0 if idx == 0 else idx - 1]
            plan.height = None if idx == 0 else chosen.height
            plan.est_size = chosen.size
            ui.step('Quality', chosen.label())
        elif info is None:
            options = ['Best available'] + [f'Up to {h}p' for h in PLAYLIST_HEIGHTS[1:]]
            idx = ui.choose('Quality', options, 1)
            plan.height = PLAYLIST_HEIGHTS[idx]
            ui.step('Quality', options[idx])
        else:
            ui.step('Quality', 'best available')
    else:
        idx = ui.choose('Format', [label for _, label in AUDIO_FORMATS], 1)
        plan.audio_fmt = AUDIO_FORMATS[idx][0]
        ui.step('Format', plan.audio_fmt.upper())
        if plan.audio_fmt in LOSSLESS:
            ui.step('Quality', 'lossless')
        else:
            idx = ui.choose('Quality', [label for _, label in AUDIO_QUALITIES], 1)
            plan.audio_quality = AUDIO_QUALITIES[idx][0]
            ui.step('Quality', AUDIO_QUALITIES[idx][1])


def choose_single(info: dict, plan: Plan) -> None:
    qualities = video_qualities(info)
    choose_media(info, plan, qualities, audio_only=not has_video(info))
    plan.fragment = choose_fragment(info) if plan.kind == 'video' else None
    if plan.fragment and plan.est_size and info.get('duration'):
        start, end = plan.fragment
        span = (end if end is not None else info['duration']) - start
        plan.est_size = int(plan.est_size * max(0.0, span) / info['duration'])
    elif plan.fragment:
        plan.est_size = None


def is_section_list(info: dict, entries: list) -> bool:
    if not entries:
        return False
    own = info.get('extractor_key')
    return all(e.get('_type') == 'playlist' or (e.get('ie_key') and e.get('ie_key') == own) for e in entries)


def show_entries(entries: list) -> None:
    limit = max(5, min(50, ui.rows() - 14))
    for i, e in enumerate(entries[:limit], 1):
        ui.say(f'  {ui.grey(f"{i:>3}.")} {ui.shorten(e.get("title") or e.get("url") or e.get("id") or "?", ui.cols() - 12)}')
    if len(entries) > limit:
        ui.say('  ' + ui.grey(f'… and {len(entries) - limit} more (numbers follow the order on the site)'))


def choose_items(total: int) -> str | None:
    if ui.choose('Download everything or only some items?', ['Everything', 'Choose items'], 1) == 0:
        return None
    ui.say('  ' + ui.grey('Numbers separated by commas, ranges with a dash — for example  1,3,5-8'))
    while True:
        try:
            return parse_items(ui.ask('Items'), total)
        except ItemsError as e:
            ui.note(f'Could not read the list: {e}')


def pick_targets(session: Session, cfg: dict, url: str, info: dict, entries: list):
    """Resolve channel sections. Returns [(url, info, entries)] or None."""
    if not is_section_list(info, entries):
        return [(info.get('webpage_url') or url, info, entries)]
    options = [e.get('title') or e.get('url') for e in entries] + ['All sections']
    idx = ui.choose('This channel has several sections', options, 1)
    ui.step('Section', options[idx])
    chosen = entries if idx == len(entries) else [entries[idx]]
    targets = []
    for e in chosen:
        sub = probe_with_cookies(session, cfg, e['url'])
        if sub is None:
            return None
        targets.append((e['url'], sub, [x for x in (sub.get('entries') or []) if x]))
    return targets


def _short(p: Path) -> str:
    home = str(Path.home())
    return '~' + str(p)[len(home):] if str(p).startswith(home) else str(p)


def pick_base_dir(cfg: dict) -> Path | None:
    """The saved folder, or (if asking is on) a choice between it and a new one.
    A newly chosen folder becomes the saved one, so the menu shows it too."""
    base = config.base_download_dir(cfg)
    if cfg.get('ask_dir_each_time'):
        idx = ui.choose('Where to save?', [f'{_short(base)}   (current folder)', 'Choose a new folder…'], 1)
        if idx == 1:
            while True:
                candidate = Path(ui.ask('New folder', str(base))).expanduser()
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    break
                except OSError as e:
                    ui.note(f'Cannot use this folder: {e}')
            base = candidate
            cfg['download_dir'] = None if base == config.default_download_dir() else str(base)
            config.save(cfg)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        ui.fail(f'Cannot use the download folder: {e}')
        return None
    return base


def _gallery_flow(cfg: dict, session: Session, url: str, result: dict) -> int:
    """Posts, pins and stories (Instagram, Pinterest, …) via gallery-dl."""
    from .engine import PRETTY_PLATFORMS
    category, sub = gallery.identify(url) or ('?', '')
    name = PRETTY_PLATFORMS.get(category) or category.capitalize()
    kind = GALLERY_KINDS.get(sub, sub)
    ui.step('Platform', f'{name} ({kind})' if kind and kind != 'post' else name)

    while True:
        with ui.task('Analyzing link'):
            count, problems = gallery.count_items(url, session.cookies_browser)
        if count:
            break
        text = ' '.join(problems)
        if gallery.needs_login(text) and session.cookies_browser is None and offer_cookies(session, cfg):
            continue
        ui.fail(problems[0] if problems else 'Nothing to download here')
        return 1
    ui.step('Items', str(count))

    items = None
    if count > 1:
        items = choose_items(count)
        ui.refresh('Download')
        ui.step('Link', url)
        ui.step('Platform', f'{name} ({kind})' if kind and kind != 'post' else name)
        ui.step('Items', str(count) if items is None else f'{count}  (selected {items})')
    base = pick_base_dir(cfg)
    if base is None:
        return 1
    outdir = base / 'gallery'
    ui.step('Folder', str(outdir))
    ui.say()

    total = count if items is None else None
    state = {'n': 0, 'skipped': 0}

    def on_file(path: Path, skipped: bool) -> None:
        state['n'] += 1
        state['skipped'] += bool(skipped)
        ui.progress_line((state['n'] / total) if total else None,
                         f'{state["n"]}' + (f'/{total}' if total else '') + f'  {ui.shorten(path.name, 36)}')

    def run():
        state.update(n=0, skipped=0)
        ui.progress_line(0.0 if total else None, 'starting…')
        with ui.no_echo():
            return gallery.download(url, outdir, items, session.cookies_browser, on_file)

    files, errors = run()
    if errors and session.cookies_browser is None and gallery.needs_login(' '.join(errors)):
        if offer_cookies(session, cfg):
            files, errors = run()
    ui.clear_line()
    for e in errors:
        ui.fail(e)
    if files:
        new = len(files) - state['skipped']
        ui.step('Saved', f'{new} file(s)' + (f', {state["skipped"]} already existed' if state['skipped'] else ''))
        ui.say()
        ui.say('  ' + (ui.green('Done') if not errors else ui.yellow(f'Finished with {len(errors)} error(s)')))
        result['folder'] = outdir
        return 0 if not errors else 2
    return 1


# ── the flow ──────────────────────────────────────────────────

def _download_flow(cfg: dict, url: str | None, result: dict) -> int:
    ui.reset()
    ui.refresh('Download')

    if not url:
        while True:
            url = normalize_url(ui.ask('Paste a link'))
            if url:
                break
            if not ui.interactive():
                ui.fail('That does not look like a link')
                return 1
            ui.note('That does not look like a link (it should start with http:// or https://)')
    else:
        url = normalize_url(url)
        if url is None:
            ui.fail('That does not look like a link (it should start with http:// or https://)')
            return 1
    ui.step('Link', url)

    session = Session()
    if gallery.available() and gallery.prefers(url):
        return _gallery_flow(cfg, session, url, result)

    if not ffmpeg_available():
        ui.note('ffmpeg is not installed — needed for merging, audio and fragments: brew install ffmpeg')

    noplaylist = False
    info = probe_with_cookies(session, cfg, url)
    if info is None:
        if session.unsupported and gallery.available() and gallery.identify(url):
            return _gallery_flow(cfg, session, url, result)
        return 1
    if (info.get('extractor') == 'generic' and str(info.get('ext', '')).lower() in IMAGE_EXTS
            and gallery.available() and gallery.identify(url)):
        return _gallery_flow(cfg, session, url, result)      # a plain image link, not a video

    if info.get('_type') == 'playlist' and video_and_list(url):
        if ui.choose('This link is a video inside a playlist', ['Only this video', 'The whole playlist'], 1) == 0:
            noplaylist = True
            info = probe_with_cookies(session, cfg, url, noplaylist=True)
            if info is None:
                return 1

    ui.step('Platform', pretty_platform(info))
    if 'youtube' in str(info.get('extractor', '')).lower() and not js_runtime_available():
        ui.note('YouTube needs a JavaScript runtime — install it with: brew install deno')

    all_files: list[Path] = []
    all_errors: list[str] = []

    if info.get('_type') == 'playlist':
        entries = [e for e in (info.get('entries') or []) if e]
        targets = pick_targets(session, cfg, url, info, entries)
        if targets is None:
            return 1
        ui.step('Playlist', targets[0][1].get('title') or '')
        if len(targets) > 1:
            ui.step('Items', ', '.join(f'{ti.get("title")}: {len(te)}' for _, ti, te in targets))
            items = None
        else:
            tentries = targets[0][2]
            if not tentries:
                ui.fail('Nothing to download here')
                return 1
            ui.step('Items', str(len(tentries)))
            ui.say()
            show_entries(tentries)
            ui.say()
            items = choose_items(len(tentries))
            ui.refresh('Download')
            ui.step('Selected', 'everything' if items is None else items)
        template = Plan(outdir=Path('.'), is_playlist=True, items=items)
        choose_media(None, template)
        base = pick_base_dir(cfg)
        if base is None:
            return 1
        plans = [(turl, Plan(outdir=base, kind=template.kind, container=template.container, height=template.height,
                             audio_fmt=template.audio_fmt, audio_quality=template.audio_quality,
                             items=items, is_playlist=True))
                 for turl, _, _ in targets]
    else:
        ui.step('Title', info.get('title') or '?')
        if info.get('uploader') or info.get('channel'):
            ui.step('Author', info.get('uploader') or info.get('channel'))
        if info.get('duration'):
            ui.step('Duration', format_duration(info['duration']))
        plan = Plan(outdir=Path('.'))
        choose_single(info, plan)
        base = pick_base_dir(cfg)
        if base is None:
            return 1
        plan.outdir = base
        plans = [(info.get('webpage_url') or url, plan)]

    ui.step('Folder', str(plans[0][1].target_dir))
    ui.say()

    def saved(path: Path) -> None:
        ui.step('Saved', path.name)

    def download(turl, plan):
        with ui.no_echo():
            return session.download(turl, plan, on_file=saved)

    for turl, plan in plans:
        files, errors = download(turl, plan)
        if errors and session.cookies_browser is None and any(needs_cookies(e) for e in errors):
            if offer_cookies(session, cfg):
                files2, errors = download(turl, plan)
                files += files2
        all_files += files
        all_errors += errors

    for e in all_errors:
        ui.fail(e)
    unique = list(dict.fromkeys(all_files))
    if unique:
        ui.say()
        ui.say('  ' + (ui.green('Done') if not all_errors else ui.yellow(f'Finished with {len(all_errors)} error(s)')))
        result['folder'] = unique[0].parent
        return 0 if not all_errors else 2
    return 1


def run_download(cfg: dict, url: str | None = None) -> int:
    """Run the guided flow, then hold the screen so the result can be read."""
    result: dict = {}
    code = _download_flow(cfg, url, result)
    if ui.interactive():
        if result.get('folder') and sys.platform == 'darwin':
            key = ui.wait_key('Any other key to continue', extra='O  Open in Finder  |  ')
            if key.lower() == 'o':
                subprocess.run(['open', str(result['folder'])], check=False)
        else:
            ui.wait_key('Press any key to continue')
    return code


# ── entry point ───────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    from . import menu

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] in (['-h'], ['--help']):
        ui.say(HELP)
        return 0
    if argv[:1] in (['-V'], ['--version']):
        import yt_dlp
        ui.say(f'essential {__version__} (yt-dlp {yt_dlp.version.__version__})')
        return 0

    cfg = config.load()
    url = argv[0] if argv else None
    code = 0
    try:
        with ui.fullscreen():
            if url:
                code = run_download(cfg, url)
            else:
                code = menu.run(cfg)
        if url and ui.interactive():
            ui.dump_session()
    except menu.Restart:
        import os
        os.execv(sys.executable, [sys.executable, '-m', 'yt_essential'])
    except (ui.Abort, KeyboardInterrupt):
        if url and ui.interactive():
            ui.dump_session()
        return 130
    return code


if __name__ == '__main__':
    sys.exit(main())
