#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOKS_DIR="${1:-$HOME/sync/syncthing/wiki/books}"
SERVICE_USER="${SERVICE_USER:-nameserv}"
SERVICE_GROUP="${SERVICE_GROUP:-nameserv}"

echo "[1/5] Generating CCSO input from markdown..."
python3 "$REPO_DIR/scripts/books_markdown_to_ccso.py" "$BOOKS_DIR" "$REPO_DIR/util/db/books.input"

echo "[2/5] Installing books.input to /opt/nameserv..."
install -m 0644 "$REPO_DIR/util/db/books.input" /opt/nameserv/util/db/books.input

echo "[3/5] Rebuilding CCSO database..."
/opt/nameserv/util/db/initdb-books

echo "[4/5] Applying runtime permissions..."
chown "$SERVICE_USER:$SERVICE_GROUP" /opt/nameserv/db/prod.*
chmod 644 /opt/nameserv/db/prod.*
chmod 664 /opt/nameserv/db/prod.seq

echo "[5/5] Restarting socket service..."
if systemctl list-unit-files | rg -q '^ccso\.socket'; then
  systemctl restart ccso.socket
fi

echo "Done."
