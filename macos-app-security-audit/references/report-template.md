# Vulnerability Report Template

Standardized template for macOS application security vulnerability reports.

---

## Report Metadata

| Field | Value |
|-------|-------|
| **Report ID** | `SEC-YYYY-XXX` |
| **Date** | YYYY-MM-DD |
| **Researcher** | [Name / Team] |
| **Classification** | [Public / Confidential / Internal] |

---

## 1. Vulnerability Overview

### Summary

| Field | Value |
|-------|-------|
| **Title** | [App Name] [Version] — [Brief vulnerability description] |
| **CWE** | [CWE ID + Name, e.g., CWE-841: Improper Enforcement of Behavioral Workflow] |
| **CVSS v3.1** | [Score] / 10.0 ([Severity]: None/Low/Medium/High/Critical) |
| **Affected Version** | [Version number + Build] |
| **Platform** | macOS [Version] (ARM64 / x86_64) |
| **Disclosed to Vendor** | [Yes/No — Date] |

### CVSS Vector

```
CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:N
```

| Metric | Value | Justification |
|--------|-------|---------------|
| Attack Vector (AV) | Local | Physical or local shell access required |
| Attack Complexity (AC) | Low | Simple file write or binary patch |
| Privileges Required (PR) | None | No root required |
| User Interaction (UI) | None | No user interaction needed |
| Scope (S) | Unchanged | |
| Confidentiality (C) | None | No data exfiltration |
| Integrity (I) | High | Application behavior fully modified |
| Availability (A) | None | No DoS |

---

## 2. Technical Analysis

### 2.1 Attack Surface

Describe which attack surface was exploited:

- **Local state storage**: `UserDefaults` / Plist / SQLite / Keychain
- **Binary-level**: Conditional branch / return value / function logic
- **Network**: API endpoint / receipt validation / license activation
- **IPC**: XPC / distributed notifications / URL scheme

### 2.2 Control Flow Diagram

```
[User Action / App Launch]
        │
        ▼
[Condition Check: isPurchased? / isValid? / isTrialExpired?]
        │
   ┌────┴────┐
   ▼         ▼
[Paid path]  [Restricted path]
(full access) (watermark / limited features / upsell)
```

### 2.3 Root Cause

Explain the fundamental flaw:

- The paid state is stored as a plaintext boolean in `UserDefaults` with no integrity protection (no HMAC, no server-side verification).
- The conditional branch `CBZ X0, watermark_code` at VM address `0x...` gates access to the restricted path; replacing it with `B watermark_code` unconditionally skips the restriction.
- etc.

### 2.4 Affected Features

List all paid/premium features that can be unlocked:

1. [Feature A]
2. [Feature B]
3. ...

---

## 3. Reproduction Steps

### 3.1 Environment

| Item | Detail |
|------|--------|
| macOS Version | [e.g., 14.6] |
| Architecture | [ARM64 / x86_64] |
| App Version | [Version + Build] |
| Tools Required | [e.g., codesign, xxd, dd, mitmproxy] |
| Permissions Required | [e.g., None / sudo for binary patch] |

### 3.2 Step-by-Step

```
1. [Step 1 description]
   $ command

2. [Step 2 description]
   $ command

3. [Step 3 description]
   $ command

4. Verify:
   - Expected (normal): [restriction present]
   - Actual (after attack): [restriction bypassed]
```

### 3.3 Evidence

- Screenshots before/after
- Terminal output logs
- Binary diff output

---

## 4. Attack Complexity Assessment

| Dimension | Rating | Notes |
|-----------|--------|-------|
| **Technical Skill** | [Novice / Intermediate / Advanced] | ... |
| **Time Required** | [< 5 min / < 30 min / < 2 hr / > 2 hr] | ... |
| **Tools Required** | [Built-in only / Requires 3rd party / Specialized hardware] | ... |
| **Automation Potential** | [Fully / Partially / Manual] | ... |
| **Detection Difficulty** | [Trivial / Moderate / Hard / Nearly Impossible] | ... |
| **Persistence** | [Survives reboot / Survives reinstall / Lost on update] | ... |

---

## 5. Remediation Recommendations

### P0 — Immediate (Should implement within 1 sprint)

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 1 | Move paid-state validation to server-side | Current local-only check is trivially bypassable |
| 2 | Add HMAC signature to UserDefaults values | Prevents undetected tampering without server round-trip |
| 3 | Implement binary integrity check (CRC/checksum of `__TEXT`) | Detects binary patching at runtime |

### P1 — Short-term (Within 1 month)

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 1 | Add receipt refresh + server validation on every cold launch | Prevents stale receipt reuse |
| 2 | Enable Hardened Runtime with library validation | Prevents dylib injection |
| 3 | Implement certificate pinning for critical API endpoints | Prevents MITM-based response tampering |

### P2 — Long-term (Architecture improvement)

| # | Recommendation | Rationale |
|---|---------------|-----------|
| 1 | Adopt on-device cryptographic attestation for license state | Defense-in-depth against local tampering |
| 2 | Implement runtime anti-tampering with multiple detection layers | Raise the bar for binary-level attacks |
| 3 | Periodic server-signed nonce challenge to verify client integrity | Prevents offline replay attacks indefinitely |

---

## 6. References

- [Link to relevant CWE]
- [Link to binary patching primer]
- [Link to Apple Security Documentation]
- ...

---

## Appendix A: Patch Details (if applicable)

```
File:      /path/to/Target.app/Contents/MacOS/<binary>
Offset:    0xXXXXXX (file offset)
Original:  0xXXXXXXXX (hex bytes) — [Mnemonic]
Patched:   0xXXXXXXXX (hex bytes) — [Mnemonic]
VM Addr:   0xXXXXXXXXXX
```

```bash
# Read original
xxd -s <offset> -l 4 -p <binary>

# Apply patch
echo "<new_hex>" | xxd -r -p | dd of=<binary> bs=1 seek=<offset> conv=notrunc

# Re-sign
sudo codesign --force --deep --sign - /path/to/Target.app
```

## Appendix B: Post-Patch Checklist

- [ ] Binary backup created: `<binary>.bak`
- [ ] Patch applied and verified via `xxd`
- [ ] App re-signed: `codesign --force --deep --sign -`
- [ ] TCC permissions reset: `tccutil reset All <bundle-id>`
- [ ] App launches without crash
- [ ] Patched behavior confirmed
- [ ] All findings documented in this report
