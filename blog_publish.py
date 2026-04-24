"""
Script to copy markdown files tagged with **blog** in their YAML front‑matter into
Jekyll‑ready posts while:

1. Replacing the entire front‑matter with a Jekyll template you control.
2. Copying Obsidian‑style embedded images (`![[image.png|500]]`) into a target
   assets folder and converting the syntax to standard Markdown (preserving any
   explicit size like `|500` → `{: width="500" }`). Broken links fall back to a
   site‑wide default `title-image` and remain visibly broken in the body.
3. Turning Obsidian wiki‑links (`[[Page]]`, `[[Page|Display]]`) into plain text.
4. Copying/overwriting **only** when the source file is newer than the most
   recent exported version (mtime check).
5. Deriving and storing an **excerpt** (first real paragraph) in front‑matter—
   clipped at the nearest sentence boundary (up to `EXCERPT_MAX` chars).
6. Recording `last_updated` from the post's footer version history.
7. Removing any draft blocks delimited by `{draft}` … `{end draft}`.
8. Optionally generating a *news* post announcing an update when the script is
   run with `--create-update-posts`. The announcement matches the format in
   `2025-07-25-public-forecast-update.md`: categories `news`, layout `post`, tags
   `[blog]`, the current timestamp, and a one‑sentence body linking to the
   updated article.

### Date handling
`date:` may be a full timestamp, a simple date, or absent; all normalised.
"""

import argparse
import re
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Tuple, Optional

try:
    import frontmatter  # pip install python-frontmatter
except ImportError:
    raise SystemExit("Please `pip install python-frontmatter` before running.")

# ---------- CONFIG ------------------------------------------------------------

SOURCE_MD_DIR = Path("~/Dropbox/documents/Networked Notes/all").expanduser()
SOURCE_IMG_DIR = Path("~/Dropbox/documents/Networked Notes/files").expanduser()
DEST_MD_DIR   = Path("~/Dropbox/bin/web/jshrader.github.io/_posts").expanduser()
DEST_IMG_DIR  = Path("~/Dropbox/bin/web/jshrader.github.io/images").expanduser()

# Testing directories (keep commented!)
# SOURCE_MD_DIR = Path("~/Dropbox/bin/obsidian/test/test_source").expanduser()
# SOURCE_IMG_DIR = Path("~/Dropbox/bin/obsidian/test/test_image").expanduser()
# DEST_MD_DIR   = Path("~/Dropbox/bin/obsidian/test/_posts").expanduser()
# DEST_IMG_DIR  = Path("~/Dropbox/bin/obsidian/test/images").expanduser()

DEFAULT_TITLE_IMAGE = "/images/default_title_image.png"
WIKILINK_REPLACEMENTS: Dict[str, str] = {}

# Maximum characters for excerpt; adjust to taste. If None, no hard cap.
EXCERPT_MAX = 500

# -----------------------------------------------------------------------------

IMAGE_PATTERN = re.compile(r"!\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
WIKILINK_PATTERN = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
DRAFT_PATTERN = re.compile(r"{draft}[\s\S]*?{\s*end draft\s*}", flags=re.IGNORECASE)
VERSION_HISTORY_PATTERN = re.compile(
    r"Version history<br>\s*(.*?)</p>", flags=re.IGNORECASE | re.DOTALL
)
VERSION_HISTORY_DATE_PATTERN = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)\s*:")

# --------------------------- Helper functions --------------------------------

def _normalise_date(raw_date) -> str:
    if isinstance(raw_date, datetime):
        return raw_date.strftime("%Y-%m-%d %H:%M")
    if isinstance(raw_date, date):
        return raw_date.isoformat()
    if isinstance(raw_date, str) and raw_date.strip():
        return raw_date.strip()
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _coerce_to_date(raw_date) -> Optional[date]:
    if isinstance(raw_date, datetime):
        return raw_date.date()
    if isinstance(raw_date, date):
        return raw_date
    if isinstance(raw_date, str) and raw_date.strip():
        raw_date = raw_date.strip()
        try:
            return datetime.fromisoformat(raw_date).date()
        except ValueError:
            try:
                return date.fromisoformat(raw_date.split()[0])
            except ValueError:
                return None
    return None


def build_new_frontmatter(original: Dict, fallback_title: str) -> Dict:
    title = original.get("title") or original.get("slug") or fallback_title
    date_str = _normalise_date(original.get("date"))
    return {
        "layout": "post",
        "categories": "blog",
        "title": title,
        "date": date_str,
        "tags": original.get("tags", []),
        # "excerpt" and "title-image" injected later
    }


def extract_and_copy_image(img_name: str) -> Optional[str]:
    src_path = SOURCE_IMG_DIR / img_name
    if not src_path.exists():
        print(f"⚠ Image not found: {src_path}")
        return None
    DEST_IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = DEST_IMG_DIR / img_name
    shutil.copy2(src_path, dest_path)
    rel_path = "/" + str(DEST_IMG_DIR.relative_to(DEST_MD_DIR.parent) / img_name).replace("\\", "/")
    return rel_path


def transform_content(body: str) -> Tuple[str, Optional[str]]:
    """Return (clean_body, first_valid_image_path)."""
    body = DRAFT_PATTERN.sub("", body)  # strip draft blocks

    first_image_path: Optional[str] = None

    def _img_repl(match):
        nonlocal first_image_path
        img_name = match.group(1).strip()
        size_spec = match.group(2)
        new_path = extract_and_copy_image(img_name)
        if new_path and first_image_path is None:
            first_image_path = new_path
        if new_path is None:
            return match.group(0)
        if size_spec and size_spec.isdigit():
            return f"![{img_name}]({new_path}){{: width=\"{size_spec}\" }}"
        return f"![{img_name}]({new_path})"

    body = IMAGE_PATTERN.sub(_img_repl, body)

    def _wiki_repl(match):
        page, display = match.group(1).strip(), match.group(2)
        return display.strip() if display else WIKILINK_REPLACEMENTS.get(page, page)

    body = WIKILINK_PATTERN.sub(_wiki_repl, body)
    return body, first_image_path


def _sentence_clip(text: str, limit: Optional[int]) -> str:
    if limit is None or len(text) <= limit:
        return text
    cutoff = text.rfind('.', 0, limit)
    return (text[:cutoff + 1] if cutoff != -1 else text[:limit]).rstrip()


def extract_excerpt(markdown_body: str) -> str:
    lines = markdown_body.splitlines()
    para_lines, in_para = [], False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_para and para_lines:
                break
            continue
        if stripped.startswith('#') or stripped.startswith('!['):
            continue
        in_para = True
        para_lines.append(stripped)
    paragraph = ' '.join(para_lines).strip()
    return _sentence_clip(paragraph, EXCERPT_MAX)


def extract_last_updated(markdown_body: str, published_date):
    published_day = _coerce_to_date(published_date)
    version_history = VERSION_HISTORY_PATTERN.search(markdown_body)

    if version_history:
        version_dates = [
            datetime.strptime(match.group(1), "%Y-%m-%d").date()
            for match in VERSION_HISTORY_DATE_PATTERN.finditer(version_history.group(1))
        ]
        if version_dates:
            latest_version_day = max(version_dates)
            if published_day is not None:
                latest_version_day = max(latest_version_day, published_day)
            return latest_version_day

    if published_day is not None:
        return published_day
    return _normalise_date(published_date).split()[0]


def has_blog_tag(post) -> bool:
    tags = post.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    return "blog" in tags


def _normalise_title_for_match(title: str) -> str:
    return " ".join(title.strip().split()).casefold()


def find_post_by_title(post_title: str) -> Path:
    wanted = _normalise_title_for_match(post_title)
    matches = []

    for md_path in SOURCE_MD_DIR.rglob("*.md"):
        post = frontmatter.load(md_path)
        if not has_blog_tag(post):
            continue

        candidate_titles = {_normalise_title_for_match(md_path.stem)}
        title = post.get("title")
        if isinstance(title, str) and title.strip():
            candidate_titles.add(_normalise_title_for_match(title))

        if wanted in candidate_titles:
            matches.append(md_path)

    if not matches:
        raise SystemExit(f'No blog-tagged source note found for "{post_title}".')
    if len(matches) > 1:
        match_list = ", ".join(path.name for path in matches)
        raise SystemExit(
            f'Multiple blog-tagged source notes match "{post_title}": {match_list}'
        )
    return matches[0]

# ------------------------------ Update‑post helper ---------------------------

def create_update_post(title: str, slug: str):
    """Write a news post announcing that *title*/*slug* was updated."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M")
    fm = {
        "layout": "post",
        "categories": "news",
        "title": f"Update: {title}",
        "date": date_str,
        "tags": ["blog"],
    }
    body = f'The blog post "[{title}]({slug})" has been updated!'
    update_post = frontmatter.Post(body, **fm)

    filename_date = now.strftime("%Y-%m-%d")
    update_filename = f"{filename_date}-{slug}-update.md"
    dest_path = DEST_MD_DIR / update_filename
    # Avoid clutter: if a news update with same filename already exists, append a counter
    counter = 1
    while dest_path.exists():
        dest_path = DEST_MD_DIR / f"{filename_date}-{slug}-update-{counter}.md"
        counter += 1
    with dest_path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(update_post))
    print(f"  ↳ update post created: {dest_path.name}")

# ------------------------------ Main pipeline --------------------------------

def most_recent_dest(slug: str) -> Optional[Path]:
    candidates = list(DEST_MD_DIR.glob(f"*-{slug}.md"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def process_file(md_path: Path, create_update_posts: bool = False):
    post = frontmatter.load(md_path)
    if not has_blog_tag(post):
        return

    slug = md_path.stem.replace(" ", "-").lower()
    latest_dest = most_recent_dest(slug)
    source_mtime = md_path.stat().st_mtime
    if latest_dest and source_mtime <= latest_dest.stat().st_mtime:
        print(f"— {md_path.name} is up‑to‑date (no changes)")
        return

    # ---------------- Transform & write primary post ------------------------
    transformed_body, first_img = transform_content(post.content)
    fallback_title = md_path.stem.replace('-', ' ').replace('_', ' ').title()
    new_fm = build_new_frontmatter(post.metadata, fallback_title)
    new_fm["title-image"] = first_img or DEFAULT_TITLE_IMAGE
    new_fm["excerpt"] = extract_excerpt(transformed_body)
    new_fm["last_updated"] = extract_last_updated(transformed_body, new_fm["date"])

    new_post = frontmatter.Post(transformed_body, **new_fm)
    date_str = new_fm["date"].split()[0]
    dest_filename = f"{date_str}-{slug}.md"

    DEST_MD_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = DEST_MD_DIR / dest_filename
    with dest_path.open("w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(new_post))

    print(
        f"✓ {md_path.name} → {dest_path.relative_to(DEST_MD_DIR.parent)} "
        f"(title-image: {new_fm['title-image']})"
    )

    if create_update_posts:
        create_update_post(new_fm["title"], slug)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Export Obsidian blog-tagged notes into Jekyll posts."
    )
    parser.add_argument(
        "post_title",
        nargs="*",
        help="title of the single blog post to export",
    )
    parser.add_argument(
        "--update-all",
        action="store_true",
        help="export all blog-tagged posts",
    )
    parser.add_argument(
        "--create-update-posts",
        action="store_true",
        help="also generate news posts announcing updated blog posts",
    )
    args = parser.parse_args(argv)

    joined_title = " ".join(args.post_title).strip()
    if args.update_all == bool(joined_title):
        parser.error("provide a post title or pass --update-all")

    args.post_title = joined_title or None
    return args


def main():
    args = parse_args()
    DEST_MD_DIR.mkdir(parents=True, exist_ok=True)
    if args.update_all:
        for md_path in SOURCE_MD_DIR.rglob("*.md"):
            process_file(md_path, create_update_posts=args.create_update_posts)
        return

    md_path = find_post_by_title(args.post_title)
    process_file(md_path, create_update_posts=args.create_update_posts)

if __name__ == "__main__":
    main()
