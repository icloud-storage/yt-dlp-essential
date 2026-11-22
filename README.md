# yt-dlp Essential

**Download video and audio from almost any website with a few simple questions — no flags, no formats to memorise.**

A friendly terminal front-end for [yt-dlp](https://github.com/yt-dlp/yt-dlp) (and, as an extra, [gallery-dl](https://github.com/mikf/gallery-dl)), built for macOS and Windows.

## Installation

### macOS

Open **Terminal** and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/icloud-storage/yt-dlp-essential/main/install.sh | bash
```

The installer installs missing dependencies through Homebrew (FFmpeg, a JavaScript runtime for YouTube, and Python if needed) and puts `essn` on your PATH. Program files and the virtual environment live in `~/.yt-essential`; no `sudo` is required.

For a local checkout:

```bash
cd yt-dlp-essential && YTES_SOURCE="$PWD" bash install.sh
```

### Windows 10/11 (x64)

Supported baseline: **Windows 10 version 1709 (build 16299) or later, or Windows 11; 64-bit; Windows PowerShell 5.1 or PowerShell 7+.**

1. Download the repository using **Code → Download ZIP**, or clone it:

   ```powershell
   git clone https://github.com/icloud-storage/yt-dlp-essential.git
   cd yt-dlp-essential
   ```

2. Open PowerShell in the extracted repository folder (the folder containing `pyproject.toml` and `windows\`).
3. Run the installer:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass -Force
   .\windows\install.ps1
   ```

   Alternatively, double-click `windows\install.bat`.
4. Open a **new** PowerShell or Windows Terminal window and run:

   ```powershell
   essn
   ```

The installer checks for 64-bit Python 3.10+, FFmpeg/ffprobe, and Deno 2.3+. If WinGet is available, it attempts to install missing Python, FFmpeg, and Deno packages. WinGet is optional: if it is unavailable or a package installation fails, install the missing component manually and rerun the installer. Do not start PowerShell as Administrator pre-emptively; WinGet may request elevation when a particular package requires it.

To skip automatic installation of system dependencies:

```powershell
.\windows\install.ps1 -SkipSystemDependencies
```

To install from a local checkout explicitly:

```powershell
.\windows\install.ps1 -SourcePath 'C:\path\to\yt-dlp-essential'
```

After a successful installation, `essn` is added to the current user's PATH. If Windows does not recognize the command immediately, open a new terminal window. The installer log is written to `%APPDATA%\yt-essential\logs`.

## Use

```text
essn                  # opens the menu
essn <link>           # analyzes the link and starts straight away
```

`essn` opens a guided menu (↑↓ + Enter, or press a number; `U` update, `V` version, `Q` quit). When a new yt-dlp or gallery-dl version exists, a notice with the current and new versions appears at the top.

What the download flow does, step by step (every finished step gets a ✓):

1. **Detects the platform** automatically (YouTube, Vimeo, X, TikTok, SoundCloud, VK, and other sites supported by yt-dlp).
2. **Single video** — choose Video + Audio or Only Audio, then a format (MP4, MKV, WebM, or MP3, M4A, Opus, FLAC, WAV for audio), quality, and optionally a time range such as `0:30-1:45` (`0-90` means seconds; `1:00-` means to the end).
3. **Playlist or channel** — download everything or select entries by numbers and ranges such as `1,3,5-8`. Channels with sections (Videos / Shorts / Live) let you choose a section.
4. **Login required?** If a site requires sign-in, an age check, or a bot check, the app offers to extract cookies from a supported browser and retry.
5. **Choose a destination** — use the saved folder or choose a new one. A new folder becomes the saved one; the folder prompt can be disabled from the menu.
6. **Organized output** — audio and video downloads are stored in separate subfolders. Playlists get their own subfolder with numbered files.

**Images, posts and stories (extra).** Instagram, Pinterest, and supported direct image links are handled through gallery-dl. Instagram commonly requires a valid logged-in session. Cookie extraction depends on the browser, profile, OS encryption and the site's current authentication requirements; selecting a browser does not itself mean that a valid session was extracted.

## Menu items

| Item | What it does |
|---|---|
| Download | Paste a link and follow the steps |
| Folder | Choose the destination folder |
| Ask folder | Choose the saved folder or a new one before each download |
| Cookies | Remember which browser to extract cookies from |
| Update | Update yt-dlp and gallery-dl (websites change often; update when something stops working) |

## Configuration and file locations

| Platform | Program files | Configuration | Default downloads |
|---|---|---|---|
| macOS | `~/.yt-essential` | `~/.config/yt-essential/config.json` | `~/Downloads/yt-essential` |
| Windows | `%LOCALAPPDATA%\yt-essential` | `%APPDATA%\yt-essential\config.json` | `%USERPROFILE%\Downloads\yt-essential` |

On Windows, logs are stored in `%APPDATA%\yt-essential\logs`. The compatibility layer also supports `YTES_CONFIG_DIR` as an explicit configuration-directory override.

## Dependencies

- **Python 3.10+ (64-bit on Windows)** — application runtime.
- **FFmpeg and ffprobe** — required for merging separate audio/video streams, audio extraction/conversion, and some fragment operations. Simple downloads of already-muxed streams may work without FFmpeg.
- **Deno 2.3+ (recommended for current YouTube JavaScript challenges)** — yt-dlp also needs its EJS companion package, installed through the declared yt-dlp dependency.
- **WinGet (Windows only, optional)** — used by the Windows installer to install missing system dependencies. Without WinGet, install them manually.

### Windows browser cookies

The Windows adapter offers installed browsers such as Edge, Chrome, Firefox, Brave, Vivaldi and Opera. The browser must contain an active session for the site being accessed. On some Windows/Chrome configurations, DPAPI or Chrome App-Bound Encryption can prevent third-party tools from decrypting cookies. Firefox may be used as an alternative if it contains a valid logged-in session. A successful cookie database read is not proof that the site session is authenticated; the site may still return `401 Unauthorized` or `403 Forbidden`.

## Update / uninstall

### macOS

Updates are announced in the menu. Press `U` to update the app, yt-dlp and gallery-dl. To uninstall:

```bash
bash install.sh --uninstall
```

### Windows

From the repository folder:

```powershell
.\windows\update.ps1
.\windows\doctor.ps1
.\windows\uninstall.ps1
```

The Windows uninstaller removes the installed program, virtual environment and PATH entry. It keeps the user's configuration and downloaded files.

## Windows troubleshooting

- **`essn` is not recognized:** open a new terminal after installation; verify `%LOCALAPPDATA%\yt-essential\bin` is in the user PATH.
- **FFmpeg or ffprobe missing:** install FFmpeg, reopen the terminal, and check `ffmpeg -version` and `ffprobe -version`.
- **YouTube JavaScript challenge errors:** verify `deno --version` reports 2.3 or newer.
- **PowerShell script execution is blocked:** use `Set-ExecutionPolicy -Scope Process Bypass -Force` in the current terminal, then rerun the script. This does not change the machine-wide policy.
- **FFmpeg fails only when a proxy is configured:** update the Windows compatibility layer using `windows\update.ps1`; the Windows adapter forwards supported HTTP(S) proxy settings to yt-dlp's FFmpeg input downloader. SOCKS proxy forwarding to FFmpeg is not implemented by this adapter.
- **Browser cookies fail:** close the browser completely, ensure the profile is logged in to the target site, and inspect the diagnostic output. DPAPI/App-Bound Encryption or site-side authentication checks may still prevent access.

## For developers

```bash
git clone https://github.com/icloud-storage/yt-dlp-essential.git
cd yt-dlp-essential
python -m venv .venv
```

On macOS/Linux:

```bash
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -t . -v
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -t . -v
```

The tests that exercise real downloads may require FFmpeg and network access. Windows-specific compatibility tests are in `tests/test_windows_compat.py`. PowerShell scripts should also be parsed/run on Windows PowerShell 5.1 and PowerShell 7 in CI.

Layout: `cli.py` (dialogue and entry point), `menu.py` (main menu), `ui.py` (terminal UI, keys, spinner), `engine.py` (yt-dlp integration), `gallery.py` (gallery-dl), `formats.py` (quality menu), `parsing.py` (selection and time ranges), `updates.py` (version checks), `config.py` (settings), and `windows/` (Windows installer, launchers, diagnostics and compatibility adapter).

## Credits and legal notes

Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) and [gallery-dl](https://github.com/mikf/gallery-dl) (GPL-2.0), installed as separate dependencies and not bundled here. FFmpeg and Deno are also external tools and are installed separately. Respect website terms of service and content-owner rights. The original project is released under the Unlicense; third-party components retain their own licenses.

## Releasing an update (maintainers)

Bump the version in both `yt_essential/__init__.py` (`__version__`) and `pyproject.toml`, commit and push the release to `main`, then create a matching Git tag and GitHub Release. The menu checks the repository version and announces updates. Before a Windows release, run the Windows CI job and the manual smoke-test checklist for supported Windows versions, PowerShell versions, browser cookie handling, FFmpeg/proxy and paths containing spaces or non-ASCII characters.
