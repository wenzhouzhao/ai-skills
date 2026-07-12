---
name: macos-app-security-audit
description: >
  Generic macOS app security audit methodology. Use when the user asks to audit paid features,
  bypass IAP/license, patch ARM64 binaries, inject dylibs, manipulate Keychain, replay network
  traffic, or perform macOS app pentesting.
model: claude-fable-5
tools: Bash, Read, Write, Edit, Glob, Grep
---

# macOS App Security Audit

Generic security audit playbook for macOS applications. Covers reconnaissance, attack surface mapping,
ARM64 binary patching, dylib injection, network replay, Keychain manipulation, time tampering, and
standardized vulnerability reporting.

## Instructions

Read `SKILL.md` for the full methodology. Start with Phase 1 recon:

```bash
bash scripts/macos_recon.sh /path/to/Target.app
```

## Quick Reference

### Recon (Phase 1)

```bash
# One-shot recon
bash scripts/macos_recon.sh /path/to/Target.app

# Manual key commands
codesign -dvvv /path/to/Target.app 2>&1
otool -f /path/to/Target.app/Contents/MacOS/<binary>
plutil -p /path/to/Target.app/Contents/Info.plist | grep CFBundleIdentifier
strings /path/to/Target.app/Contents/MacOS/<binary> | grep -iE 'purchas|premium|license|trial|expir'
```

### Attack Vectors (Phase 3) — by priority

| # | Vector | When to use | Command |
|---|--------|------------|---------|
| 1 | Plist/UserDefaults tampering | Local state storage found | `defaults write <bundle-id> <key> -bool true` |
| 2 | Time tampering | Trial expiration checked locally | `sudo systemsetup -setdate "01/01/2025"` |
| 3 | ARM64 binary patch | Conditional branches found | `xxd` + `dd` (see SKILL.md §3.2) |
| 4 | Network replay | Server-side validation without anti-replay | `mitmproxy -s bypass.py -p 8080` |
| 5 | dylib injection | `disable-library-validation` entitlement | `DYLD_INSERT_LIBRARIES=hook.dylib <binary>` |
| 6 | Keychain manipulation | Paid state in Keychain | `security delete-generic-password -s "<name>"` |

### ARM64 Patch Quick Reference

| Original | Patched | Encoding change | Effect |
|----------|---------|----------------|--------|
| `CBZ X0, loc` | `B loc` | `0x34xxxxxx` → `0x14xxxxxx` | Conditional → unconditional branch |
| `CBNZ X0, loc` | `NOP` | `0x35xxxxxx` → `0xD503201F` | Skip conditional branch |
| `MOVZ X0, #0` | `MOVZ X0, #1` | `0xD2800000` → `0xD2800020` | Return true instead of false |

### Post-patch

```bash
sudo codesign --force --deep --sign - /path/to/Target.app
tccutil reset All <bundle-id>
```

## Reference Documents

- `references/attack-surface-taxonomy.md` — Attack surface taxonomy table
- `references/binary-patching-primer.md` — ARM64 patch patterns reference
- `references/report-template.md` — Vulnerability report template

## Requirements

- macOS 14+ with built-in tools: `codesign`, `otool`, `strings`, `plutil`, `xxd`, `file`, `security`
- Optional: `mitmproxy`, `Proxyman`, `Hopper`, `Ghidra`
