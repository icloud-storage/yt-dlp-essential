#!/usr/bin/env bash
# essential (yt-dlp essential) — installer for macOS (also works on Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/icloud-storage/yt-dlp-essential/main/install.sh | bash
#
# Local install from an unpacked folder (no GitHub needed):
#   cd yt-dlp-essential && YTES_SOURCE="$PWD" bash install.sh
#
# Uninstall:  bash install.sh --uninstall
# Advanced env vars: YTES_REPO=user/repo  YTES_BRANCH=main  YTES_SOURCE=<pip spec>
set -euo pipefail

REPO="${YTES_REPO:-icloud-storage/yt-dlp-essential}"
BRANCH="${YTES_BRANCH:-main}"
SOURCE="${YTES_SOURCE:-https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip}"
HOME_DIR="${YTES_HOME:-$HOME/.yt-essential}"
VENV="$HOME_DIR/venv"
BIN_DIR="${YTES_BIN_DIR:-$HOME/.local/bin}"

step() { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m! %s\033[0m\n' "$1"; }
die()  { printf '\n\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ── uninstall ─────────────────────────────────────────────────
if [ "${1:-}" = "--uninstall" ]; then
  step "Uninstalling essential"
  rm -f "$BIN_DIR/essn" "$BIN_DIR/yt-es" "$BIN_DIR/ytes"
  rm -rf "$HOME_DIR"
  ok "Removed program files (your settings in ~/.config/yt-essential and your downloads are kept)"
  exit 0
fi

step "Installing essential"

# ── system: Homebrew deps ─────────────────────────────────────
need_brew_pkgs=""
find_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}
PY="$(find_python || true)"
[ -n "$PY" ] || need_brew_pkgs="$need_brew_pkgs python@3.12"
have ffmpeg || need_brew_pkgs="$need_brew_pkgs ffmpeg"
# JavaScript runtime — required by YouTube extraction in current yt-dlp
if ! have deno && ! have node && ! have bun; then need_brew_pkgs="$need_brew_pkgs deno"; fi

if [ -n "$need_brew_pkgs" ]; then
  if have brew; then
    step "Installing with Homebrew:${need_brew_pkgs}"
    # shellcheck disable=SC2086
    brew install $need_brew_pkgs
    PY="$(find_python || true)"
  else
    warn "Homebrew is not installed, but these are missing:${need_brew_pkgs}. Install Homebrew from https://brew.sh and run this command again."
  fi
fi
[ -n "$PY" ] || die "Python 3.10 or newer is required."
ok "Python: $("$PY" --version 2>&1)"
if have ffmpeg; then ok "ffmpeg found"; else warn "ffmpeg is missing — merging, audio and fragments need it (brew install ffmpeg)"; fi

# ── isolated virtual environment ──────────────────────────────
step "Creating isolated environment"
mkdir -p "$HOME_DIR" "$BIN_DIR"
rm -rf "$VENV"
"$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
step "Downloading essential, yt-dlp and gallery-dl"
# shellcheck disable=SC2086
"$VENV/bin/python" -m pip install --quiet --upgrade "$SOURCE" ${YTES_PIP_ARGS:-} \
  || die "Installation failed. Check your internet connection (and the repository name: $REPO)."

ln -sf "$VENV/bin/essn" "$BIN_DIR/essn"
rm -f "$BIN_DIR/yt-es" "$BIN_DIR/ytes"    # commands from earlier versions
ok "Installed"

# ── PATH ──────────────────────────────────────────────────────
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    line="export PATH=\"$BIN_DIR:\$PATH\"  # yt-dlp essential"
    for rc in "$HOME/.zshrc" "$HOME/.bash_profile"; do
      # always create .zshrc (macOS default shell); touch .bash_profile only if it exists
      if [ "$rc" = "$HOME/.zshrc" ] || [ -f "$rc" ]; then
        grep -qF "# yt-dlp essential" "$rc" 2>/dev/null || printf '\n%s\n' "$line" >> "$rc"
      fi
    done
    ok "Added $BIN_DIR to PATH (open a new Terminal window)" ;;
esac

echo
echo "Done! Open a new Terminal window and run:"
echo "    essn              # menu"
echo "    essn <link>       # analyze and download a link right away"
