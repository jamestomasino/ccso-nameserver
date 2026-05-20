#!/usr/bin/env python3
import argparse
import hashlib
from pathlib import Path

DEFAULT_INPUT_DIR = Path("~/sync/syncthing/wiki/books").expanduser()
DEFAULT_OUTPUT_FILE = Path(__file__).resolve().parents[1] / "util" / "db" / "books.input"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert normalized book markdown files into CCSO books.input format."
    )
    p.add_argument(
        "input_dir",
        type=Path,
        nargs="?",
        default=DEFAULT_INPUT_DIR,
        help=f"Directory containing normalized book markdown files (default: {DEFAULT_INPUT_DIR})",
    )
    p.add_argument(
        "output_file",
        type=Path,
        nargs="?",
        default=DEFAULT_OUTPUT_FILE,
        help=f"Path for generated books.input (default: {DEFAULT_OUTPUT_FILE})",
    )
    return p.parse_args()


def parse_frontmatter_and_body(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text.strip()
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text.strip()

    fm_block = text[4:end]
    body = text[end + 5 :].strip()
    fm: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip()
        if val.startswith('"') and val.endswith('"') and len(val) >= 2:
            val = val[1:-1]
        fm[key] = val
    return fm, body


def clean_value(value: str) -> str:
    value = (value or "").replace("\t", " ").strip()
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\n", "\\n")
    return value


def parse_tags(tags_raw: str) -> str:
    tags_raw = tags_raw.strip()
    if tags_raw.startswith("[") and tags_raw.endswith("]"):
        inner = tags_raw[1:-1].strip()
        if not inner:
            return ""
        parts = [p.strip().strip('"').strip("'") for p in inner.split(",")]
        parts = [p for p in parts if p]
        return ",".join(parts)
    return tags_raw


def short_alias(fm: dict[str, str]) -> str:
    gid = fm.get("goodreads_id", "").strip()
    if gid:
        alias = f"gr-{gid}"
        if len(alias) <= 32:
            return alias
    source = (fm.get("id") or fm.get("title") or "book").encode("utf-8", errors="ignore")
    digest = hashlib.sha1(source).hexdigest()[:24]
    return f"b-{digest}"


def numeric_id(index: int, fm: dict[str, str]) -> str:
    gid = fm.get("goodreads_id", "").strip()
    if gid.isdigit() and len(gid) <= 16:
        return gid.zfill(9)
    return str(index).zfill(9)


def rating_string(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        return f"{float(raw):g}/5"
    except ValueError:
        return raw


def make_record(index: int, md_file: Path) -> str | None:
    fm, body = parse_frontmatter_and_body(md_file.read_text(encoding="utf-8"))
    if not fm:
        return None

    title = clean_value(fm.get("title", ""))
    if not title:
        return None

    fields: list[tuple[int, str]] = [
        (5, numeric_id(index, fm)),
        (6, short_alias(fm)),
        (3, title),
        (4, "book review"),
        (60, title),
    ]

    mapping = [
        (61, "author"),
        (62, "year"),
        (64, "publisher"),
        (68, "status"),
        (69, "date_read"),
    ]
    for fid, key in mapping:
        val = clean_value(fm.get(key, ""))
        if val:
            fields.append((fid, val))

    isbn = clean_value(fm.get("isbn13", "")) or clean_value(fm.get("isbn10", ""))
    if isbn:
        fields.append((63, isbn))

    tags = parse_tags(fm.get("tags", ""))
    tags = clean_value(tags)
    if tags:
        fields.append((66, tags))

    rating = rating_string(fm.get("rating", ""))
    rating = clean_value(rating)
    if rating:
        fields.append((67, rating))

    review = clean_value(body)
    if review:
        fields.append((70, review))

    gid = fm.get("goodreads_id", "").strip()
    if gid:
        fields.append((71, f"https://www.goodreads.com/book/show/{gid}"))

    return "\t".join(f"{fid}:{value}" for fid, value in fields)


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    output_file = args.output_file.expanduser().resolve()

    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    files = [p for p in sorted(input_dir.glob("*.md")) if p.name != "index.md"]
    records: list[str] = []
    skipped = 0
    for i, md_file in enumerate(files, start=1):
        rec = make_record(i, md_file)
        if rec is None:
            skipped += 1
            continue
        records.append(rec)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(records) + ("\n" if records else ""), encoding="utf-8")

    print(f"Read markdown files: {len(files)}")
    print(f"Wrote CCSO records: {len(records)}")
    print(f"Skipped files: {skipped}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
