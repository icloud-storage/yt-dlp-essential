"""Persistent user settings (JSON file)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULTS = {
    'download_dir': None,        # None -> ~/Downloads/yt-essential
    'ask_dir_each_time': True,
    'cookies_browser': None,     # e.g. 'safari', 'chrome'
}


def config_dir() -> Path:
    override = os.environ.get('YTES_CONFIG_DIR')
    if override:
        return Path(override).expanduser()
    base = os.environ.get('XDG_CONFIG_HOME')
    return (Path(base) if base else Path.home() / '.config') / 'yt-essential'


def config_path() -> Path:
    return config_dir() / 'config.json'


def default_download_dir() -> Path:
    return Path.home() / 'Downloads' / 'yt-essential'


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(config_path().read_text(encoding='utf-8'))
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.cfg-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump({k: cfg.get(k, v) for k, v in DEFAULTS.items()}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def base_download_dir(cfg: dict) -> Path:
    raw = cfg.get('download_dir')
    return Path(raw).expanduser() if raw else default_download_dir()
