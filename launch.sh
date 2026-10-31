#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
case "$(uname -s)" in Darwin) sys=macos ;; Linux) sys=linux ;; *) echo 'Unsupported execution system.' >&2; exit 1 ;; esac
case "$(uname -m)" in x86_64|amd64) arch=x86_64 ;; arm64|aarch64) arch=aarch64 ;; *) echo 'Unsupported CPU.' >&2; exit 1 ;; esac
key="$sys-$arch"
case "$key" in
  linux-x86_64) expected="ce4f6d0a6cfdb3bed6e44c2f9affd85943c76a42e25ad3a259002f31d6fb8a20" ;;
  linux-aarch64) expected="bb4b6392670c5d3f93876996fcaa19858a4a413a0c7720144c18b0d6f1f0db2d" ;;
  macos-x86_64) expected="37c38fda76fec1fbf310adcbafb7f0d96af13b5511bf8ea954c3aa8eec185734" ;;
  macos-aarch64) expected="353d5f1b4fd2715e7053f12f068435d5bbad16b91e057006b5d01e0925709a7e" ;;
esac
if [ -n "${AHUI_HD_CACHE:-}" ]; then base="$AHUI_HD_CACHE"
elif [ "$sys" = macos ]; then base="$HOME/Library/Caches/ahui-hd-upscale"
else base="${XDG_CACHE_HOME:-$HOME/.cache}/ahui-hd-upscale"; fi
state="$base/v1/$key"
mkdir -p "$state"
archive="$ROOT/assets/platforms/$key/python.tar.gz"
if command -v sha256sum >/dev/null 2>&1; then actual=$(sha256sum "$archive" | cut -d ' ' -f 1)
elif command -v shasum >/dev/null 2>&1; then actual=$(shasum -a 256 "$archive" | cut -d ' ' -f 1)
else echo 'Missing SHA-256 verifier.' >&2; exit 1; fi
if [ "$actual" != "$expected" ]; then echo 'Bundled Python integrity check failed.' >&2; exit 1; fi
runtime="$state/python-$expected"
if [ ! -f "$runtime/.ready" ]; then
  stage=$(mktemp -d "$state/python-stage.XXXXXX")
  trap 'rm -rf -- "$stage"' EXIT HUP INT TERM
  tar -xzf "$archive" -C "$stage"
  test -x "$stage/python/bin/python3"
  printf '%s' "$expected" > "$stage/python/.ready"
  if [ -e "$runtime" ]; then echo 'Incomplete Python cache; choose a new AHUI_HD_CACHE.' >&2; exit 1; fi
  mv "$stage/python" "$runtime"
  rmdir "$stage"
  trap - EXIT HUP INT TERM
fi
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
exec "$runtime/bin/python3" -I "$ROOT/scripts/bootstrap.py" "$@"
