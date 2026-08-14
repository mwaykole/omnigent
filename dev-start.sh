#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 1. Sync Python deps
echo "==> Syncing Python dependencies..."
uv sync --extra all --group dev

# 2. Install frontend deps
echo "==> Installing frontend dependencies..."
cd web && pnpm install && cd ..

# 3. Build & install omnidev (the dev pod supervisor)
echo "==> Building omnidev..."
cargo install --path dev/omnidev --locked --force

# 4. Launch the dev pod (server + host + Vite frontend)
echo "==> Starting omnigent dev pod..."
omnidev
