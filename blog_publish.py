"""
Script to copy markdown files tagged with **blog** in their YAML front‑matter into
Jekyll‑ready posts while:

1. Replacing the entire front‑matter with a Jekyll template you control.
2. Copying Obsidian‑style embedded images (`![[image.png|500]]`) into a target
   assets folder and converting the syntax to standard Markdown.
3. Turning Obsidian wiki‑links (`[[Page]]`, `[[Page|Display]]`) into plain text:
      • Use the *display text* (`Display`) if provided.
      • Otherwise emit the page name without the surrounding brackets.
      • Optionally pipe the page name through `WIKILINK_REPLACEMENTS` for custom
        substitutions.
4. Setting `title-image` in the new front‑matter to the **first** embedded image
   (copied as above) or a configurable default.

Edit the CONFIG section before running.
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional

try:
    import frontmatter  # pip install python-frontmatter
except ImportError:
    raise SystemExit("Please `pip install python-frontmatter` before running.")

# ---------- CONFIG ------------------------------------------------------------

SOURCE_MD_DIR = Path("~/Dropbox/bin/obsidian/test/test_source").expanduser()
SOURCE_IMG_DIR = Path("~/Dropbox/bin/obsidian/test/test_image").expanduser()
DEST_MD_DIR   = Path("~/Dropbox/bin/obsidian/test/_post").expanduser()
DEST_IMG_DIR  = Path("~/Dropbox/bin/obsidian/test/image").expanduser()

# Default fallback image (relative to your site root)
DEFAULT_TITLE_IMAGE = "/images/default_title_image.png"

# Optional custom replacements for wiki‑links **without** display text
#   e.g. {"RFC 3339": "RFC‑3339"}  —> [[RFC 3339]] → RFC‑3339
WIKILINK_REPLACEMENTS: Dict[str, str] = {}

# -----------------------------------------------------------------------------

# ![[image.png|500]] or ![[image.png]]
IMAGE_PATTERN = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")

# [[Page]]            → group(1) = Page, group(2) = None
# [[Page|Display]]    → group(1) = Page, group(2) = Display
WIKILINK_PATTERN = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")

# --------------------------- Helper functions --------------------------------

def build_new_frontmatter(original: Dict) -> Dict:
    """Return a base Jekyll front‑matter dict (title‑image added later)."""
    title = original.get("title") or original.get("slug") or original.get("file_stem", "Untitled")
    return {
        "layout": "post",
        "categories": "blog",
        "title": title,
        "date": original.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
        "tags": original.get("tags", []),
    }


def extract_and_copy_image(img_name: str) -> str:
    """Copy *img_name* to DEST_IMG_DIR and return a site‑relative path."""
    src_path = SOURCE_IMG_DIR / img_name
    if not src_path.exists():
        print(f"⚠ Image not found: {src_path}")
        return img_name  # keep placeholder so broken link is obvious

    DEST_IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = DEST_IMG_DIR / img_name
    shutil.copy2(src_path, dest_path)

    rel_path = "/" + str(DEST_IMG_DIR.relative_to(DEST_MD_DIR.parent) / img_name).replace("\\", "/")
    return rel_path


def transform_content(body: str) -> Tuple[str, Optional[str]]:
    """Convert image embeds and wiki‑links; return (new_body, first_image_path)."""
    first_image_path: Optional[str] = None

    # 1) Images
    def _img_repl(match):
        nonlocal first_image_path
        img_name = match.group(1).strip()
        new_path = extract_and_copy_image(img_name)
        if first_image_path is None:
            first_image_path = new_path
        return f"![{img_name}]({new_path})"

    body = IMAGE_PATTERN.sub(_img_repl, body)

    # 2) Wiki‑links
    def _wiki_repl(match):
        page = match.group(1).strip()
        display = match.group(2)
        if display:
            return display.strip()
        # no display text → look up custom replacement or fall back to page name
        return WIKILINK_REPLACEMENTS.get(page, page)

    body = WIKILINK_PATTERN.sub(_wiki_repl, body)

    return body, first_image_path

# ------------------------------ Main pipeline --------------------------------

def process_file(md_path: Path):
    post = frontmatter.load(md_path)

    if "blog" not in post.get("tags", []):
        return  # skip non‑blog notes

    # Transform body & detect first image
    transformed_body, first_img = transform_content(post.content)

    # Assemble new front‑matter
    new_fm = build_new_frontmatter(post.metadata)
    new_fm["title-image"] = first_img or DEFAULT_TITLE_IMAGE

    new_post = frontmatter.Post(transformed_body, **new_fm)

    # Jekyll filename: YYYY-MM-DD‑slug.md
    date_str = new_fm["date"].split()[0]
    slug = md_path.stem.replace(" ", "-").lower()
    dest_filename = f"{date_str}-{slug}.md"

    DEST_MD_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = DEST_MD_DIR / dest_filename
    with dest_path.open("w", encoding="utf-8") as f:
        frontmatter.dump(new_post, f)

    print(
        f"✓ {md_path.name} → {dest_path.relative_to(DEST_MD_DIR.parent)} "
        f"(title-image: {new_fm['title-image']})"
    )


def main():
    for md_path in SOURCE_MD_DIR.glob("**/*.md"):
        process_file(md_path)


if __name__ == "__main__":
    main()
