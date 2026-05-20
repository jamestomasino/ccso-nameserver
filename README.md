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
sudo apt install -y build-essential perl flex bison bc libgdbm-dev
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

## Notes

- If `qi` is served by inetd, keep it in `-d -q` mode for clean protocol I/O.
