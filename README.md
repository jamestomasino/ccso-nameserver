# CCSO Nameserver (Book DB Profile)

This fork targets a single use case:

- Debian host install (no Docker)
- inetd-executed `qi` on TCP 105
- CCSO schema/data tuned for a personal book review database

## Upstream Reference

Original modernized repository by Michael Lazar:

- https://github.com/michael-lazar/ccso-nameserver

## Quickstart (Debian)

Install build deps:

```bash
sudo apt update
sudo apt install -y build-essential perl flex bison bc libgdbm-dev libgdbm-compat-dev libfl-dev
```

Build and install:

```bash
./ccso build
./ccso install-primes
./ccso install
```

Initialize the book database:

```bash
sudo /opt/nameserv/util/db/initdb-books
```

## inetd Wiring

`/etc/services`:

```conf
cso     105/tcp     csonet-ns
```

`/etc/inetd.conf`:

```conf
cso stream tcp nowait nobody /opt/nameserv/bin/qi qi -d -q
```

Reload:

```bash
sudo systemctl restart openbsd-inetd
```

## Gopher Type 2 Link

Example selector line:

```text
2Book Reviews (Search)		gopher.black	105
```

## Book Profile Files

- `util/db/books.cnf`: searchable field definitions
- `util/db/books.input`: seed records in `field_id:value` format
- `util/db/initdb-books`: database build script

## Data Pipeline

Generate normalized markdown from Goodreads CSV (defaults to `.local/books-markdown`, ignored by git):

```bash
python3 scripts/goodreads_to_markdown.py "/path/to/goodreads_library_export.csv"
```

Generate CCSO seed data from markdown files (defaults to `~/sync/syncthing/wiki/books`):

```bash
python3 scripts/books_markdown_to_ccso.py
```

Typical server refresh flow:

```bash
python3 scripts/books_markdown_to_ccso.py
sudo /opt/nameserv/util/db/initdb-books
```

Yes: `initdb-books` performs a full rebuild of the CCSO database files each run.

## Nightly Cron (Safe)

Create a wrapper script on the server (example: `/usr/local/bin/ccso-books-nightly`):

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/ccso-nameserver"
LOG_FILE="/var/log/ccso-books-nightly.log"
LOCK_FILE="/var/lock/ccso-books-nightly.lock"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -Is) [skip] job already running" >> "$LOG_FILE"
  exit 0
fi

{
  echo "$(date -Is) [start] rebuilding CCSO books database"
  cd "$REPO_DIR"
  /usr/bin/python3 scripts/books_markdown_to_ccso.py
  /opt/nameserv/util/db/initdb-books
  echo "$(date -Is) [ok] rebuild complete"
} >> "$LOG_FILE" 2>&1
```

Make it executable:

```bash
sudo chmod 755 /usr/local/bin/ccso-books-nightly
```

Install root cron entry (`sudo crontab -e`) for nightly 02:15:

```cron
15 2 * * * /usr/local/bin/ccso-books-nightly
```

Notes:

- The lock (`flock`) prevents overlapping runs.
- Logs are appended to `/var/log/ccso-books-nightly.log`.
- If markdown generation fails, the database rebuild step will not run.

Optional explicit paths:

```bash
python3 scripts/books_markdown_to_ccso.py /path/to/books-markdown /path/to/books.input
```

## Notes

- If `qi` is served by inetd, keep it in `-d -q` mode for clean protocol I/O.
