---
name: web-clone
description: Clone/ replicate websites. Use when the user asks to clone a website, reproduce a site, or copy a web page's design.
model: claude-fable-5
tools: Bash, WebFetch, WebSearch
---

# Web Clone

Clone websites using a systematic methodology. This skill provides a decision tree for different site types (static, React/Vue/Next, WebGL/Canvas).

## Instructions

Read `SKILL.md` for the full methodology, then follow its decision tree step by step:

1. **Step 1**: Search GitHub for source code first (`gh api "search/repositories?q=<keywords>"`)
2. **Step 2**: If no source found, use browser reconnaissance to detect tech stack
3. **Step 3**: Choose the right path based on recon results (static mirror vs template rebuild vs reverse-engineer)
4. **Step 4**: Set up project structure
5. **Step 5**: Remove tracking scripts, write NOTES.md, verify in browser
6. **Step 6**: Replace content with user's own content

The `scripts/` directory contains helper scripts (Node.js) for reconnaissance, asset harvesting, network capture, route crawling, interaction probing, sourcemap hunting, comparison, and auditing.

## Key Rules

- Always try to find real source code before scraping
- Never trust AI-generated analysis code without verifying against real source
- For WebGL/Canvas sites, do deep reverse engineering of real source
- Always verify the clone in a real browser (not just code inspection)
- Check license before cloning

## Requirements

- Node.js for scripts
- Playwright for browser automation

## Source

Originally from https://github.com/Jane-xiaoer/claude-skill-web-clone
