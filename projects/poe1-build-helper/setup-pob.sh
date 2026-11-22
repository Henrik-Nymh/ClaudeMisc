#!/usr/bin/env bash
# Set up headless Path of Building for poe1-build-helper:
# installs LuaJIT + luautf8 if missing, and fetches PoB (Lua sources only,
# no images) into .cache/pob. Rerun to update PoB. Linux/macOS (Windows: WSL).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
dest="${POE1_POB_DIR:-$here/.cache/pob}"
ref="${POE1_POB_REF:-master}"
repo="https://github.com/PathOfBuildingCommunity/PathOfBuilding.git"

sudo_cmd=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null; then sudo_cmd="sudo"; fi

if ! command -v luajit >/dev/null || ! command -v luarocks >/dev/null; then
  if command -v apt-get >/dev/null; then
    $sudo_cmd apt-get update -qq
    DEBIAN_FRONTEND=noninteractive $sudo_cmd apt-get install -y -qq luajit libluajit-5.1-dev luarocks
  elif command -v brew >/dev/null; then
    brew install luajit luarocks
  else
    echo "Please install LuaJIT and luarocks, then rerun this script." >&2
    exit 1
  fi
fi

if ! luajit -e 'require("lua-utf8")' 2>/dev/null; then
  $sudo_cmd luarocks --lua-version=5.1 install luautf8 >/dev/null
fi

if [ ! -d "$dest/.git" ]; then
  mkdir -p "$(dirname "$dest")"
  git clone --quiet --depth 1 --branch "$ref" --filter=blob:none --sparse "$repo" "$dest"
else
  git -C "$dest" fetch --quiet --depth 1 origin "$ref"
  git -C "$dest" checkout --quiet --force FETCH_HEAD
fi
git -C "$dest" sparse-checkout set --no-cone \
  '/src/' '!/src/**/*.png' '!/src/**/*.webp' '!/src/**/*.jpg' \
  '/runtime/lua/' '/manifest.xml' '/changelog.txt' '/help.txt' '/LICENSE.md'

echo "Path of Building $(git -C "$dest" log -1 --format='%h (%cs)') ready in $dest"
