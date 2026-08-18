# AGENTS.md

## Purpose

This repo provides a lightweight vision helper for agents without native image input. When an image cannot be read directly, use `vision.js` to convert it into text through a configured vision API.

## When to use

- Image path: `node vision.js "<absolute image path>" "<prompt>"`
- Image URL: `node vision.js --url "<image url>" "<prompt>"`
- Pasted image with no accessible path/URL: `node vision.js --clipboard "<prompt>"`

Fallback rules:

- If a local path does not exist, or no path/URL is provided, `vision.js` automatically tries the system clipboard.
- Pass `--no-fallback` to disable automatic clipboard fallback and fail with an explicit error.

## Configuration

**Multi-provider (preferred):** place a `providers.json` next to `vision.js` listing every vision model you want to use. `vision.js` will auto-elect the best one by historical success rate + latency, and fail over to the next on any error. Example:

```json
{
  "providers": [
    { "name": "zhipu", "apiKey": "KEY", "model": "glm-4.6v-flash",
      "baseUrl": "https://open.bigmodel.cn/api/paas/v4", "localImage": true },
    { "name": "agnes", "apiKey": "KEY", "model": "agnes-2.5-flash",
      "baseUrl": "https://apihub.agnes-ai.com/v1", "localImage": false },
    { "name": "tencent-youtu", "apiKey": "KEY", "model": "youtu-vita",
      "baseUrl": "https://tokenhub.tencentmaas.com/v1", "localImage": true }
  ]
}
```

- `localImage: false` means the provider only accepts a public `image_url` (e.g. Agnes); local-file / clipboard inputs skip it automatically.
- **Public-URL priority:** when the input is a public `http(s)` image (`--url`), providers with `localImage: false` get a deterministic priority boost (no random exploration) so they are selected first — ideal for URL-only services and for testing against public images.
- `providers.json` is git-ignored — never commit it.

**Single provider (backward compatible):** if no `providers.json`, credentials come from `VISION_API_KEY`, `VISION_MODEL`, and `VISION_BASE_URL`, as environment variables or a `.env` file next to `vision.js`. The old `DASHSCOPE_*` names are still accepted as a fallback. Defaults target 智谱 BigModel (`glm-4.6v-flash` at `https://open.bigmodel.cn/api/paas/v4`). `.env` is git-ignored — never commit it.

Extra CLI options: `--list` (list providers), `--stats` (show election stats), `--provider <name>` (force one, skip election), `--reset-stats` (clear learned stats).

## Rules

- Always use the absolute path to `vision.js`.
- Never print or share the API key.
- If the API call fails, report the error and ask the user to check the key, model, or base URL.
- With multiple providers, a single failure is expected and handled by failover — only escalate if ALL providers fail.
