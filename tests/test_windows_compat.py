import os
import unittest
from pathlib import Path
from unittest.mock import patch

from windows.yt_essential_windows import (
    _CliSubprocessFacade,
    _replace_text,
    config_directory,
    decode_console_key,
    default_download_directory,
    detect_browser_keys,
    detect_ffmpeg_http_proxy,
    add_ffmpeg_proxy_options,
    read_console_line,
    windows_safe_download_options,
)


def windows_style(path):
    """Normalize a Path rendered by a POSIX test host to Windows separators."""
    return str(path).replace("/", "\\")


class WindowsPaths(unittest.TestCase):
    def test_appdata_config_path_with_unicode_and_spaces(self):
        with patch.dict(os.environ, {"APPDATA": r"C:\Users\Иван Иванов\AppData\Roaming"}, clear=True):
            self.assertEqual(
                windows_style(config_directory()),
                r"C:\Users\Иван Иванов\AppData\Roaming\yt-essential",
            )

    def test_explicit_config_override_expands_environment_variables(self):
        with patch.dict(
            os.environ,
            {"YTES_CONFIG_DIR": r"%USERPROFILE%\Мои настройки\yt-essential", "USERPROFILE": r"C:\Users\User"},
            clear=True,
        ):
            self.assertEqual(
                windows_style(config_directory()),
                r"C:\Users\User\Мои настройки\yt-essential",
            )

    def test_download_folder_is_under_userprofile_downloads(self):
        with patch.dict(os.environ, {"USERPROFILE": r"C:\Users\Иван Петров"}, clear=True):
            self.assertEqual(
                windows_style(default_download_directory()),
                r"C:\Users\Иван Петров\Downloads\yt-essential",
            )

    def test_xdg_is_respected_only_when_explicitly_configured(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": r"D:\portable\config"}, clear=True):
            self.assertEqual(windows_style(config_directory()), r"D:\portable\config\yt-essential")


class WindowsKeyboardMapping(unittest.TestCase):
    def test_extended_keys(self):
        for scan, expected in (("H", "up"), ("P", "down"), ("M", "right"), ("K", "left")):
            self.assertEqual(decode_console_key("\xe0", scan), expected)

    def test_regular_keys(self):
        self.assertEqual(decode_console_key("\r"), "enter")
        self.assertEqual(decode_console_key("\x1b"), "esc")
        self.assertEqual(decode_console_key("q"), "q")

    def test_line_editor_treats_ctrl_d_as_eof(self):
        class FakeMsvcrt:
            @staticmethod
            def getwch():
                return "\x04"

        from windows import yt_essential_windows as compat
        with patch.object(compat, "msvcrt", FakeMsvcrt), patch("sys.stdout"):
            with self.assertRaises(EOFError):
                read_console_line("Prompt: ")

    def test_eof_and_interrupt(self):
        with self.assertRaises(EOFError):
            decode_console_key("\x04")
        with self.assertRaises(KeyboardInterrupt):
            decode_console_key("\x03")


class WindowsIntegration(unittest.TestCase):
    def test_download_options_enable_windows_safe_names_without_dropping_fields(self):
        options = {"format": "bestvideo+bestaudio", "windowsfilenames": False}
        result = windows_safe_download_options(options)
        self.assertIs(result, options)
        self.assertEqual(result["windowsfilenames"], True)
        self.assertEqual(result["format"], "bestvideo+bestaudio")

    def test_finder_open_is_routed_to_explorer(self):
        path = r"C:\Users\Иван\Видео тест"
        with patch("windows.yt_essential_windows.subprocess.run") as run:
            _CliSubprocessFacade.run(["open", path], check=False)
        run.assert_called_once_with(["explorer.exe", path], check=False)

    def test_platform_specific_install_hints_are_windows_native(self):
        text = _replace_text(
            "brew install ffmpeg; brew install deno; macOS may ask for permission (Keychain, or Full Disk Access for Safari) — allow it",
            (
                ("brew install ffmpeg", "winget install ffmpeg"),
                ("brew install deno", "winget install deno"),
                ("macOS may ask for permission (Keychain, or Full Disk Access for Safari) — allow it", "Windows browser hint"),
            ),
        )
        self.assertEqual(text, "winget install ffmpeg; winget install deno; Windows browser hint")


class FfmpegProxyForwarding(unittest.TestCase):
    def test_prefers_https_proxy(self):
        self.assertEqual(
            detect_ffmpeg_http_proxy({"https": "http://127.0.0.1:2080", "http": "http://127.0.0.1:8080"}),
            "http://127.0.0.1:2080",
        )

    def test_falls_back_to_http_proxy(self):
        self.assertEqual(
            detect_ffmpeg_http_proxy({"http": "127.0.0.1:2080"}),
            "http://127.0.0.1:2080",
        )

    def test_does_not_pass_socks_proxy_to_ffmpeg_http_proxy(self):
        self.assertIsNone(detect_ffmpeg_http_proxy({"https": "socks5://127.0.0.1:1080"}))

    def test_missing_proxy_leaves_options_unchanged(self):
        options = {"quiet": True}
        self.assertIs(add_ffmpeg_proxy_options(options, None), options)
        self.assertNotIn("external_downloader_args", options)

    def test_adds_proxy_to_ffmpeg_input_args(self):
        options = {"quiet": True}
        result = add_ffmpeg_proxy_options(options, "http://127.0.0.1:2080")
        self.assertEqual(
            result["external_downloader_args"],
            {"ffmpeg_i": ["-http_proxy", "http://127.0.0.1:2080"]},
        )

    def test_replaces_existing_ffmpeg_proxy_without_dropping_other_args(self):
        options = {"external_downloader_args": {"ffmpeg_i": ["-loglevel", "warning", "-http_proxy", "http://old:1"]}}
        result = add_ffmpeg_proxy_options(options, "http://127.0.0.1:2080")
        self.assertEqual(
            result["external_downloader_args"]["ffmpeg_i"],
            ["-loglevel", "warning", "-http_proxy", "http://127.0.0.1:2080"],
        )


class BrowserDetection(unittest.TestCase):
    def test_installed_browsers_are_listed_first(self):
        result = detect_browser_keys(exists=lambda path: "Edge" in str(path) or "Brave" in str(path), env={
            "LOCALAPPDATA": r"C:\Users\User\AppData\Local",
            "APPDATA": r"C:\Users\User\AppData\Roaming",
            "ProgramFiles": r"C:\Program Files",
            "ProgramFiles(x86)": r"C:\Program Files (x86)",
        })
        self.assertEqual(result[:2], ["edge", "brave"])
        self.assertEqual(set(result), {"edge", "chrome", "firefox", "brave", "vivaldi", "opera", "chromium"})

    def test_unknown_browser_path_does_not_remove_supported_fallbacks(self):
        result = detect_browser_keys(exists=lambda _path: False, env={})
        self.assertEqual(result, ["edge", "chrome", "firefox", "brave", "vivaldi", "opera", "chromium"])


class WinGetInstallerCommand(unittest.TestCase):
    def test_install_command_uses_supported_install_options(self):
        script = (Path(__file__).parents[1] / "windows" / "install.ps1").read_text(encoding="utf-8-sig")
        helper_start = script.index("function Invoke-WinGetInstall")
        helper_end = script.index("function Ensure-Directory", helper_start)
        helper = script[helper_start:helper_end]
        self.assertIn("install --exact --id $PackageId --source winget --silent", helper)
        self.assertIn("--accept-source-agreements", helper)
        self.assertIn("--accept-package-agreements", helper)
        command_line = next(line for line in helper.splitlines() if "$winget.Source install" in line)
        self.assertNotIn("--upgrade", command_line)

    def test_ffmpeg_package_id_is_the_shared_build_with_ffmpeg_and_ffprobe(self):
        script = (Path(__file__).parents[1] / "windows" / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Invoke-WinGetInstall 'Gyan.FFmpeg.Shared' 'FFmpeg (ffmpeg + ffprobe)'", script)


if __name__ == "__main__":
    unittest.main()
