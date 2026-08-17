#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# 0. Clear caches
echo "==> Clearing caches..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -rf .ruff_cache web/node_modules/.vite web/node_modules/.cache web/dist

# 1. Sync Python deps
echo "==> Syncing Python dependencies..."
uv sync --extra all --group dev

# 2. Install frontend deps
echo "==> Installing frontend dependencies..."
cd web && pnpm install --force && cd ..

# 3. Build & install omnidev (the dev pod supervisor)
echo "==> Building omnidev..."
cargo install --path dev/omnidev --locked --force

# 4. Launch the dev pod (server + host + Vite frontend)
echo "==> Starting omnigent dev pod..."
echo ""
echo "    Tip: Hard-refresh browser (Ctrl+Shift+R / Cmd+Shift+R) to bust browser cache."
echo ""
omnidev
