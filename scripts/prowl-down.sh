#!/usr/bin/env bash
set -euo pipefail

# Stop Prowlarr and qBittorrent. Downloads and seeding pause until prowl-up runs again.
cd "$(dirname "$0")/.."
docker compose stop
