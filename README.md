# yt-dlp Essential

**Download video and audio from almost any website with a few simple questions — no flags, no formats to memorise.**
A friendly terminal front-end for [yt-dlp](https://github.com/yt-dlp/yt-dlp) (and, as an extra, [gallery-dl](https://github.com/mikf/gallery-dl)), built for macOS.

## Install (one command)

Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/icloud-storage/yt-dlp-essential/main/install.sh | bash
```

The installer installs the missing pieces through Homebrew (`ffmpeg`, a JavaScript runtime for YouTube, Python if needed)
and puts one command on your PATH: `essn`. Everything lives in `~/.yt-essential`; nothing needs `sudo`.

**Without GitHub (local copy)** (from an unpacked copy of this folder):

```bash
cd yt-dlp-essential && YTES_SOURCE="$PWD" bash install.sh
```

## Use

```text
essn                  # opens the menu
essn <link>           # analyzes the link and starts straight away
```

`essn` clears the terminal and shows a minimal menu (↑↓ + Enter, or press a number; `U` update, `V` version, `Q` quit). When a new
yt-dlp (or gallery-dl) version exists, a notice with the current and the new version appears at the top.

What the download flow does, step by step (every finished step gets a ✓):

1. **Detects the platform** automatically (YouTube, Vimeo, X, TikTok, SoundCloud, VK, … — whatever yt-dlp supports, ~1,000 sites).
2. **Single video** — *1. Video + Audio / 2. Only Audio*. Then the **format** (MP4, MKV, WebM — or MP3, M4A, Opus, FLAC, WAV for audio),
   then the **quality** (`1080p · 60fps · mp4 (h264) · ≈ 140 MB`; for lossy audio: best / 320 / 192 / 128 kbps).
   Then **whole video or a fragment**: type one range, e.g. `0:30-1:45`. (Shortcuts: `0-90` = seconds, `1:00-` = to the end.)
   A progress bar shows percent, size, speed and time left.
3. **Playlist or channel** — shows the numbered list and asks **everything or only some**.
   Type numbers separated by commas and ranges with a dash: `1,3,5-8`. Channels with several sections
   (Videos / Shorts / Live) ask which section you want, or all of them.
4. **Needs a login?** If a site asks for sign-in, an age check or a bot check, it says so and **offers to extract cookies
   from your browser automatically** (Safari, Chrome, Firefox, Brave, Edge, …), then retries.
5. **Where to save** — before downloading you choose between the saved folder and a new one. A new folder becomes the saved one
   (the menu shows it). Turn the question off with the *Ask folder* menu item.
6. **Tidy output** — files go to `~/Downloads/yt-essential/` and are split into `audio/` and `video/`.
   Playlists get their own sub-folder with numbered files.

**Images, posts and stories (extra).** Links from Instagram (posts, reels, stories, profiles) and Pinterest (pins, boards) — and
plain image links — are handled automatically through gallery-dl. Same flow, same `essn` command; files go to a `gallery/`
sub-folder of your chosen folder (`gallery/instagram/<user>/…`). Instagram usually needs login: allow the cookie offer.

### Menu items

| Item | What it does |
|---|---|
| Download | Paste a link and follow the steps |
| Folder | Where files go (default `~/Downloads/yt-essential`) |
| Ask folder | On: before each download choose the saved folder or a new one. Off: always the saved folder |
| Cookies | Remember which browser to take cookies from |
| Update | Updates yt-dlp and gallery-dl (websites change often — update when something stops working) |

Settings are stored in `~/.config/yt-essential/config.json`.

### macOS notes

* **Cookies from Safari** need *Full Disk Access* for Terminal (System Settings → Privacy & Security). Chrome/Brave/Edge may show a Keychain prompt — click *Allow*.
* Videos are saved as `.mp4` with H.264/AAC whenever the site offers it, so they play in QuickTime. Very high resolutions (4K+) are often VP9/AV1 and may end up in `.mkv`.

## Update / uninstall

Updates are announced in the menu. When a newer version of essential (the version number in this repository's `main` branch),
yt-dlp or gallery-dl exists, the menu shows *current → new*; press `U` to update everything at once and the app restarts itself.

```bash
essn                      # menu → Update (or press U)
bash install.sh --uninstall
```

## How it relates to yt-dlp

This project does **not** copy yt-dlp's or gallery-dl's source. It is a thin layer (`yt_essential/`) that uses yt-dlp as a library and
installs the official `yt-dlp` and `gallery-dl` packages as dependencies. That is deliberate: sites break every few days and yt-dlp ships fixes
constantly, so you always get the latest extractors by updating — there is no fork to keep in sync.

## For developers

```bash
git clone https://github.com/icloud-storage/yt-dlp-essential && cd yt-dlp-essential
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
python -m unittest discover -s tests -t . -v        # ffmpeg needed for the end-to-end tests
```

Layout: `cli.py` (the dialogue and entry point), `menu.py` (main menu), `ui.py` (full-screen UI, keys, spinner),
`engine.py` (the only module that touches yt-dlp), `gallery.py` (gallery-dl), `formats.py` (quality menu), `parsing.py` (`1,3,5-8` and time ranges),
`updates.py` (new-version check), `config.py`.

## Credits

Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) and [gallery-dl](https://github.com/mikf/gallery-dl) (GPL-2.0), which are
installed as separate dependencies and are not bundled here. All the downloading work is theirs.

Please respect the terms of service of the sites you download from and the rights of content owners. Released into the public domain (Unlicense), like yt-dlp.

## Releasing an update (for the maintainer)

Bump the version in **both** `yt_essential/__init__.py` (`__version__`) and `pyproject.toml`, commit and push to `main`.
Everyone's menu then shows *essential 1.1.0 → 1.2.0* within about six hours (or immediately via *Update*).
