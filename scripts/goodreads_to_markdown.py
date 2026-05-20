#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import html
import json
import re
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / ".local" / "books-markdown"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert Goodreads CSV export into normalized markdown files."
    )
    p.add_argument("input_csv", type=Path, help="Path to goodreads_library_export.csv")
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
    args.input_csv = args.input_csv.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    no_review = 0

    with args.input_csv.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("Exclusive Shelf") or "").strip().lower() != "read":
                skipped += 1
                continue

            fm = create_frontmatter(row)
            review = normalize_review(row.get("My Review", ""))
            if not review:
                no_review += 1

            out_name = f"{fm['id']}.md"
            out_path = args.output_dir / out_name
            out_path.write_text(emit_markdown(fm, review), encoding="utf-8")
            written += 1

    print(f"Wrote {written} markdown files to {args.output_dir}")
    print(f"Skipped non-read books: {skipped}")
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
