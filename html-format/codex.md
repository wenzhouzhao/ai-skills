---
name: html-format
description: Format single-line/minified HTML files into readable multi-line HTML
model: claude-fable-5
tools: Bash
---

# HTML Format

Format single-line, minified, or JSON-wrapped HTML files into readable, indented HTML.

## Instructions

When the user asks to format HTML files, run the core script:

```bash
python3 <project_root>/html-format/format.py <target_directory_or_files>
```

The script auto-detects 4 HTML formats and picks the right strategy:

| Type | Signature | Strategy |
|------|-----------|----------|
| A | `Script ran on page` header (web-clone output) | JSON extract → fix void elements → prettier |
| B | `SingleFile` header (massive base64 inline) | Python structural line breaks |
| C | Standard minified HTML | prettier |
| D | `<meta></meta>` void element errors | Fix voids → prettier |

## Usage Examples

```bash
# Format all .html files in current directory
python3 /path/to/ai-skills/html-format/format.py .

# Format specific files
python3 /path/to/ai-skills/html-format/format.py a.html b.html

# Format files in a directory
python3 /path/to/ai-skills/html-format/format.py /path/to/dir
```

## Requirements

- Python 3 (stdlib only)
- Node.js + prettier (types A/C/D only; resolved from `PRETTIER_BIN` →
  `node_modules/.bin/prettier` → global `prettier` → npx cache → `npx --yes prettier`,
  so it also works offline when a cached copy exists)

## Notes

- Always run `format.py` — don't try to replicate its logic inline
- If prettier fails on a file, the script auto-falls back to Python formatting
- SingleFile (Type B) inline base64 blocks are automatically extracted to
  standalone `images/` and `fonts/` files, and the `data:` URIs are replaced
  with relative paths — this shrinks the HTML dramatically and keeps page rendering intact
- Extraction dedupes by content hash (sha256) within each directory, and continues
  numbering from existing files, so re-running is safe and won't overwrite assets
- Files with no inline base64 are skipped (no unnecessary writes)
- **Semantic filenames (default):** extracted assets are named from context —
  `<img alt>` → `id`/`class` → `rel` (icon→favicon, apple-touch-icon, etc.) →
  CSS selector (for `background-image`) → `font-family`+weight inside `@font-face`
  (e.g. `noto-sans-tc-100.woff2`). Falls back to `<prefix>_NNNN` when no context is
  available; same-name/different-content gets a `-2`/`-3` suffix.
  Pass `--sequential` to force plain `<prefix>_NNNN` naming.
- `images/` and `fonts/` directories are created lazily — a site with no fonts
  won't get an empty `fonts/` directory
- **Never rely on bare `npx prettier`**: npx re-resolves the latest version from the
  registry on every run, so a cached prettier gets re-downloaded and the command
  hangs (or is killed) offline. `resolve_prettier()` handles this; the chosen
  prettier path is printed at runtime.
