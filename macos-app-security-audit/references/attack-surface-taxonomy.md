# macOS Application Attack Surface Taxonomy

Comprehensive classification of attack surfaces commonly found in macOS applications.
Use this as a checklist during Phase 2 (Attack Surface Mapping) of security audits.

---

## 1. Paid Feature / IAP / License Enforcement

### 1.1 Local State Storage

| Attack Surface | Storage Location | Typical Vulnerability | Risk Level |
|---------------|------------------|-----------------------|------------|
| `UserDefaults` boolean flag | `~/Library/Preferences/<bundle-id>.plist` | Plaintext `isPurchased = false` → set to `true` | 🔴 Critical |
| `UserDefaults` timestamp | `~/Library/Preferences/<bundle-id>.plist` | `trial_start_date` or `expiry_date` modifiable | 🔴 Critical |
| Custom Plist in App Group | `~/Library/Group Containers/<group>/` | Shared plist with purchase flags | 🔴 Critical |
| Custom Plist in Container | `~/Library/Containers/<bundle-id>/` | Local license file (.plist / .dat / .lic) | 🟡 High |
| SQLite database | `~/Library/Application Support/<app>/` | `SELECT is_premium FROM user_settings` modifiable | 🟡 High |
| Keychain item | Keychain (Access Group scoped) | Requires app context or injection to modify | 🟠 Medium |
| `NSUbiquitousKeyValueStore` | iCloud KVS | Synced across devices; modifiable on any linked device | 🟡 High |

### 1.2 Receipt Validation

| Attack Surface | Description | Bypass Method |
|---------------|-------------|---------------|
| Local receipt (`appStoreReceiptURL`) | App Store receipt in app bundle | Replace with valid receipt from another app |
| `SKReceiptRefreshRequest` | On-demand receipt refresh | Block network or return cached response |
| Custom server-side validation | Receipt hash sent to own server | Replay attack or modify server response |
| `SSSSVerifyAppleEntitlement` | IOKit private entitlement verification | Hook via dylib injection |

### 1.3 License Key Validation

| Attack Surface | Description | Bypass Method |
|---------------|-------------|---------------|
| Local algorithmic check | Key format validated locally with checksum/algo | Reverse algorithm → keygen |
| Online activation | Key + hardware fingerprint sent to server | Replay response; modify hardware fingerprint |
| Offline activation file | `.lic` file written after successful activation | Copy `.lic` from activated machine |
| Time-limited license | Expiry date embedded in license | Time manipulation; patch expiry check |

---

## 2. Binary-Level Protections

### 2.1 Anti-Debugging

| Technique | Detection Method | Bypass |
|-----------|-----------------|--------|
| `ptrace(PT_DENY_ATTACH, ...)` | Prevents debugger attachment | Patch `ptrace` call or NOP it |
| `sysctl` with `P_TRACED` | Checks `kinfo_proc.kp_proc.p_flag` | Return fake `kinfo_proc` |
| `isatty(STDIN_FILENO)` | Detects if stdin is a terminal | Patch `isatty` to return 0 |
| `getppid()` check | Detects if parent is a debugger | Patch `getppid` |

### 2.2 Anti-Tampering

| Technique | Detection Method | Bypass |
|-----------|-----------------|--------|
| Code signature self-check | `SecCodeCheckValidity` / `SecStaticCodeCheckValidity` | Patch validation call or remove signature |
| Binary hash / checksum | CRC/MD5 of `__TEXT` segment | Patch checksum routine |
| `LC_VERSION_MIN_MACOSX` / build ID check | File integrity hash | Patch or spoof the check |
| Bundle checksum (App Store) | `_MSSendAppleEvent` integrity check | Only on App Store builds |

### 2.3 Runtime Integrity

| Technique | Description | Bypass |
|-----------|-------------|--------|
| `__RESTRICT` section | Prevents `DYLD_INSERT_LIBRARIES` | Remove `__RESTRICT` from Mach-O |
| Hardened Runtime | Flags in code signature | Remove flags or ad-hoc re-sign |
| Library Validation | Only allows Apple-signed or team-signed dylibs | Disable via `com.apple.security.cs.disable-library-validation` |
| SIP (System Integrity Protection) | Prevents modification of system binaries | `csrutil disable` (Recovery mode) |

---

## 3. Data Storage & Privacy

### 3.1 Sensitive Data at Rest

| Storage | Typical Content | Risk |
|---------|----------------|------|
| `UserDefaults` (plist) | Auth tokens, user preferences, purchase state | ⚠️ Readable by any process as same user |
| Keychain | Passwords, certificates, crypto keys | More secure; ACL-scoped but accessible within same signing identity |
| SQLite / Core Data | User data, cached API responses | Plaintext unless encrypted |
| `NSCachesDirectory` | Cached images, network responses | May contain sensitive data |
| `NSApplicationSupportDirectory` | App-specific data files | Variable; depends on app implementation |
| iCloud / CloudKit | Synced data across devices | Accessible via iCloud credentials |

### 3.2 Inter-Process Communication (IPC)

| Mechanism | Attack Surface |
|-----------|---------------|
| XPC Services | Privilege escalation if service lacks proper validation |
| `NSDistributedNotificationCenter` | Sensitive data broadcast globally; spoofable |
| `CFMessagePort` | Mach port communication; may be intercepted |
| Apple Events / `NSAppleScript` | Scripting bridge abuse |
| URL Schemes (`CFBundleURLTypes`) | Data injection via custom URL scheme |
| Pasteboard (`NSPasteboard`) | Clipboard data leakage |

### 3.3 File Permissions

| Check | Command |
|-------|---------|
| App bundle permissions | `ls -la /path/to/Target.app/Contents/MacOS/<binary>` |
| Data directory permissions | `ls -la ~/Library/Application Support/<app>/` |
| World-readable config files | `find ~/Library -perm +004 -name "*<app>*"` |

---

## 4. Network Communication

### 4.1 Transport Security

| Configuration | Location | Risk |
|---------------|----------|------|
| `NSAppTransportSecurity` | `Info.plist` | Check for `NSAllowsArbitraryLoads = true` |
| `NSExceptionDomains` | `Info.plist` | Domain-specific ATS exceptions |
| Certificate pinning | Binary / bundled cert | Prevents MITM; requires binary patch to bypass |

### 4.2 API Endpoints

| Endpoint Type | Key Questions |
|---------------|---------------|
| Receipt verification | `POST /verifyReceipt` — does it pass raw receipt or hash? |
| License activation | Is hardware fingerprint sent? Is response replayable? |
| Status check | `GET /status?user_id=X` — predictable user IDs? |
| Analytics / Telemetry | What data is sent? Can it be spoofed? |

### 4.3 MITM Attack Feasibility

| Condition | Feasible? |
|-----------|-----------|
| No ATS, no cert pinning | ✅ Trivial (mitmproxy with proxy CA) |
| ATS enabled, no cert pinning | ✅ Possible (install mitmproxy CA as trusted) |
| ATS + cert pinning | ❌ Requires binary patch to disable pinning |
| Custom TLS with hardcoded cert | ❌ Requires binary patch |

---

## 5. Entitlements & Sandbox

### 5.1 Key Entitlements to Audit

| Entitlement | Risk Implication |
|-------------|-----------------|
| `com.apple.security.app-sandbox` | `false` → no sandbox; full FS access |
| `com.apple.security.cs.disable-library-validation` | Allows loading arbitrary dylibs → injection vector |
| `com.apple.security.cs.allow-unsigned-executable-memory` | Allows JIT; could be abused for code execution |
| `com.apple.security.cs.disable-executable-page-protection` | Disables W^X; extreme risk |
| `com.apple.security.files.user-selected.read-write` | User-approved file access |
| `com.apple.security.network.client` | Outbound network access |
| `com.apple.security.network.server` | Inbound network (listening socket) |
| `com.apple.security.device.camera` / `.microphone` | Hardware access |
| `keychain-access-groups` | Shared keychain access across apps from same team |

### 5.2 Sandbox Escape Vectors

| Vector | Description |
|--------|-------------|
| XPC service with elevated privileges | Misconfigured XPC service may allow sandbox escape |
| `NSOpenPanel` / `NSSavePanel` | User-granted file access can be exploited |
| Shared App Group container | Cross-app data leaks within same team |
| URL scheme handler | Data injection from external sources |

---

## 6. Update Mechanism

| Mechanism | Risk |
|-----------|------|
| Sparkle (unsigned feed) | MITM on update feed → malicious update |
| Sparkle (signed feed) | Secure if EdDSA signature verified |
| In-app updater calling home | Check if update URL is hardcoded and mutable |
| App Store (receipt-based) | Update replaces binary → patch lost |

---

## 7. Quick Audit Checklist

- [ ] Bundle ID & version documented
- [ ] Architecture (arm64 / x86_64 / Universal) confirmed
- [ ] Code signature status verified
- [ ] Entitlements reviewed (especially sandbox and dylib loading)
- [ ] All plist paths enumerated
- [ ] Strings classified (payment, URLs, crypto, anti-debug keywords)
- [ ] Paid state storage location identified
- [ ] Control flow determined (local-only vs server-backed)
- [ ] Anti-debug / anti-tamper mechanisms catalogued
- [ ] Network endpoints identified (if any)
- [ ] ATS configuration reviewed
- [ ] IPC surfaces documented
