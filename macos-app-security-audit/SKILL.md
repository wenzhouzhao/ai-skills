---
name: macos-app-security-audit
description: >
  通用 macOS 应用安全审计方法论。触发词 — macOS 安全审计、Mac 应用破解、付费绕过、
  二进制 patch、IAP 破解、license 绕过、Mac app 漏洞挖掘、macOS app security audit、
  mac app crack、app pentest、macOS 逆向、mac app reverse engineering。
  覆盖 Plist/UserDefaults 篡改、ARM64 二进制指令 patch、代码注入、网络重放、Keychain 操纵、
  时间篡改、重签名等完整攻击面。方法论/playbook 型 skill，不绑定任何具体应用。
metadata:
  version: "1.0.0"
  author: security-team
  use_case: 通用 macOS 应用安全审计 playbook
---

# macOS App Security Audit — 通用 macOS 应用安全审计方法论

对任意 macOS 应用进行系统化安全审计的完整 playbook。覆盖信息收集、攻击面映射、攻击向量执行、持久化与副作用管理、标准化报告输出全流程。

## 适用场景

- macOS 应用的付费/IAP/订阅功能安全审计
- License 验证机制评估与绕过测试
- 权限提升与沙盒逃逸评估
- 敏感数据泄露分析（Keychain / UserDefaults / Plist / 自定义数据库）
- 反篡改/反调试机制有效性测试

## 前置条件

| 项目 | 说明 |
|------|------|
| 系统 | macOS 14+（部分命令需 SIP 配置调整） |
| 工具 | 全部使用系统自带工具：`codesign`、`otool`、`strings`、`plutil`、`xxd`、`file`、`security` |
| 可选工具 | `mitmproxy` / `Proxyman` / `Charles`（网络分析）、`Hopper` / `Ghidra`（静态分析） |
| 权限 | 部分攻击向量需 `sudo`；代码注入需 SIP 部分关闭 |

---

## Phase 1 — 信息收集 (Reconnaissance)

### 目标

收集目标应用的 Bundle ID、版本、架构、签名状态、所有配置文件路径、可读字符串等基础信息。结果用于后续攻击面判断。

### 一键脚本

```bash
bash scripts/macos_recon.sh /path/to/Target.app [output_dir]
```

脚本自动执行以下全部检查并输出结构化 JSON。输出示例见脚本注释。

### 手动步骤（脚本内部逻辑说明）

#### 1.1 签名与架构

```bash
# 完整签名信息（Authority、TeamIdentifier、Entitlements）
codesign -dvvv /path/to/Target.app 2>&1

# Entitlements 列表
codesign -d --entitlements - /path/to/Target.app 2>&1 | plutil -p -

# 架构信息
file /path/to/Target.app/Contents/MacOS/<binary>
otool -f /path/to/Target.app/Contents/MacOS/<binary>

# 获取 Bundle ID & 版本
plutil -p /path/to/Target.app/Contents/Info.plist | grep -E "CFBundleIdentifier|CFBundleShortVersionString|CFBundleVersion"
```

**关键判断点**：
- `Authority=Apple Root CA` → App Store 分发，有收据验证
- `Authority=Developer ID Application` → 独立分发，可能无收据
- `Signature=adhoc` 或缺省 → 无签名或自签名，无 Gatekeeper 保护
- `com.apple.security.app-sandbox=true` → 应用已沙盒化
- `com.apple.security.cs.disable-library-validation` → 允许加载任意 dylib（注入入口）

#### 1.2 Plist 收集

```bash
# 应用 Bundle 内所有 plist
find /path/to/Target.app -name "*.plist" 2>/dev/null

# App Group 容器
find ~/Library/Group\ Containers -maxdepth 2 -name "*.plist" 2>/dev/null | grep -i "<bundle-id-prefix>"

# Preferences
find ~/Library/Preferences -name "*<bundle-id-prefix>*" 2>/dev/null

# Container (沙盒应用)
find ~/Library/Containers/<bundle-id> -name "*.plist" 2>/dev/null
```

#### 1.3 可读字符串提取与分类

```bash
# 提取所有可读字符串（最小 4 字符）
BINARY="/path/to/Target.app/Contents/MacOS/<binary>"
strings "$BINARY" | grep -E '.{4,}' > strings_all.txt

# 付费/IAP 关键词
grep -iE 'purchas|premium|pro|vip|subscri|license|activ|unlock|receipt|validate|verify|trial' strings_all.txt

# URL/域名
grep -oE 'https?://[a-zA-Z0-9._/-]+' strings_all.txt | sort -u

# 文件路径/UserDefaults Key
grep -oE '[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+' strings_all.txt | sort -u

# 加密/哈希函数
grep -iE 'AES|RSA|SHA|HMAC|base64|encrypt|decrypt|hash|cipher' strings_all.txt

# 反调试/篡改检测
grep -iE 'ptrace|sysctl|debug|tamper|integrity|signature|jailbreak' strings_all.txt
```

---

## Phase 2 — 攻击面映射 (Attack Surface Mapping)

### 2.1 付费/IAP 状态存储分析

按优先级排查以下存储位置：

| 优先级 | 存储位置 | 特征 | 攻击难度 |
|--------|---------|------|---------|
| P0 | `UserDefaults`（`~/Library/Preferences/<bundle-id>.plist`） | 明文布尔/字符串标记 | 极低 |
| P0 | 自定义 Plist（App Group / Container 内） | 明文开关、过期时间戳 | 极低 |
| P1 | SQLite/自定义数据库 | 需解析表结构 | 中 |
| P1 | Keychain | 加密存储，需 root 或注入读取 | 中-高 |
| P2 | 服务端令牌 | 完全服务端验证 | 高 |

**判断方法**：
1. 先 grep strings 输出中的 `purchas` / `license` / `pro` / `trial` / `expire` 等关键词
2. 对可疑 UserDefaults key，用 `plutil -p` 查看当前值
3. 用 `fs_usage` 或 `lsof` 监控应用运行时的文件 I/O 定位状态文件

### 2.2 控制链路判断

```
┌──────────┐    读取状态     ┌──────────────┐    验证收据/Token    ┌──────────┐
│  应用启动  │ ──────────────→ │  本地状态存储  │ ──────────────────→ │  服务端    │
└──────────┘                 └──────────────┘                     └──────────┘
                                    │                                    │
                                    ▼                                    ▼
                              ┌──────────┐                        ┌──────────┐
                              │ 纯本地判断 │                        │ 服务端兜底 │
                              │ → 高风险  │                        │ → 低风险   │
                              └──────────┘                        └──────────┘
```

关键判定：如果攻击者修改本地状态后功能即生效、无任何网络验证回调，则为**纯本地判断**——高风险漏洞。

### 2.3 网络流量分析（如适用）

若应用涉及网络验证：

```bash
# 使用 mitmproxy 捕获流量（需先安装）
mitmproxy -p 8080
# 配置系统代理：系统设置 → 网络 → 代理 → HTTP/HTTPS → 127.0.0.1:8080

# 分析要点：
# - 收据验证 API 端点
# - 请求体中的设备指纹/签名参数
# - 响应体中的付费状态字段
# - 是否存在重放攻击窗口（无 nonce / 时间戳校验）
```

### 2.4 反调试/反篡改检测

```bash
# 检查是否使用 ptrace 反调试
strings <binary> | grep -i ptrace

# 检查 sysctl 反调试
strings <binary> | grep -i "sysctl.*P_TRACED"

# 检查代码签名自校验
strings <binary> | grep -i "SecCodeCheckValidity\|SecStaticCodeCheckValidity"

# 检查越狱/rootless 检测
strings <binary> | grep -i "jailbreak\|rootless\|amfid"
```

### 2.5 沙盒边界分析

```bash
# 从 Entitlements 判断沙盒状态
codesign -d --entitlements - /path/to/Target.app 2>&1

# 关键 Entitlements：
# com.apple.security.app-sandbox = true → 已启用沙盒
# com.apple.security.files.user-selected.read-write → 可访问用户选择的文件
# com.apple.security.network.client → 可发起网络连接
# com.apple.security.cs.disable-library-validation → 允许加载任意 dylib ⚠️
```

---

## Phase 3 — 攻击向量 (Attack Vectors)

### 向量优先级排序

| 优先级 | 攻击向量 | 适用条件 | 成功率 | 复杂度 |
|--------|---------|---------|--------|--------|
| P0 | Plist/UserDefaults 篡改 | 本地明文状态存储 | 高 | 极低 |
| P0 | 时间篡改 | 试用期基于本地时间 | 高 | 极低 |
| P1 | 二进制指令 patch | 本地条件判断 | 高 | 中 |
| P2 | 网络请求重放/篡改 | 服务端验证但无防重放 | 中 | 中 |
| P2 | 代码注入 (dylib hook) | disable-library-validation | 中 | 高 |
| P3 | Keychain 操纵 | 付费状态存 Keychain | 低-中 | 高 |

---

### 3.1 Plist / UserDefaults 篡改

**原理**：应用的付费标记以明文布尔值存储在 plist 中，修改后即时生效。

**命令示例**：
```bash
# 方式一：直接编辑 UserDefaults plist
plutil -p ~/Library/Preferences/<bundle-id>.plist    # 先查看当前值
plutil -replace <key> -bool true ~/Library/Preferences/<bundle-id>.plist

# 方式二：通过 defaults 命令
defaults read <bundle-id>
defaults write <bundle-id> <key> -bool true

# 方式三：App Group plist
plutil -p ~/Library/Group\ Containers/<group-id>/Library/Preferences/<plist-name>.plist
plutil -replace <key> -bool true ~/Library/Group\ Containers/<group-id>/Library/Preferences/<plist-name>.plist
```

**成功判定**：
- 修改后重启应用，付费功能可用
- 用户界面显示"已购买"或等效标记
- 水印/限制消失

**失败原因排查**：
- 值在启动时被无条件重置（输出标记而非输入开关）
- 值有 HMAC 签名校验（修改后校验失败）
- 值仅为本地缓存，真实状态来自服务端

---

### 3.2 二进制指令 Patch (ARM64)

**原理**：直接修改 Mach-O 二进制中的条件跳转指令，使付费检查永远通过。

**前置步骤**：
```bash
# 1. 备份原始二进制
cp /path/to/Target.app/Contents/MacOS/<binary> /path/to/Target.app/Contents/MacOS/<binary>.bak

# 2. 获取 fat binary 信息
file /path/to/Target.app/Contents/MacOS/<binary>
otool -f /path/to/Target.app/Contents/MacOS/<binary>

# 3. 找到架构对应的 fat offset（如 arm64 slice 的起始偏移）
# 对于 arm64 单架构二进制，fat offset = 0
```

**常用 Patch 模式**：

| 原指令 | Patch 后 | 机器码变换 | 含义 |
|--------|---------|-----------|------|
| `CBZ X0, loc_xxx` | `B loc_xxx` | 条件分支 → 无条件跳转 | "如果付费则跳过水印" → "永远跳过水印" |
| `CBNZ X0, loc_xxx` | `NOP` | 条件分支 → 空操作 | "如果未付费则显示限制" → "永远不显示限制" |
| `MOVZ X0, #0` | `MOVZ X0, #1` | 返回值 false → true | 函数返回 false → 返回 true |
| `TBNZ X0, #0, loc` | `NOP` + `NOP` | 位测试 → 空操作 | 跳过标志位检查 |

**定位目标指令的工作流**：
```bash
# Step 1：用 strings 找线索
strings <binary> | grep -iE 'purchas|premium|watermark|trial|limit|expir'

# Step 2：用 otool 反汇编，搜索附近代码
otool -tV <binary> | grep -A 5 -B 5 "感兴趣的函数名"

# Step 3：确认指令的 VM 地址 → fat offset
# fat_offset = VM_address - 0x100000000  (macOS 默认基址)
# 对于有 fat header 的二进制，先用 otool -f 获取架构 offset，再加 VM offset

# Step 4：用 xxd 定位并 patch
xxd -s <offset> -l 4 -p <binary>                        # 读取原始 4 字节
echo "<new_hex>" | xxd -r -p | dd of=<binary> bs=1 seek=<offset> conv=notrunc   # 写入
```

**CBZ → B Patch 细节**：
CBZ 指令 4 字节编码：
- `CBZ Xn, offset` → `10110100 xxxxxxxx xxxxxxxx xxxxxx0x`
- 如 `0x34000648`（CBZ X0, +0xC8）→ `0x14000032`（B +0xC8）

ARM64 B 指令编码：
- `B offset` → `000101xx xxxxxxxx xxxxxxxx xxxxxxxx`
- 偏移量 = (目标地址 - 当前地址) / 4

**成功判定**：
- patch 后应用行为改变（付费限制消失）
- 无崩溃（说明未触发自校验）
- codesign 验证失败（`codesign -vvv <binary>` 返回非 0）—— 这是预期结果，patch 必然破坏签名

---

### 3.3 代码注入 (DYLD_INSERT_LIBRARIES / dylib Hook)

**原理**：在应用启动时注入自定义动态库，hook 关键函数改变其返回值。

**前置条件**（需满足其一）：
- 应用 Entitlements 含 `com.apple.security.cs.disable-library-validation`
- SIP 已关闭（`csrutil disable`，**仅限测试环境**）
- 应用无签名（`codesign --remove-signature` 后可注入）

**注入流程**：
```bash
# 1. 编译 hook dylib
cat > hook.m << 'EOF'
#import <Foundation/Foundation.h>
#import <objc/runtime.h>

__attribute__((constructor))
static void init(void) {
    // Method swizzling 示例：hook NSUserDefaults boolForKey:
    Method orig = class_getInstanceMethod([NSUserDefaults class],
                                          @selector(boolForKey:));
    Method swiz = class_getInstanceMethod([NSUserDefaults class],
                                          @selector(hook_boolForKey:));
    method_exchangeImplementations(orig, swiz);
}

@interface NSUserDefaults (Hook)
- (BOOL)hook_boolForKey:(NSString *)key;
@end

@implementation NSUserDefaults (Hook)
- (BOOL)hook_boolForKey:(NSString *)key {
    if ([key containsString:@"purchas"] || [key containsString:@"pro"]) {
        NSLog(@"[HOOK] Intercepted key: %@, returning YES", key);
        return YES;
    }
    return [self hook_boolForKey:key]; // 调用原始实现（已交换）
}
@end
EOF

clang -dynamiclib -framework Foundation -framework AppKit hook.m -o hook.dylib

# 2. 注入启动
DYLD_INSERT_LIBRARIES=hook.dylib /path/to/Target.app/Contents/MacOS/<binary>
```

**常用 Hook 目标**：
- `-[NSUserDefaults boolForKey:]` / `integerForKey:`— 篡改本地状态读取
- `-[NSFileManager fileExistsAtPath:]` — 隐藏检查文件
- `SecItemCopyMatching` — Keychain 操作劫持
- `-[NSData initWithBase64EncodedString:]` — 拦截签名/令牌
- `SSSSVerifyAppleEntitlement` / StoreKit 收据验证函数
- 应用自身的验证函数（通过 strings 定位）

**成功判定**：
- 注入后应用功能行为改变且不崩溃
- NSLog 输出确认 hook 被触发
- 若应用崩溃，可能触发了反注入检测（检查 `DYLD_INSERT_LIBRARIES` 环境变量）

---

### 3.4 网络请求重放/篡改

**原理**：拦截应用与验证服务器的通信，修改请求或响应数据。

**mitmproxy 脚本示例**：
```python
# bypass_verify.py
from mitmproxy import http

def response(flow: http.HTTPFlow) -> None:
    """拦截验证响应，将付费状态强制改为 true"""
    if "verify" in flow.request.pretty_url or "validate" in flow.request.pretty_url:
        # 修改 JSON 响应
        import json
        try:
            data = json.loads(flow.response.text)
            data["status"] = "active"
            data["is_premium"] = True
            data["expiry_date"] = "2099-12-31T23:59:59Z"
            flow.response.text = json.dumps(data)
            print(f"[BYPASS] Modified response for {flow.request.pretty_url}")
        except:
            pass

def request(flow: http.HTTPFlow) -> None:
    """拦截收据验证请求，替换为假收据"""
    if "verifyReceipt" in flow.request.pretty_url:
        import json
        try:
            data = json.loads(flow.request.text)
            print(f"[REPLAY] Captured receipt: {data.get('receipt-data', 'N/A')[:50]}...")
        except:
            pass
```

**运行**：
```bash
mitmproxy -s bypass_verify.py -p 8080
```

**成功判定**：
- 应用获取到篡改后的响应
- 付费状态变为已激活
- 若应用使用证书固定 (SSL Pinning) 则此方法失效 → 需结合二进制 patch 移除证书校验

---

### 3.5 Keychain 操纵

**原理**：通过 `security` 命令行工具读取/修改 Keychain 中的付费状态项。

```bash
# 列出应用相关 Keychain 项
security find-generic-password -s "<bundle-id>" 2>/dev/null
security find-generic-password -g -s "<bundle-id>" 2>&1

# 删除并重建（需要应用使用的 service/account 名称）
security delete-generic-password -s "<service>" -a "<account>" 2>/dev/null
security add-generic-password -s "<service>" -a "<account>" -w "true"
```

**限制**：
- 需要知道确切的 service 和 account 名称
- 某些 Keychain 项需要特定访问组（Access Group），无法直接修改
- Keychain 项可能有 ACL 限制（提示用户授权）
- 成功率取决于应用的 Keychain 访问策略

**成功判定**：
- 修改/删除后应用行为改变，付费恢复
- `security` 命令返回成功 (exit code 0)

---

### 3.6 时间篡改

**原理**：试用期/订阅过期通常基于本地系统时间判断。

```bash
# 方法一：修改系统时间（需关闭自动时间同步）
sudo systemsetup -setdate "01/01/2025"
sudo systemsetup -settime "12:00:00"

# 恢复
sudo systemsetup -setusingnetworktime on

# 方法二：使用 faketime（需安装 libfaketime）
# brew install libfaketime  # 仅在测试环境
DYLD_INSERT_LIBRARIES=/path/to/libfaketime.dylib DYLD_FORCE_FLAT_NAMESPACE=1 \
    FAKETIME="2025-01-01 12:00:00" /path/to/Target.app/Contents/MacOS/<binary>
```

**成功判定**：
- 试用期功能在"过期"时间后仍可用
- 注意：修改系统时间影响全局，测试后立即恢复

**防护特征检查**：
- `strings | grep -i "network.*time\|ntp\|time.*server"` — 服务端时间同步
- `strings | grep -i "first.*launch\|install.*date"` — 首次使用时间检测

---

### 3.7 重签名 + 权限维持

**原理**：patch 后签名失效，需 ad-hoc 重签名并重置权限。

```bash
# 1. 移除旧签名
sudo codesign --remove-signature /path/to/Target.app

# 2. ad-hoc 重签名
sudo codesign --force --deep --sign - /path/to/Target.app

# 3. 可选：用开发者证书签名（需要 Apple Developer 账号）
sudo codesign --force --deep --sign "Developer ID Application: <Name> (<TeamID>)" /path/to/Target.app

# 4. 验证签名
codesign -dvvv /path/to/Target.app

# 5. 重置 TCC 权限（签名变更后需要）
tccutil reset All <bundle-id>
# 或单独重置某类权限
tccutil reset ScreenCapture <bundle-id>
tccutil reset Microphone <bundle-id>
tccutil reset Camera <bundle-id>
```

**注意事项**：
- ad-hoc 签名无法通过 Gatekeeper（需右键打开或 `spctl --master-disable`）
- App Store 应用重签名后无法接收更新
- 部分应用检查签名 TeamIdentifier，ad-hoc 签名会导致检查失败

---

## Phase 4 — Patch 持久化与副作用

### 4.1 签名失效后的重签名方案

| 方案 | Gatekeeper 兼容 | 需要 | 适用场景 |
|------|----------------|------|---------|
| ad-hoc | 否（需右键打开） | 无 | 个人测试 |
| Developer ID | 是 | Apple Developer 账号 ($99/年) | 长期使用 |
| 禁用 Gatekeeper | — | `sudo spctl --master-disable` | 测试环境 |

### 4.2 TCC 权限重置

签名变更后系统视为新应用，所有 TCC 权限（摄像头、麦克风、屏幕录制、辅助功能等）清零。

```bash
tccutil reset All <bundle-id>
```

用户需在系统设置 → 隐私与安全性中重新授权。

### 4.3 App 更新对 Patch 的影响

| 更新方式 | Patch 是否保留 | 说明 |
|---------|-------------|------|
| App Store 自动更新 | **丢失** | 二进制被完整替换 |
| DMG 覆盖安装 | **丢失** | 同上 |
| 增量更新 | **可能部分保留** | 取决于更新是否触及 patch 区域 |
| 小版本热修复 | **不确定** | 需重新验证 |

**建议**：patch 后禁用自动更新，或保存 patch 脚本以便快速重放。

### 4.4 Gatekeeper / SIP 绕过注意事项

| 机制 | 默认状态 | 绕过方式 | 风险 |
|------|---------|---------|------|
| Gatekeeper | 启用 | `spctl --master-disable` 或右键打开 | 降低系统安全 |
| SIP | 启用 | `csrutil disable`（恢复模式） | 极高风险，仅限测试环境 |
| Hardened Runtime | 取决于应用 | `--disable-library-validation` entitlement | 需要应用本身开启 |

**安全警告**：禁用 SIP 或 Gatekeeper 会严重降低 macOS 安全性，仅限隔离测试环境使用。测试完成后务必恢复。

---

## Phase 5 — 报告模板

使用 `references/report-template.md` 中的标准化报告模板。核心要素：

### 报告结构

```
1. 漏洞概述（Vulnerability Overview）
   - 标题格式：[App Name] 付费绕过漏洞
   - 漏洞类型（CWE 映射）
   - CVSS 评分
   - 影响版本

2. 技术分析（Technical Analysis）
   - 攻击面定位
   - 控制链路图
   - 根因分析

3. 复现步骤（Reproduction Steps）
   - 环境要求
   - 逐步操作说明
   - 预期结果 vs 实际结果

4. 攻击复杂度（Attack Complexity）
   - 所需工具/权限
   - 时间成本
   - 是否可自动化

5. 修复建议（Remediation）
   - 按 P0/P1/P2 优先级分级
   - 短期缓解措施
   - 长期架构建议
```

---

## 技能脚本

### macos_recon.sh

一键信息收集脚本，收集目标应用的所有基础信息并输出结构化 JSON。

```bash
bash scripts/macos_recon.sh /path/to/Target.app [output_dir]
```

输出 JSON 包含：`bundle_id`、`version`、`architecture`、`signature_status`、`entitlements`、`plist_paths`、`classified_strings`。

---

## 参考文档

| 文档 | 内容 |
|------|------|
| `references/attack-surface-taxonomy.md` | macOS 应用常见攻击面分类详表 |
| `references/binary-patching-primer.md` | ARM64 常见 patch 模式速查（CBZ→B、MOVZ、NOP 等） |
| `references/report-template.md` | 标准化漏洞报告模板 |

## 依赖

- macOS 系统自带工具：`codesign`、`otool`、`strings`、`plutil`、`xxd`、`file`、`security`、`tccutil`
- 可选：`mitmproxy`、`Proxyman`、`Charles`（网络分析）
- 可选：`Hopper`、`Ghidra`（高级静态分析）
