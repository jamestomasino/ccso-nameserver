#!/usr/bin/env python3
import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build index.md for normalized book markdown files.")
    p.add_argument("books_dir", type=Path, help="Directory containing per-book markdown files")
    return p.parse_args()


def parse_frontmatter(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return data

    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"')
    return data


def main() -> None:
    args = parse_args()
    books_dir = args.books_dir

    rows: list[tuple[str, str, str]] = []
    for path in sorted(books_dir.glob("*.md")):
        if path.name == "index.md":
            continue
        fm = parse_frontmatter(path)
        title = fm.get("title", path.stem)
        author = fm.get("author", "")
        slug = path.stem
        rows.append((title.lower(), title, author, slug))

    rows.sort(key=lambda x: x[0])

    out = [
        "# Books",
        "",
        "Collections of book notes",
        "",
        "| Title | Author |",
        "|-------|--------|",
    ]
    for _, title, author, slug in rows:
        out.append(f"| [{title}]({slug}) | {author} |")

    index_path = books_dir / "index.md"
    index_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {index_path} with {len(rows)} entries.")


if __name__ == "__main__":
    main()
