#!/usr/bin/env bash
#
# macos_recon.sh — macOS App Security Reconnaissance Script
# ==========================================================
#
# One-shot information gathering for any macOS application.
# Outputs structured JSON with Bundle ID, version, architecture,
# signature status, entitlements, all plist paths, and classified strings.
#
# Usage:
#   bash macos_recon.sh /path/to/Target.app [output_dir]
#
# Requirements:
#   macOS 14+ with built-in tools only: codesign, otool, strings, plutil, xxd, file, security
#
# Output:
#   <output_dir>/macos_recon_<timestamp>.json   — structured JSON
#   <output_dir>/strings_all.txt                — all extracted strings
#   <output_dir>/strings_classified.txt         — classified strings summary

set -euo pipefail

# ────────────────────────────── Argument Parsing ──────────────────────────────

APP_PATH="${1:-}"
OUTPUT_DIR="${2:-${PWD}/recon_output}"

if [[ -z "$APP_PATH" ]]; then
    echo "ERROR: No .app path provided."
    echo "Usage: bash macos_recon.sh /path/to/Target.app [output_dir]"
    exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: '$APP_PATH' is not a valid directory."
    exit 1
fi

APP_NAME=$(basename "$APP_PATH" .app)
INFO_PLIST="$APP_PATH/Contents/Info.plist"

if [[ ! -f "$INFO_PLIST" ]]; then
    echo "ERROR: Info.plist not found. Is '$APP_PATH' a valid .app bundle?"
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUTPUT_DIR"

JSON_OUT="${OUTPUT_DIR}/macos_recon_${TIMESTAMP}.json"
STRINGS_ALL="${OUTPUT_DIR}/strings_all.txt"
STRINGS_CLASSIFIED="${OUTPUT_DIR}/strings_classified.txt"

echo "[*] Reconnaissance started for: $APP_NAME"
echo "[*] Output directory: $OUTPUT_DIR"

# ────────────────────────────── Helper Functions ──────────────────────────────

json_escape() {
    # Escape a string for JSON value (basic: backslash, double-quote, newline)
    python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))" 2>/dev/null || echo "\"$*\""
}

get_binary_path() {
    # Extract the executable name from Info.plist
    local exe
    exe=$(plutil -p "$INFO_PLIST" 2>/dev/null | grep CFBundleExecutable | awk -F'"' '{print $2}')
    echo "$APP_PATH/Contents/MacOS/${exe}"
}

# ────────────────────────────── Phase 1: Basic Info ──────────────────────────

echo "[1/6] Gathering basic application information..."

BINARY_PATH=$(get_binary_path)

if [[ ! -f "$BINARY_PATH" ]]; then
    echo "ERROR: Binary not found at $BINARY_PATH"
    exit 1
fi

# Bundle ID
BUNDLE_ID=$(plutil -p "$INFO_PLIST" 2>/dev/null | grep CFBundleIdentifier | awk -F'"' '{print $2}')

# Version
BUNDLE_VERSION=$(plutil -p "$INFO_PLIST" 2>/dev/null | grep CFBundleShortVersionString | awk -F'"' '{print $2}')
BUNDLE_BUILD=$(plutil -p "$INFO_PLIST" 2>/dev/null | grep '"CFBundleVersion"' | awk -F'"' '{print $2}')

# Architecture
ARCH_INFO=$(file "$BINARY_PATH" 2>/dev/null)
ARCH_LIST=$(otool -f "$BINARY_PATH" 2>/dev/null | grep -E 'architecture' | sed 's/.*architecture //' | tr '\n' ',' | sed 's/,$//')

# ────────────────────────────── Phase 2: Signature Info ──────────────────────

echo "[2/6] Checking code signature..."

# Full codesign output
SIGN_FULL=$(codesign -dvvv "$APP_PATH" 2>&1) || SIGN_FULL="codesign failed"
SIGN_STATUS_RAW=$(codesign -v "$APP_PATH" 2>&1 && echo "valid" || echo "invalid")

# Extract key fields
AUTHORITIES=$(echo "$SIGN_FULL" | grep '^Authority=' | sed 's/Authority=//')
TEAM_ID=$(echo "$SIGN_FULL" | grep '^TeamIdentifier=' | sed 's/TeamIdentifier=//')
IDENTIFIER=$(echo "$SIGN_FULL" | grep '^Identifier=' | sed 's/Identifier=//')

# Entitlements
ENTITLEMENTS_RAW=$(codesign -d --entitlements - "$APP_PATH" 2>/dev/null | plutil -p - 2>/dev/null) || ENTITLEMENTS_RAW=""
HAS_SANDBOX=$(echo "$ENTITLEMENTS_RAW" | grep -c "com.apple.security.app-sandbox.*true" || echo "0")
HAS_DISABLE_LIBRARY_VALIDATION=$(echo "$ENTITLEMENTS_RAW" | grep -c "com.apple.security.cs.disable-library-validation" || echo "0")

# ────────────────────────────── Phase 3: Plist Discovery ──────────────────────

echo "[3/6] Discovering plist files..."

PLIST_PATHS=""

# In-app plists
APP_PLISTS=$(find "$APP_PATH" -name "*.plist" 2>/dev/null | sort)

# UserDefaults (Preferences)
PREFS_PLISTS=$(find ~/Library/Preferences -maxdepth 1 -name "*${BUNDLE_ID}*" -o -name "*${APP_NAME}*" 2>/dev/null | sort)

# App Group containers
GROUP_CONTAINERS=$(find ~/Library/Group\ Containers -maxdepth 3 -name "*.plist" 2>/dev/null | sort)

# Sandbox container
CONTAINER_ROOT=~/Library/Containers/${BUNDLE_ID}
CONTAINER_PLISTS=""
if [[ -d "$CONTAINER_ROOT" ]]; then
    CONTAINER_PLISTS=$(find "$CONTAINER_ROOT" -maxdepth 4 -name "*.plist" 2>/dev/null | sort)
fi

# Combine all plist paths
ALL_PLISTS=$(cat <(echo "$APP_PLISTS") <(echo "$PREFS_PLISTS") <(echo "$GROUP_CONTAINERS") <(echo "$CONTAINER_PLISTS") 2>/dev/null | sort -u)

# ────────────────────────────── Phase 4: Strings Extraction ──────────────────

echo "[4/6] Extracting readable strings..."

strings "$BINARY_PATH" 2>/dev/null | grep -E '.{4,}' > "$STRINGS_ALL" || true
TOTAL_STRINGS=$(wc -l < "$STRINGS_ALL" | tr -d ' ')

# Classify strings
{
    echo "=== PAYMENT/IAP/LICENSE ==="
    grep -iE 'purchas|premium|pro|vip|subscri|license|activ|unlock|receipt|validate|verify|trial|expir|renew' "$STRINGS_ALL" || echo "(none)"

    echo ""
    echo "=== URLs / DOMAINS ==="
    grep -oE 'https?://[a-zA-Z0-9._/-]+' "$STRINGS_ALL" | sort -u || echo "(none)"

    echo ""
    echo "=== CRYPTO / ENCRYPTION ==="
    grep -iE 'AES|RSA|SHA|HMAC|base64|encrypt|decrypt|hash|cipher|sign|verify' "$STRINGS_ALL" || echo "(none)"

    echo ""
    echo "=== ANTI-DEBUG / ANTI-TAMPER ==="
    grep -iE 'ptrace|sysctl|debug|tamper|integrity|signature|jailbreak|anti.*debug|P_TRACED' "$STRINGS_ALL" || echo "(none)"

    echo ""
    echo "=== KEYCHAIN REFERENCES ==="
    grep -iE 'SecItem|Keychain|kSec|security' "$STRINGS_ALL" || echo "(none)"

    echo ""
    echo "=== FILE PATHS / DIRECTORIES ==="
    grep -E '(~/|/Users/|/Library/|/Application Support/)' "$STRINGS_ALL" | head -30 || echo "(none)"

    echo ""
    echo "=== Total strings: $TOTAL_STRINGS ==="
} > "$STRINGS_CLASSIFIED"

# ────────────────────────────── Phase 5: Additional Checks ───────────────────

echo "[5/6] Running additional checks..."

# Hardened Runtime
HAS_HARDENED_RUNTIME=$(echo "$SIGN_FULL" | grep -c "flags=.*runtime" || echo "0")

# Library validation
HAS_LIBRARY_VALIDATION=$(echo "$SIGN_FULL" | grep -c "flags=.*library-validation" || echo "0")

# Check for __RESTRICT section (anti-DYLD_INSERT_LIBRARIES)
RESTRICT_SECTION=$(otool -l "$BINARY_PATH" 2>/dev/null | grep -c "__restrict" || echo "0")

# Check for PIE (Position Independent Executable)
IS_PIE=$(otool -vh "$BINARY_PATH" 2>/dev/null | grep -c "PIE" || echo "0")

# ────────────────────────────── Phase 6: JSON Output ────────────────────────

echo "[6/6] Generating JSON output..."

# Build JSON manually for portability (no jq dependency)
python3 - "$OUTPUT_DIR" "$JSON_OUT" "$APP_NAME" "$APP_PATH" "$BINARY_PATH" \
    "$BUNDLE_ID" "$BUNDLE_VERSION" "$BUNDLE_BUILD" "$ARCH_INFO" "$ARCH_LIST" \
    "$SIGN_STATUS_RAW" "$SIGN_FULL" "$AUTHORITIES" "$TEAM_ID" "$IDENTIFIER" \
    "$ENTITLEMENTS_RAW" "$HAS_SANDBOX" "$HAS_DISABLE_LIBRARY_VALIDATION" \
    "$HAS_HARDENED_RUNTIME" "$HAS_LIBRARY_VALIDATION" "$RESTRICT_SECTION" "$IS_PIE" \
    "$TOTAL_STRINGS" "$STRINGS_ALL" "$STRINGS_CLASSIFIED" \
    "$APP_PLISTS" "$PREFS_PLISTS" "$GROUP_CONTAINERS" "$CONTAINER_PLISTS" << 'PYEOF'
import sys, json, os

(out_dir, json_out, app_name, app_path, binary_path,
 bundle_id, version, build, arch_info, arch_list,
 sign_status, sign_full, authorities, team_id, identifier,
 entitlements, has_sandbox, has_disable_lib_val,
 has_hardened_runtime, has_lib_validation, restrict_section, is_pie,
 total_strings, strings_all, strings_classified,
 app_plists, prefs_plists, group_containers, container_plists) = sys.argv[1:]

def lines(s):
    return [l.strip() for l in s.split('\n') if l.strip()] if s else []

result = {
    "app_name": app_name,
    "app_path": app_path,
    "binary_path": binary_path,
    "bundle_id": bundle_id,
    "version": version,
    "build": build,
    "architecture": {
        "raw": arch_info.strip(),
        "architectures": [a.strip() for a in arch_list.split(',') if a.strip()]
    },
    "signature": {
        "status": sign_status.strip(),
        "team_identifier": team_id.strip() if team_id else "",
        "identifier": identifier.strip() if identifier else "",
        "authorities": lines(authorities),
        "entitlements_raw": entitlements.strip() if entitlements else "",
        "has_sandbox": has_sandbox.strip() != "0",
        "has_disable_library_validation": has_disable_lib_val.strip() != "0",
        "has_hardened_runtime": has_hardened_runtime.strip() != "0",
        "has_library_validation": has_lib_validation.strip() != "0"
    },
    "security_hardening": {
        "has_restrict_section": restrict_section.strip() != "0",
        "is_pie": is_pie.strip() != "0"
    },
    "plist_paths": {
        "in_app": lines(app_plists),
        "preferences": lines(prefs_plists),
        "group_containers": lines(group_containers),
        "sandbox_container": lines(container_plists)
    },
    "strings": {
        "total_count": int(total_strings),
        "all_file": strings_all,
        "classified_file": strings_classified
    },
    "output_dir": out_dir
}

with open(json_out, 'w') as f:
    json.dump(result, f, indent=2)

print(f"[*] JSON output written to: {json_out}")
PYEOF

echo ""
echo "══════════════════════════════════════════════"
echo "  Reconnaissance Complete: $APP_NAME"
echo "══════════════════════════════════════════════"
echo "  Bundle ID:     $BUNDLE_ID"
echo "  Version:       $BUNDLE_VERSION (Build $BUNDLE_BUILD)"
echo "  Architecture:  $ARCH_LIST"
echo "  Signature:     $SIGN_STATUS_RAW"
echo "  Sandbox:       $( [[ $HAS_SANDBOX != "0" ]] && echo "YES" || echo "NO" )"
echo "  Hardened:      $( [[ $HAS_HARDENED_RUNTIME != "0" ]] && echo "YES" || echo "NO" )"
echo "  Allow dylib:   $( [[ $HAS_DISABLE_LIBRARY_VALIDATION != "0" ]] && echo "YES ⚠️" || echo "NO" )"
echo "  Total strings: $TOTAL_STRINGS"
echo "──────────────────────────────────────────────"
echo "  JSON:          $JSON_OUT"
echo "  Strings:       $STRINGS_ALL"
echo "  Classified:    $STRINGS_CLASSIFIED"
echo "══════════════════════════════════════════════"
