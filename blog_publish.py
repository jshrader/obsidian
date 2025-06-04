"""
Script to copy markdown files that are tagged with 'blog' in their YAML front‑matter
to a destination compatible with a Jekyll blog, while:

1. Replacing the front‑matter with new Jekyll‑style fields (see TODO below).
2. Copying referenced Obsidian‑style embedded images to a separate destination folder.
3. Converting image links to standard Markdown syntax.
4. Performing simple find‑and‑replace transformations on terms wrapped in [[double brackets]].

Fill in the CONFIG section and the TODOs before running.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict

try:
    import frontmatter  # pip install python-frontmatter
except ImportError:
    raise SystemExit("Please `pip install python-frontmatter` before running.")

# ---------- CONFIG ------------------------------------------------------------

# Source & destination paths – ***edit these***
SOURCE_MD_DIR = Path("/path/to/source/markdown")
SOURCE_IMG_DIR = Path("/path/to/source/images")
DEST_MD_DIR   = Path("/absolute/path/to/_posts")
DEST_IMG_DIR  = Path("/absolute/path/to/assets/img")

# Replacement map for [[wiki links]]
WIKILINK_REPLACEMENTS: Dict[str, str] = {
    # "old term": "new term",
}

# Jekyll‑compatible front‑matter template – ***adjust fields as needed***
def build_new_frontmatter(original: Dict) -> Dict:
    """Return a dict representing the new front‑matter."""
    if "title" in original:
        title = original["title"]
    else:
        # Fallback: derive title from filename
        title = original.get("slug") or original.get("file_stem", "Untitled")
    new = {
        "layout": "post",
        "title": title,
        "date": original.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
        "tags": original.get("tags", []),
        # TODO: add/remove fields as required, e.g. "image", "categories"
    }
    return new

# -----------------------------------------------------------------------------

IMAGE_PATTERN = re.compile(r"!\\[\\[([^|\\]]+)(?:\\|[^\\]]*)?\\]\\]")  # ![[image.png|500]]
WIKILINK_PATTERN = re.compile(r"\\[\\[([^\\]]+)\\]\\]")               # [[some term]]


def extract_and_copy_image(img_name: str) -> str:
    """Copy image to DEST_IMG_DIR and return its relative Jekyll path."""
    src_path = SOURCE_IMG_DIR / img_name
    if not src_path.exists():
        print(f"⚠ Image not found: {src_path}")
        return img_name  # leave as‑is
    DEST_IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = DEST_IMG_DIR / img_name
    shutil.copy2(src_path, dest_path)
    # Return path relative to markdown file, e.g. /assets/img/…
    rel_path = "/" + str(DEST_IMG_DIR.relative_to(DEST_MD_DIR.parent) / img_name).replace("\\", "/")
    return rel_path


def transform_content(body: str) -> str:
    """Transform body: convert image embeds & wikilinks."""

    def _img_repl(match):
        img_name = match.group(1)
        new_path = extract_and_copy_image(img_name)
        return f"![{img_name}]({new_path})"

    body = IMAGE_PATTERN.sub(_img_repl, body)

    def _wiki_repl(match):
        term = match.group(1)
        return WIKILINK_REPLACEMENTS.get(term, term)

    body = WIKILINK_PATTERN.sub(_wiki_repl, body)

    return body


def process_file(md_path: Path):
    post = frontmatter.load(md_path)
    tags = post.get("tags", [])
    if "blog" not in tags:
        return  # Skip non‑blog notes

    new_fm = build_new_frontmatter(post.metadata)
    new_body = transform_content(post.content)

    # Reconstruct and write
    new_post = frontmatter.Post(new_body, **new_fm)

    # Jekyll wants filenames like YYYY‑MM‑DD‑slug.md
    date_str = new_fm["date"].split()[0]  # YYYY-MM-DD
    slug = md_path.stem.replace(" ", "-").lower()
    dest_filename = f"{date_str}-{slug}.md"
    DEST_MD_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = DEST_MD_DIR / dest_filename
    with dest_path.open("w", encoding="utf-8") as f:
        frontmatter.dump(new_post, f)
    print(f"✓ {md_path.name} -> {dest_path.relative_to(DEST_MD_DIR.parent)}")


def main():
    for md_path in SOURCE_MD_DIR.glob("**/*.md"):
        process_file(md_path)


if __name__ == "__main__":
    main()
