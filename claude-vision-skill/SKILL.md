---
name: claude-vision-skill
description: Use when the user shares, pastes, or references an image (local path or URL) and you need to describe, analyze, or recognize its content, especially when the current model cannot read images directly. Run the bundled vision.js helper to convert the image into text.
---

# Vision Helper

The current model may not support native image input. When the user provides an image path or URL, do not rely on viewing the image directly. Instead run:

```bash
node <SKILL_DIR>/vision.js "<absolute image path>" "<prompt>"
```

For an image URL:

```bash
node <SKILL_DIR>/vision.js --url "<image url>" "<prompt>"
```

When the user pastes an image into the chat but no file path or URL is visible:

```bash
node <SKILL_DIR>/vision.js --clipboard "<prompt>"
```

`--clipboard` reads the current image from the system clipboard (macOS uses a bundled Swift helper, Windows uses a bundled PowerShell script; the pasted image is usually still there). If it fails, ask the user to save the image to a file and provide the absolute path.

Fallback rules (automatic):

- If a local path is given but the file does not exist, vision.js automatically falls back to the clipboard.
- If no image path or URL is given at all, vision.js automatically tries the clipboard.
- Pass `--no-fallback` to disable this behavior and fail with an explicit error instead.

Rules:

- Always use the absolute path to `vision.js`.
- Use an absolute image path for local files, or `--url` for remote images.
- Prefer `--clipboard` when the user pasted an image with no accessible path.
- Use Chinese for descriptions unless the user asks otherwise.
- Configuration: prefer a `providers.json` next to `vision.js` listing multiple vision models; `vision.js` auto-elected the best by success rate + latency and fails over to the next on error. Single-provider fallback still works via `.env` (`VISION_API_KEY`, `VISION_MODEL`, `VISION_BASE_URL`; the old `DASHSCOPE_*` names still work). Defaults target 智谱 BigModel (`glm-4.6v-flash`). Both `providers.json` and `.env` are git-ignored — never print or commit the API key.
- With multiple providers a single failure is expected (failover handles it) — only escalate if ALL providers fail.
- Extra CLI options: `--list`, `--stats`, `--provider <name>`, `--reset-stats`.
- If the API call fails, report the error to the user and ask them to check the key, model, or base URL.
