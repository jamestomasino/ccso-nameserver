#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import html
import json
import re
import zipfile
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / ".local" / "books-markdown"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert Goodreads export (CSV or privacy-export JSON/ZIP) into normalized markdown files."
    )
    p.add_argument(
        "input_path",
        type=Path,
        help="Path to Goodreads source (goodreads_library_export.csv, review.json/review.zip, or export directory)",
    )
    p.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write markdown files (default: {DEFAULT_OUTPUT_DIR})",
    )
    p.add_argument(
        "--no-index",
        action="store_true",
        help="Do not generate index.md in the output directory",
    )
    return p.parse_args()


def parse_utc_date(value: str) -> str:
    value = (value or "").strip()
    if not value or value == "(not provided)":
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def clean_isbn(value: str) -> str:
    value = (value or "").strip()
    if value.startswith('="') and value.endswith('"'):
        value = value[2:-1]
    return value.strip()


def parse_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return dt.datetime.strptime(value, "%Y/%m/%d").date().isoformat()
    except ValueError:
        return ""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "book"


def normalize_review(raw: str) -> str:
    raw = raw or ""
    raw = html.unescape(raw)
    raw = re.sub(r"(?is)<\s*/\s*p\s*>", "\n\n", raw)
    raw = re.sub(r"(?is)<\s*p[^>]*>", "", raw)
    raw = raw.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    raw = re.sub(r"(?is)<[^>]+>", "", raw)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    return raw


def normalize_tags(shelf: str, shelves: str) -> list[str]:
    tags = []
    for source in (shelf, shelves):
        for tag in (source or "").split(","):
            t = tag.strip().lower()
            if not t or t in {"read", "to-read", "currently-reading"}:
                continue
            if t not in tags:
                tags.append(t)
    return tags


def create_frontmatter(row: dict[str, str]) -> dict[str, object]:
    goodreads_id = (row.get("Book Id") or "").strip()
    title = (row.get("Title") or "").strip()
    author = (row.get("Author") or "").strip()
    year = (row.get("Year Published") or row.get("Original Publication Year") or "").strip()
    isbn13 = clean_isbn(row.get("ISBN13", ""))
    isbn10 = clean_isbn(row.get("ISBN", ""))
    rating = (row.get("My Rating") or "").strip()
    date_read = parse_date(row.get("Date Read", ""))
    date_added = parse_date(row.get("Date Added", ""))
    publisher = (row.get("Publisher") or "").strip()
    binding = (row.get("Binding") or "").strip()
    pages = (row.get("Number of Pages") or "").strip()
    tags = normalize_tags(row.get("Exclusive Shelf", ""), row.get("Bookshelves", ""))

    canonical_id = f"gr-{goodreads_id}-{slugify(title)}" if goodreads_id else f"book-{slugify(title)}"

    fm = {
        "id": canonical_id,
        "title": title,
        "author": author,
        "year": year,
        "isbn13": isbn13,
        "isbn10": isbn10,
        "publisher": publisher,
        "binding": binding,
        "pages": pages,
        "rating": float(rating) if rating.isdigit() else "",
        "status": "read",
        "date_read": date_read,
        "date_added": date_added,
        "goodreads_id": goodreads_id,
        "tags": tags,
    }
    return fm


def create_frontmatter_from_review_row(row: dict[str, object], fallback_id: str) -> tuple[dict[str, object], str]:
    title = str(row.get("book") or "").strip()
    rating_raw = str(row.get("rating") or "").strip()
    rating = float(rating_raw) if rating_raw.isdigit() else ""
    review = normalize_review(str(row.get("review") or ""))
    if review == "(not provided)":
        review = ""
    date_read = parse_utc_date(str(row.get("updated_at") or row.get("last_revision_at") or ""))
    date_added = parse_utc_date(str(row.get("created_at") or ""))
    canonical_id = f"grx-{slugify(title)}-{fallback_id}"

    fm = {
        "id": canonical_id,
        "title": title,
        "author": "",
        "year": "",
        "isbn13": "",
        "isbn10": "",
        "publisher": "",
        "binding": "",
        "pages": "",
        "rating": rating,
        "status": "read",
        "date_read": date_read,
        "date_added": date_added,
        "goodreads_id": "",
        "tags": [],
    }
    return fm, review


def rows_from_csv(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("Exclusive Shelf") or "").strip().lower() != "read":
                continue
            rows.append(row)
    return rows


def rows_from_review_json(data: list[object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if "book" not in item:
            continue
        if str(item.get("read_status") or "").strip().lower() != "read":
            continue
        if not str(item.get("book") or "").strip():
            continue
        out.append(item)
    return out


def load_review_json_path(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return rows_from_review_json(data)


def load_input_rows(path: Path) -> tuple[str, list[dict[str, object]]]:
    if path.is_dir():
        for name in ("goodreads_library_export.csv", "review.zip", "review.json"):
            candidate = path / name
            if candidate.exists():
                return load_input_rows(candidate)
        raise FileNotFoundError(f"No supported Goodreads export file found in {path}")

    lower = path.name.lower()
    if lower.endswith(".csv"):
        return "csv", rows_from_csv(path)

    if lower.endswith(".json"):
        return "review_json", load_review_json_path(path)

    if lower.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "review.json" in names:
                data = json.loads(zf.read("review.json"))
                if isinstance(data, list):
                    return "review_json", rows_from_review_json(data)
            if "goodreads_library_export.csv" in names:
                with zf.open("goodreads_library_export.csv") as f:
                    text = f.read().decode("utf-8-sig")
                reader = csv.DictReader(text.splitlines())
                rows = [
                    row for row in reader
                    if (row.get("Exclusive Shelf") or "").strip().lower() == "read"
                ]
                return "csv", rows
    raise FileNotFoundError(f"Unsupported input format: {path}")


def emit_markdown(frontmatter: dict[str, object], review: str) -> str:
    def q(s: object) -> str:
        return json.dumps(str(s), ensure_ascii=False)

    lines = ["---"]
    ordered = [
        "id",
        "title",
        "author",
        "year",
        "isbn13",
        "isbn10",
        "publisher",
        "binding",
        "pages",
        "rating",
        "status",
        "date_read",
        "date_added",
        "goodreads_id",
        "tags",
    ]
    for key in ordered:
        value = frontmatter.get(key, "")
        if value == "" or value == []:
            continue
        if key == "tags":
            lines.append(f"tags: [{', '.join(q(v) for v in value)}]")
        elif isinstance(value, float):
            lines.append(f"{key}: {value:.1f}")
        else:
            safe = str(value).replace("\n", " ").strip()
            lines.append(f"{key}: {q(safe)}")
    lines.extend(["---", ""])
    if review:
        lines.append(review)
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    args.input_path = args.input_path.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    no_review = 0

    source_kind, rows = load_input_rows(args.input_path)
    if source_kind == "csv":
        for row in rows:
            fm = create_frontmatter(row)  # type: ignore[arg-type]
            review = normalize_review((row.get("My Review", "") if isinstance(row, dict) else ""))
            if not review:
                no_review += 1
            out_name = f"{fm['id']}.md"
            out_path = args.output_dir / out_name
            out_path.write_text(emit_markdown(fm, review), encoding="utf-8")
            written += 1
    else:
        for idx, row in enumerate(rows, start=1):
            fm, review = create_frontmatter_from_review_row(row, f"{idx:04d}")
            if not review:
                no_review += 1
            out_name = f"{fm['id']}.md"
            out_path = args.output_dir / out_name
            out_path.write_text(emit_markdown(fm, review), encoding="utf-8")
            written += 1

    print(f"Input source: {args.input_path} ({source_kind})")
    print(f"Wrote {written} markdown files to {args.output_dir}")
    print(f"Read books without review text: {no_review}")

    if not args.no_index:
        entries: list[tuple[str, str, str]] = []
        for md in sorted(args.output_dir.glob("*.md")):
            if md.name == "index.md":
                continue
            lines = md.read_text(encoding="utf-8").splitlines()
            title = md.stem
            author = ""
            if lines and lines[0].strip() == "---":
                for line in lines[1:]:
                    if line.strip() == "---":
                        break
                    if ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    key = k.strip()
                    val = v.strip().strip('"')
                    if key == "title":
                        title = val
                    elif key == "author":
                        author = val
            entries.append((title.lower(), title, author, md.stem))

        entries.sort(key=lambda x: x[0])
        out = [
            "# Books",
            "",
            "Collections of book notes",
            "",
            "| Title | Author |",
            "|-------|--------|",
        ]
        for _, title, author, slug in entries:
            out.append(f"| [{title}]({slug}) | {author} |")
        index_path = args.output_dir / "index.md"
        index_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"Wrote index: {index_path} ({len(entries)} entries)")


if __name__ == "__main__":
    main()
