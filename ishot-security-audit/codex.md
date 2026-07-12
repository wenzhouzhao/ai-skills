---
name: ishot-security-audit
description: >
  Security audit and watermark bypass for iShot screenshot app.
  Use when the user asks to audit iShot's paid watermark protection,
  bypass iShot watermark, crack iShot, or perform binary patch attack.
model: claude-fable-5
tools: Bash, Read, Write, Edit
---

# iShot Security Audit

Security audit and watermark bypass for iShot v2.6.7 screenshot app. Tests paid watermark protection via ARM64 binary patching, Plist tampering, and code signing analysis.

## Instructions

Read `SKILL.md` for the full methodology and reference documents, then use the core script:

```bash
cd <project_root>/ishot-security-audit && python3 ishot_security_tester.py <command>
```

## Commands

| Command | Description | Requires sudo |
|---------|-------------|---------------|
| `auto` | One-click attack (verify + patch) | Yes |
| `dry-run` | Verify patch points without modifying files | No |
| `attack` | Execute CBZ→B binary patch attack | Yes |
| `plist` | Plist tampering test (proves this vector is ineffective) | No |
| `restore` | Restore original binary from backup | Yes |
| `status` | Show current patch status | No |
| `report` | Generate test report | No |

## Standard Workflow

```bash
# Step 1: Check current status
python3 ishot_security_tester.py status

# Step 2: Verify attack feasibility (no modification)
python3 ishot_security_tester.py dry-run

# Step 3: Execute attack
sudo python3 ishot_security_tester.py attack

# Step 4: Re-sign and reset permissions (signature invalidated by patch)
sudo codesign --force --deep --sign - /Applications/iShot.app
tccutil reset ScreenCapture cn.better365.ishot

# Step 5: Test — take a long screenshot, watermark should be gone
```

## Attack Vectors

### Plist Tampering (INEFFECTIVE)
`iShotHavePurchased` is an output marker, not an input switch. Reset to false on every app launch.

### ARM64 CBZ→B Patch (EFFECTIVE)
Replaces 3 conditional branch instructions with unconditional branches, permanently skipping watermark rendering.

| # | Feature | VM Address | Fat Offset | CBZ→B |
|---|---------|-----------|------------|-------|
| 1 | Long screenshot watermark | `0x10001A15C` | `0x23615C` | `0x34000648`→`0x14000032` |
| 2 | Fullscreen framed screenshot | `0x10005F6C0` | `0x27B6C0` | `0x340005A8`→`0x1400002D` |
| 3 | Normal screenshot watermark | `0x1000B2858` | `0x2CE858` | `0x34000648`→`0x14000032` |

## Recovery

```bash
sudo python3 ishot_security_tester.py restore
sudo codesign --force --deep --sign - /Applications/iShot.app
```

## Reference Documents

- `references/attack-reproduction.md` — Full attack reproduction guide
- `references/binary-reverse-engineering.md` — ARM64 binary reverse engineering details
- `references/plist-i-analysis.md` — Plist analysis and IAP flow reverse engineering

## Requirements

- Python 3 (stdlib only)
- macOS built-in tools: `otool`, `xxd`, `strings`, `codesign`, `tccutil`
