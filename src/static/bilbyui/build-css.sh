#!/bin/bash
# Compile src/static/bilbyui/scss/app.scss -> src/static/bilbyui/app.css
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v sass >/dev/null 2>&1; then
  npm_prefix="$(npm config get prefix 2>/dev/null || true)"
  if [ -n "$npm_prefix" ] && [ -x "$npm_prefix/bin/sass" ]; then
    PATH="$npm_prefix/bin:$PATH"
  fi
fi

if ! command -v sass >/dev/null 2>&1; then
  echo "Dart Sass is required. Install with: npm install -g sass" >&2
  echo "Ensure the npm global bin directory is on your PATH." >&2
  exit 1
fi

sass scss/app.scss app.css --no-source-map \
  --silence-deprecation=import,if-function,global-builtin,color-functions,abs-percent
