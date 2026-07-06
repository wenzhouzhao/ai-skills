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
- Node.js + prettier (auto-downloaded via npx for types A/C/D)

## Notes

- Always run `format.py` — don't try to replicate its logic inline
- If prettier fails on a file, the script auto-falls back to Python formatting
- SingleFile (Type B) inline base64 blocks remain as long lines (inherent format limitation)
