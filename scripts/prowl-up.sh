#!/usr/bin/env bash
set -euo pipefail

# Start Prowlarr and qBittorrent.
cd "$(dirname "$0")/.."
docker compose up -d
