---
name: claude-vision-skill
description: Use ONLY when the current model CANNOT read images natively (no vision capability). When the user shares/pastes/references an image and you must describe or analyze it, run the bundled vision.js to convert the image into text via an external vision model. Do NOT use this skill if your model already supports image input — just answer from the image directly.
---

# Vision Helper

> **Critical precondition — read first.** Only use this skill when the **current model lacks native image understanding**. If you (the agent) can already see and understand the image directly (e.g. Claude/GPT-4o/Gemini/Qwen-VL with vision), **DO NOT invoke this skill** — describe or analyze the image yourself. This skill is purely a fallback for non-vision models.

## When NOT to use

- The active model is multimodal and can read the image on its own → skip this skill, answer directly.
- You already have a textual description / OCR result of the image → use that, don't re-run vision.
- The image is irrelevant to the task → don't call vision at all.

If unsure whether your model has vision, prefer answering directly; only fall back to this skill when direct image understanding clearly fails.

When the model genuinely cannot see images, and the user provides an image path or URL, run:

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
- **Disabling on a multimodal host:** set env `VISION_SKIP=1` (or put `"enabled": false` at the top level of `providers.json`). When set, `vision.js` prints a `SKIPPED` message and exits without any API call — a deterministic off-switch for environments whose model is already multimodal.
- If the API call fails, report the error to the user and ask them to check the key, model, or base URL.
