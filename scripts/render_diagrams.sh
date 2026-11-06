#!/usr/bin/env bash
# Render docs/diagrams/*.mmd to SVG with the Mermaid CLI. Needs Node.js and a Chrome or Chromium.
# Set CHROME_PATH if the browser is not at /usr/bin/google-chrome.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
chrome="${CHROME_PATH:-/usr/bin/google-chrome}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

printf '{"executablePath":"%s","args":["--no-sandbox"]}\n' "$chrome" > "$work/puppeteer.json"

for source in "$root"/docs/diagrams/*.mmd; do
    target="${source%.mmd}.svg"
    PUPPETEER_SKIP_DOWNLOAD=1 npx --yes @mermaid-js/mermaid-cli@11.4.2 \
        -p "$work/puppeteer.json" -c "$root/docs/diagrams/mermaid.config.json" \
        -b white -i "$source" -o "$target" --quiet
    echo "rendered ${target#"$root"/}"
done
