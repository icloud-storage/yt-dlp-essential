"""Windows runtime compatibility layer for yt-dlp-essential.

This module is copied into ``yt_essential/windows_compat.py`` by install.ps1.
It deliberately patches only platform integration points; download planning,
format selection, gallery-dl, parsing and update logic remain upstream code.
"""
from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

try:  # msvcrt exists only on Windows
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # lets the pure helpers be tested on non-Windows hosts
    msvcrt = None  # type: ignore[assignment]

_LOGGER = logging.getLogger("yt_essential.windows")
_ANSI_READY: bool | None = None


def _expand_environment(value: str) -> str:
    """Expand both ``%NAME%`` and ``$NAME`` forms in an explicit path override."""
    import re

    expanded = os.path.expandvars(value)
    return re.sub(r"%([^%]+)%", lambda match: os.environ.get(match.group(1), match.group(0)), expanded)


def config_directory() -> Path:
    """Return the standard Windows per-user config directory."""
    override = os.environ.get("YTES_CONFIG_DIR")
    if override:
        return Path(_expand_environment(override)).expanduser()

    # Respect an explicit XDG override for users who intentionally share config.
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(_expand_environment(xdg)).expanduser() / "yt-essential"

    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "yt-essential"


def default_download_directory() -> Path:
    """Return a stable per-user download location on Windows."""
    user_profile = os.environ.get("USERPROFILE")
    home = Path(user_profile) if user_profile else Path.home()
    return home / "Downloads" / "yt-essential"


def _browser_candidates(env: dict[str, str] | None = None) -> dict[str, tuple[Path, ...]]:
    """Known browser executable locations; no registry or third-party APIs needed."""
    e = os.environ if env is None else env
    local = Path(e.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    roaming = Path(e.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    pf = Path(e.get("ProgramFiles", e.get("ProgramW6432", r"C:\Program Files")))
    pf86 = Path(e.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    return {
        "edge": (
            pf / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            pf86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            local / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ),
        "chrome": (
            local / "Google" / "Chrome" / "Application" / "chrome.exe",
            pf / "Google" / "Chrome" / "Application" / "chrome.exe",
            pf86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        ),
        "firefox": (
            pf / "Mozilla Firefox" / "firefox.exe",
            pf86 / "Mozilla Firefox" / "firefox.exe",
            local / "Mozilla Firefox" / "firefox.exe",
            roaming / "Mozilla" / "Firefox" / "firefox.exe",
        ),
        "brave": (
            local / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            pf / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            pf86 / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ),
        "vivaldi": (
            local / "Vivaldi" / "Application" / "vivaldi.exe",
            pf / "Vivaldi" / "Application" / "vivaldi.exe",
            pf86 / "Vivaldi" / "Application" / "vivaldi.exe",
        ),
        "opera": (
            local / "Programs" / "Opera" / "launcher.exe",
            local / "Programs" / "Opera" / "opera.exe",
            local / "Programs" / "Opera GX" / "launcher.exe",
            local / "Programs" / "Opera GX" / "opera.exe",
            pf / "Opera" / "launcher.exe",
            pf86 / "Opera" / "launcher.exe",
        ),
        "chromium": (
            local / "Chromium" / "Application" / "chrome.exe",
            pf / "Chromium" / "Application" / "chrome.exe",
        ),
    }


def detect_browser_keys(
    exists: Callable[[Path], bool] | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Return installed browsers first, followed by yt-dlp-supported choices."""
    check = exists or Path.is_file
    candidates = _browser_candidates(env)
    order = ["edge", "chrome", "firefox", "brave", "vivaldi", "opera", "chromium"]
    found = [key for key in order if any(check(p) for p in candidates[key])]
    return found + [key for key in order if key not in found]


def _kernel32_console_api():
    """Load Win32 console functions with pointer-sized HANDLE signatures."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.argtypes = (wintypes.DWORD,)
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetConsoleMode.restype = wintypes.BOOL
    kernel32.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.SetConsoleMode.restype = wintypes.BOOL
    kernel32.FlushConsoleInputBuffer.argtypes = (wintypes.HANDLE,)
    kernel32.FlushConsoleInputBuffer.restype = wintypes.BOOL
    return kernel32, wintypes


def _enable_virtual_terminal() -> bool:
    """Enable ANSI cursor/color sequences in classic Windows console hosts."""
    global _ANSI_READY
    if _ANSI_READY is not None:
        return _ANSI_READY
    if os.name != "nt":
        _ANSI_READY = False
        return False
    try:
        import ctypes

        kernel32, wintypes = _kernel32_console_api()
        stdout_handle = kernel32.GetStdHandle(wintypes.DWORD(0xFFFFFFF5))  # STD_OUTPUT_HANDLE (-11)
        mode = wintypes.DWORD()
        if not stdout_handle or not kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode)):
            _ANSI_READY = False
        else:
            enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            _ANSI_READY = bool(kernel32.SetConsoleMode(stdout_handle, mode.value | enable_vt))
    except Exception:  # noqa: BLE001 - fallback to the text-only menu
        _ANSI_READY = False
    return _ANSI_READY


def is_interactive_console() -> bool:
    """Use the full-screen UI only when stdin/stdout are real ANSI-capable consoles."""
    if os.name != "nt" or msvcrt is None:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty() and _enable_virtual_terminal())
    except (AttributeError, OSError, ValueError):
        return False


def windows_safe_download_options(options: dict) -> dict:
    """Enable yt-dlp's Windows-safe filename normalization without changing other opts."""
    options["windowsfilenames"] = True
    return options


def _normalize_http_proxy(proxy: str | None) -> str | None:
    """Return an HTTP(S) proxy URL usable by FFmpeg, or None for unsupported proxies."""
    from urllib.parse import urlsplit

    if not isinstance(proxy, str) or not proxy.strip():
        return None
    value = proxy.strip()
    if "://" not in value:
        value = f"http://{value}"
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        # Accessing .port validates malformed ports while preserving credentials/path.
        _ = parsed.port
    except ValueError:
        return None
    return value


def detect_ffmpeg_http_proxy(proxies: dict[str, str] | None = None) -> str | None:
    """Find the HTTPS/HTTP proxy yt-dlp gets from the environment/system settings.

    yt-dlp's Python downloader reads urllib's proxy map, but FFmpeg is a separate
    process and does not automatically inherit that proxy configuration as an
    FFmpeg input option. YouTube media URLs are HTTPS, so prefer the HTTPS proxy.
    """
    if proxies is None:
        try:
            from urllib.request import getproxies
            proxies = getproxies()
        except Exception:  # noqa: BLE001 - proxy discovery must not break downloads
            return None
    for key in ("https", "http", "all"):
        proxy = _normalize_http_proxy(proxies.get(key))
        if proxy:
            return proxy
    return None


def add_ffmpeg_proxy_options(options: dict, proxy: str | None) -> dict:
    """Pass the detected HTTP(S) proxy to yt-dlp's FFmpeg input downloader."""
    normalized = _normalize_http_proxy(proxy)
    if not normalized:
        return options

    downloader_args = options.get("external_downloader_args")
    if not isinstance(downloader_args, dict):
        downloader_args = {}
    else:
        downloader_args = dict(downloader_args)

    current = downloader_args.get("ffmpeg_i", [])
    if isinstance(current, str):
        import shlex
        current = shlex.split(current, posix=(os.name != "nt"))
    else:
        current = list(current)

    # Replace an existing proxy option instead of adding a conflicting duplicate.
    try:
        index = current.index("-http_proxy")
    except ValueError:
        current.extend(["-http_proxy", normalized])
    else:
        if index + 1 < len(current):
            current[index + 1] = normalized
        else:
            current.append(normalized)

    downloader_args["ffmpeg_i"] = current
    options["external_downloader_args"] = downloader_args
    return options


def decode_console_key(char: str, extended: str | None = None) -> str:
    """Translate msvcrt.getwch characters into the UI's platform-neutral key names."""
    if char in ("\x00", "\xe0"):
        return {
            "H": "up",
            "P": "down",
            "M": "right",
            "K": "left",
            "G": "home",
            "O": "end",
            "S": "delete",
        }.get(extended or "", "other")
    if char in ("\r", "\n"):
        return "enter"
    if char == "\x1b":
        return "esc"
    if char == "\x04":
        raise EOFError
    if char == "\x03":
        raise KeyboardInterrupt
    return char


def read_console_key(timeout: float | None = None) -> str | None:
    """Read one console key without relying on POSIX termios/select semantics."""
    if msvcrt is None:
        raise RuntimeError("Windows console input is unavailable (msvcrt was not imported)")

    deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
    while not msvcrt.kbhit():
        if deadline is not None and time.monotonic() >= deadline:
            return None
        time.sleep(0.005)

    char = msvcrt.getwch()
    if char in ("\x00", "\xe0"):
        # Windows represents arrows and navigation keys as a prefix + scan code.
        return decode_console_key(char, msvcrt.getwch())
    return decode_console_key(char)


@contextlib.contextmanager
def windows_no_echo():
    """Temporarily disable console echo/line buffering while a task is running."""
    if not is_interactive_console():
        yield
        return

    kernel32 = None
    stdin_handle = None
    old_mode = None
    try:
        import ctypes

        kernel32, wintypes = _kernel32_console_api()
        stdin_handle = kernel32.GetStdHandle(wintypes.DWORD(0xFFFFFFF6))  # STD_INPUT_HANDLE (-10)
        mode = wintypes.DWORD()
        if stdin_handle and kernel32.GetConsoleMode(stdin_handle, ctypes.byref(mode)):
            old_mode = mode.value
            # ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT
            kernel32.SetConsoleMode(stdin_handle, old_mode & ~(0x0002 | 0x0004))
    except Exception:  # noqa: BLE001 - no-echo is cosmetic, never block downloads
        kernel32 = None
        old_mode = None

    try:
        yield
    finally:
        if kernel32 is not None and stdin_handle and old_mode is not None:
            try:
                # Match the upstream POSIX tcflush: do not let keys typed during
                # a download answer the next interactive prompt by accident.
                kernel32.FlushConsoleInputBuffer(stdin_handle)
                kernel32.SetConsoleMode(stdin_handle, old_mode)
            except Exception:  # noqa: BLE001
                pass


def read_console_line(prompt: str) -> str:
    """Small UTF-16 aware line editor for Windows terminals."""
    if msvcrt is None:
        raise RuntimeError("Windows console input is unavailable")

    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars: list[str] = []

    while True:
        char = msvcrt.getwch()
        if char in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(chars)
        if char == "\x1b":
            sys.stdout.write("\n")
            sys.stdout.flush()
            from yt_essential.ui import Abort
            raise Abort
        if char == "\x03":
            raise KeyboardInterrupt
        if char == "\x04":
            raise EOFError
        if char in ("\x08", "\x7f"):
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if char in ("\x00", "\xe0"):
            # Consume navigation scan code. The prompt editor intentionally keeps
            # insertion simple, but arrow/delete keys must not leak into the input.
            msvcrt.getwch()
            continue
        if char < " ":
            continue

        code = ord(char)
        if 0xD800 <= code <= 0xDBFF:
            # Console input is UTF-16: combine a surrogate pair for supplementary
            # characters (for example, emoji pasted into a folder path).
            low = msvcrt.getwch()
            if low and 0xDC00 <= ord(low) <= 0xDFFF:
                codepoint = 0x10000 + ((code - 0xD800) << 10) + (ord(low) - 0xDC00)
                char = chr(codepoint)
            else:
                char += low
        chars.append(char)
        sys.stdout.write(char)
        sys.stdout.flush()


def _setup_logging(config_path: Path) -> None:
    log_dir = Path(os.environ.get("YTES_LOG_DIR", str(config_path / "logs")))
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"essn-{time.strftime('%Y%m%d')}.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _LOGGER.setLevel(logging.INFO)
        _LOGGER.addHandler(handler)
        _LOGGER.propagate = False
        _LOGGER.info("Starting yt-dlp-essential Windows compatibility layer")
        _LOGGER.info("Python=%s; platform=%s; argv=%r", sys.version.split()[0], sys.platform, sys.argv[1:])
    except OSError:
        # Logging must never prevent a user from downloading.
        pass


def _wrap_ui_logger(ui_module) -> None:
    for name, level in (("step", logging.INFO), ("note", logging.WARNING), ("fail", logging.ERROR)):
        original = getattr(ui_module, name, None)
        if original is None or getattr(original, "_ytes_logged", False):
            continue

        def make_wrapper(func, log_level, func_name):
            def wrapped(*args, **kwargs):
                if func_name == "note":
                    replacements = (
                        ("brew install ffmpeg", "winget install --exact --id Gyan.FFmpeg.Shared"),
                        ("brew install deno", "winget install --exact --id DenoLand.Deno"),
                        (
                            "macOS may ask for permission (Keychain, or Full Disk Access for Safari) — allow it",
                            "Windows: если браузер не закрыт, извлечение cookies может не сработать. Закройте браузер и повторите попытку.",
                        ),
                    )
                    args = tuple(
                        _replace_text(value, replacements) if isinstance(value, str) else value
                        for value in args
                    )
                    kwargs = {
                        key: _replace_text(value, replacements) if isinstance(value, str) else value
                        for key, value in kwargs.items()
                    }
                if args:
                    _LOGGER.log(log_level, "%s: %s", func_name, " ".join(str(x) for x in args))
                return func(*args, **kwargs)
            wrapped._ytes_logged = True
            return wrapped

        setattr(ui_module, name, make_wrapper(original, level, name))


def _replace_text(value: str, replacements: tuple[tuple[str, str], ...]) -> str:
    for old, new in replacements:
        value = value.replace(old, new)
    return value


class _CliSysFacade:
    """Expose Darwin only to the CLI's Finder-vs-terminal post-download branch."""

    def __init__(self, real_sys):
        self._real_sys = real_sys

    @property
    def platform(self) -> str:
        return "darwin"

    def __getattr__(self, name):
        return getattr(self._real_sys, name)


class _CliSubprocessFacade:
    """Translate the CLI's single Finder-open command to Windows Explorer."""

    def __getattr__(self, name):
        return getattr(subprocess, name)

    @staticmethod
    def run(args, *positional, **kwargs):
        if isinstance(args, (list, tuple)) and len(args) >= 2 and args[0] == "open":
            args = ["explorer.exe", str(args[1]), *args[2:]]
        return subprocess.run(args, *positional, **kwargs)


def apply_windows_compatibility() -> None:
    """Patch the original app's platform seams while preserving its core logic."""
    if os.name != "nt":
        raise OSError("The Windows runtime layer can only be activated on Windows")

    # Enforce UTF-8 in Python itself and in child Python processes (gallery-dl/pip).
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    from yt_essential import config, ui
    from yt_essential import engine
    from yt_essential import cli, menu

    # The defaults below are called dynamically by config.load/save/base_download_dir.
    config.config_dir = config_directory
    config.default_download_dir = default_download_directory

    browser_keys = detect_browser_keys()
    browser_labels = {
        "edge": "Microsoft Edge",
        "chrome": "Google Chrome",
        "firefox": "Firefox",
        "brave": "Brave Browser",
        "vivaldi": "Vivaldi",
        "opera": "Opera",
        "chromium": "Chromium",
    }
    engine.BROWSERS = [(key, browser_labels[key]) for key in browser_keys]

    def installed_browsers() -> list[str]:
        return list(browser_keys)

    engine.installed_browsers = installed_browsers
    # cli.py and menu.py import this function directly, so refresh those references too.
    cli.installed_browsers = installed_browsers
    menu.installed_browsers = installed_browsers

    # Windows reserves characters such as < > : " / \ | ? * in file names.
    # Leave the upstream format/quality plan intact but ask yt-dlp to sanitize output names.
    original_build_download_opts = engine.build_download_opts

    def windows_build_download_opts(plan):
        return windows_safe_download_options(original_build_download_opts(plan))

    engine.build_download_opts = windows_build_download_opts

    # yt-dlp's Python API uses urllib/environment proxy settings for its own
    # requests, but the external FFmpeg process needs the proxy passed explicitly.
    # Match the CLI's `--downloader-args "ffmpeg_i:-http_proxy <proxy>"` behavior.
    original_session_base_opts = engine.Session.base_opts

    def windows_session_base_opts(session, logger):
        options = original_session_base_opts(session, logger)
        proxy = detect_ffmpeg_http_proxy()
        if proxy:
            add_ffmpeg_proxy_options(options, proxy)
            _LOGGER.info("Forwarded configured HTTP(S) proxy to FFmpeg input downloader")
        return options

    engine.Session.base_opts = windows_session_base_opts

    # msvcrt replaces termios/tty/select for key and line input.
    ui.interactive = is_interactive_console
    original_color = ui._color

    def windows_color() -> bool:
        return bool(original_color() and _enable_virtual_terminal())

    ui._color = windows_color
    ui.read_key = read_console_key
    ui._read_line = read_console_line
    ui.no_echo = windows_no_echo
    original_wait_key = ui.wait_key

    def windows_wait_key(message: str = "Press any key to continue", extra: str = "") -> str:
        return original_wait_key(message, extra.replace("Finder", "Explorer"))

    ui.wait_key = windows_wait_key

    # cli.run_download() has one macOS-specific post-download action: open in Finder.
    # Route that same interaction through Explorer without copying its download flow.
    cli.sys = _CliSysFacade(sys)
    cli.subprocess = _CliSubprocessFacade()

    _setup_logging(config.config_dir())
    _wrap_ui_logger(ui)
    _LOGGER.info("Config directory: %s", config.config_dir())
    _LOGGER.info("Default download directory: %s", config.default_download_dir())
    _LOGGER.info("Browsers offered for cookie extraction: %s", ", ".join(browser_keys))


def main() -> int:
    """Prepare Windows integration and hand control to the unchanged upstream CLI."""
    apply_windows_compatibility()
    from yt_essential.cli import main as upstream_main

    try:
        return int(upstream_main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception:
        _LOGGER.exception("Unhandled application error")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
