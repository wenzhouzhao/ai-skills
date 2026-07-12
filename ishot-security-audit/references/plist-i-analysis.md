# iShot 水印安全审计技术报告 v2

> **审计日期**: 2026-07-12
> **审计目标**: iShot v2.6.7 (Build 20260128001)
> **Bundle ID**: cn.better365.ishot
> **开发者**: Better365 (Team ID: 4K6FWZU8C4)
> **安装路径**: /Applications/iShot.app

---

## 1. 执行摘要

iShot 的长截图付费水印保护机制存在**严重的本地安全漏洞**。付费状态 (`iShotHavePurchased`) 以明文布尔值形式存储在 App Group 容器 Plist 中，**无任何校验签名、哈希或完整性验证机制**。任何具有文件写入权限的用户或进程均可直接篡改该值，从而绕过付费水印。

| 风险等级 | 漏洞类型 | 影响 |
|---------|---------|------|
| **高危** | 本地付费状态无完整性校验 | 可绕过长截图水印 |
| **中危** | 付费状态缓存于用户可写区域 | 持久化篡改 |
| **低危** | 试用量仅依赖安装时间戳 | 可重置试用期 |

---

## 2. 应用架构分析

### 2.1 应用基本信息

| 属性 | 值 |
|------|-----|
| 版本 | 2.6.7 |
| Build | 20260128001 |
| 最低系统 | macOS 10.13 |
| 架构 | Universal (x86_64 + arm64) |
| 签名 | Apple Developer ID (Hardened Runtime) |
| 沙盒 | 是 (com.apple.security.app-sandbox) |
| App Group | 4K6FWZU8C4.group.cn.better365 |

### 2.2 关键 Bundle 结构

```
/Applications/iShot.app/
├── Contents/
│   ├── MacOS/iShot                    ← 主二进制 (3.9MB, Universal)
│   ├── Info.plist
│   ├── Resources/
│   │   ├── Assets.car                 ← 含水印图片资源 needBuyWatermark.png
│   │   ├── DefaultPreferences.plist   ← 默认配置
│   │   ├── ARM/                       ← ARM64 原生库 (ffmpeg, libav*)
│   │   ├── Intel/                     ← x86_64 原生库
│   │   └── zh-Hans.lproj/            ← 中文本地化
│   ├── Frameworks/
│   │   ├── PTHotKey.framework
│   │   └── ShortcutRecorder.framework
│   ├── Library/LoginItems/
│   │   └── iShotHelper.app            ← 辅助进程
│   └── _MASReceipt/receipt            ← App Store 收据
```

### 2.3 权限与 Entitlements

```
com.apple.security.app-sandbox        = true
com.apple.security.application-groups = [4K6FWZU8C4.group.cn.better365]
com.apple.security.device.audio-input = true
com.apple.security.device.camera      = true
com.apple.security.files.user-selected.read-write = true
com.apple.security.network.client     = true
```

---

## 3. 付费与水印机制逆向分析

### 3.1 付费管理类

通过二进制符号分析，识别出以下核心类：

| 类名 | 职责 |
|------|------|
| **ApplePurchaseManager** | IAP 管理单例，处理购买/验证/恢复 |
| **BuyFromAppStoreController** | App Store 购买流程 UI 控制器 |
| **BuyNotFromAppStoreController** | 非 App Store 版本购买流程 UI 控制器 |

#### ApplePurchaseManager 关键方法

```
- startPurchaseWithProductID:CompleteBlock:      // 发起购买
- restorePurchaseWithCompleteBlock:              // 恢复购买
- verifyPurchaseWithPaymentTransaction:isTestServer:Compl:  // 验证收据
- restoreTransaction                             // 恢复交易
- productsRequest:didReceiveResponse:            // 获取产品信息
+ sharedInstance                                 // 单例
```

#### 产品 ID

```
ishotfeixuqidingyue20220212    ← 非续期订阅
ishotmonth20220301             ← 月度订阅
ishotyear20220301              ← 年度订阅
```

### 3.2 付费验证流程

```
用户操作
    │
    ▼
┌─────────────────────────────┐
│  ApplePurchaseManager       │
│  verifyPurchaseWith...      │
│  ↓                          │
│  向 Apple 服务器验证收据      │
│  ├─ https://buy.itunes...   │
│  └─ https://sandbox.itunes..│
└──────────┬──────────────────┘
           │
           ▼ (验证成功)
┌─────────────────────────────┐
│  写入本地付费状态缓存         │
│  iShotHavePurchased = 1     │
│  ↓                          │
│  存储位置:                   │
│  App Group Container Plist  │
└──────────┬──────────────────┘
           │
           ▼ (每次截图时)
┌─────────────────────────────┐
│  读取 iShotHavePurchased    │
│  ├─ = 1 → 无水印            │
│  └─ = 0 → 添加 needBuyWatermark │
└─────────────────────────────┘
```

### 3.3 本地存储位置 (漏洞核心)

付费状态缓存于以下路径：

```
~/Library/Group Containers/4K6FWZU8C4.group.cn.better365/
└── Library/
    └── Preferences/
        └── 4K6FWZU8C4.group.cn.better365.plist
```

**Plist 当前内容** (未付费状态):

```json
{
  "AppStoreiShotInstallTime": 1739504913,
  "CPUThreads": "11",
  "iShotAppleLanguages": ["zh-Hans-CN"],
  "iShotHavePurchased": 0
}
```

### 3.4 关键字符串证据

| 字符串 | 含义 | 位置 |
|--------|------|------|
| `iShotHavePurchased` | 付费状态键 | App Group Plist + 二进制 |
| `needBuyWatermark` | 水印标记/图片资源名 | Assets.car (needBuyWatermark.png) |
| `needBuyWatermark` | 水印逻辑控制字符串 | 主二进制 |
| `AppStoreiShotInstallTime` | 安装时间戳 (用于试用计算) | App Group Plist |
| `freeUseOfPromotionPlan:` | 免费推广计划方法 | 主二进制 |
| `You have %d day(s) and %d hour(s) left on your trial period` | 试用期提示 | 主二进制 |

### 3.5 水印触发逻辑

二进制分析确认水印控制逻辑：

1. 应用在长截图 (`scrollScreenshot`) 流程中检查 `needBuyWatermark` 标志
2. 该标志读取自 `iShotHavePurchased` 的值
3. 未付费时 (`iShotHavePurchased = 0`)，从 Assets.car 加载 `needBuyWatermark.png` 并叠加到截图上
4. 付费时 (`iShotHavePurchased = 1`)，跳过水印叠加

---

## 4. 安全漏洞详细分析

### 4.1 漏洞 #1：本地付费状态无完整性校验 (高危)

**描述**：付费状态 `iShotHavePurchased` 存储为明文布尔值，位于用户可写的 Plist 文件中，无任何校验签名、哈希或加密保护。

**证据**：
- App Group Plist 文件权限：`-rw-------@ 1 user staff` (用户可写)
- 应用使用标准 `boolForKey:` / `integerForKey:` 读取，无自定义验证逻辑
- 二进制中未找到任何与状态签名/校验相关的字符串 (`signature`, `checksum`, `tamper`, `integrity` 等均不包含付费状态相关上下文)
- 无 Keychain 存储作为辅助验证

**攻击向量**：
```bash
# 直接修改 Plist 中的付费标志
defaults write ~/Library/Group\ Containers/4K6FWZU8C4.group.cn.better365/Library/Preferences/4K6FWZU8C4.group.cn.better365.plist iShotHavePurchased -bool true
```

**影响**：绕过长截图付费水印，获得完整付费功能体验。

### 4.2 漏洞 #2：Apple 收据验证结果本地缓存

**描述**：`verifyPurchaseWithPaymentTransaction:isTestServer:Compl:` 方法向 Apple 服务器验证收据后，将结果写入本地 Plist 缓存。后续水印检查**直接读取此本地缓存**，而非重新验证收据。

**证据**：
- `verifyPurchaseWithPaymentTransaction` 方法存在于 `ApplePurchaseManager` 类
- `iShotHavePurchased` 键在 App Group Plist 和二进制中同时出现
- 水印相关代码 (`needBuyWatermark`) 独立于收据验证，仅读取本地状态

### 4.3 漏洞 #3：试用期依赖可篡改时间戳

**描述**：试用期计算依赖 `AppStoreiShotInstallTime`（安装时间戳），该值同样存储在用户可写的 Plist 中。

**证据**：
- Plist 包含 `AppStoreiShotInstallTime: 1739504913` (2025-02-14)
- 二进制中的试用期提示字符串："You have %d day(s) and %d hour(s) left on your trial period"
- `AppStoreiShotInstallTime` 与 `iShotHavePurchased` 位于同一 Plist 文件

**攻击向量**：修改 `AppStoreiShotInstallTime` 可无限延长试用期。

### 4.4 漏洞 #4：App Group 共享导致 Helper 进程同步受影响

**描述**：iShot Helper 辅助进程 (`cn.better365.iShotHelper`) 同样读取 App Group Plist 中的 `iShotHavePurchased`。篡改主 Plist 会影响所有相关进程。

**证据**：
- iShotHelper 二进制中同样包含 `iShotHavePurchased` 引用
- App Group 设计即为多进程共享数据

---

## 5. 攻击模拟方案

### 5.1 方案概述

通过修改 App Group Container 中的付费状态标记，模拟付费用户状态，验证水印是否被绕过。

### 5.2 模拟攻击脚本

```bash
#!/bin/bash
# ====================================================
# iShot 付费水印绕过 PoC 脚本 (仅用于安全审计)
# ====================================================

PLIST_PATH="$HOME/Library/Group Containers/4K6FWZU8C4.group.cn.better365/Library/Preferences/4K6FWZU8C4.group.cn.better365.plist"
BACKUP_PATH="${PLIST_PATH}.bak_$(date +%s)"

echo "[*] iShot 付费状态篡改 PoC"
echo "[*] 当前付费状态:"
/usr/libexec/PlistBuddy -c "Print iShotHavePurchased" "$PLIST_PATH" 2>/dev/null || echo "  Key not found"

echo "[*] 备份原始 Plist 到: $BACKUP_PATH"
cp "$PLIST_PATH" "$BACKUP_PATH"

echo "[*] 设置 iShotHavePurchased = true"
/usr/libexec/PlistBuddy -c "Set :iShotHavePurchased true" "$PLIST_PATH" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :iShotHavePurchased bool true" "$PLIST_PATH"

echo "[*] 篡改后状态:"
/usr/libexec/PlistBuddy -c "Print iShotHavePurchased" "$PLIST_PATH"

echo "[*] 尝试重启 iShot..."
killall iShot 2>/dev/null
sleep 2
open -a iShot

echo "[*] 完成。请测试长截图功能验证水印是否消失。"
echo "[*] 恢复命令: cp '$BACKUP_PATH' '$PLIST_PATH'"
```

### 5.3 测试验证步骤

1. 确保 iShot 当前处于未付费状态
2. 执行一次长截图，观察截图底部的水印 (`needBuyWatermark`)
3. 关闭 iShot
4. 运行上述 PoC 脚本修改 `iShotHavePurchased` 为 `true`
5. 重新启动 iShot
6. 再次执行长截图，对比水印是否消失
7. 测试完成后恢复原始 Plist

### 5.4 预期结果

- **篡改前**：长截图底部出现 "iShot" 品牌水印
- **篡改后**：长截图无水印，且所有付费功能正常

---

## 6. 攻击面总结

```
┌──────────────────────────────────────────────────┐
│                  iShot 安全边界                     │
├──────────────────────────────────────────────────┤
│                                                    │
│  Apple Server (收据验证)                            │
│       │                                            │
│       ▼ (仅首次购买/恢复时调用)                       │
│  ┌─────────────┐                                   │
│  │ 本地 Plist   │ ◄── 攻击面: 无签名/无校验           │
│  │             │     用户可写                       │
│  │ iShotHave-  │     无 Keychain 辅助               │
│  │ Purchased=0 │     无完整性哈希                    │
│  └──────┬──────┘                                   │
│         │                                          │
│         ▼ (每次截图读取)                              │
│  ┌─────────────┐                                   │
│  │ 水印逻辑     │                                   │
│  │             │                                   │
│  │ needBuy-    │                                   │
│  │ Watermark   │                                   │
│  └─────────────┘                                   │
│                                                    │
└──────────────────────────────────────────────────┘
```

---

## 7. 修复建议

### 7.1 短期修复 (推荐优先级)

1. **添加状态签名验证**
   - 使用 HMAC-SHA256 对 `iShotHavePurchased` 值进行签名
   - 签名密钥硬编码于二进制中（配合代码混淆）
   - 读取时校验签名，不匹配则回退到未付费状态

2. **双重验证机制**
   - 除 App Group Plist 外，同时在 Keychain 存储付费状态
   - 读取时交叉比对两处状态，不一致时以 Keychain 为准，并触发 Apple 服务端重新验证

3. **定期服务端校验**
   - 每隔 N 天或启动时异步调用 `verifyPurchaseWithPaymentTransaction` 重新验证收据
   - 校验失败时自动回退 `iShotHavePurchased` 为 false

### 7.2 中期改进

4. **完整性哈希链**
   - 计算 `AppStoreiShotInstallTime + DeviceID + ReceiptHash` 的 HMAC
   - 将哈希值存储在 Keychain 中，每次读取 Plist 时校验

5. **代码混淆与反调试**
   - 对 `iShotHavePurchased` 等关键字符串进行编译期混淆
   - 添加反调试检测，防止运行时状态篡改

### 7.3 长期架构改进

6. **移除本地状态缓存**
   - 每次启动时实时验证 App Store 收据 (使用 `appStoreReceiptURL`)
   - 仅在内存中缓存验证结果，不持久化到磁盘

7. **服务端授权**
   - 引入服务端授权令牌机制
   - 客户端每次截图时携带令牌请求服务端验证

---

## 8. 附录

### 8.1 工具调用记录

| 工具 | 用途 | 关键发现 |
|------|------|---------|
| `find` / `ls` | 定位 iShot.app 安装目录 | 确认安装路径和包结构 |
| `read_text` | 读取 Info.plist | Bundle ID: cn.better365.ishot, 版本 2.6.7 |
| `shell_executor (strings)` | 从主二进制提取字符串 | 发现 ApplePurchaseManager, needBuyWatermark, iShotHavePurchased |
| `shell_executor (plutil)` | 解析 DefaultPreferences.plist | 默认配置项列表 |
| `shell_executor (defaults read)` | 读取 UserDefaults | 发现 InstallTimeInfo, NumberOfLaunches |
| `shell_executor (security)` | 检查 Keychain | 无 iShot 相关 Keychain 条目 |
| `codesign` | 验证签名和权限 | Hardened Runtime, App Group 权限 |
| `nm` | 符号分析 | 确认 ApplePurchaseManager 方法列表 |
| `otool -ov` | ObjC 类结构分析 | 确认类继承和方法映射 |

### 8.2 关键文件清单

| 文件路径 | 用途 |
|---------|------|
| `/Applications/iShot.app/Contents/MacOS/iShot` | 主二进制 (Universal) |
| `/Applications/iShot.app/Contents/Info.plist` | 应用配置 |
| `/Applications/iShot.app/Contents/Resources/Assets.car` | 资源包 (含 needBuyWatermark.png) |
| `/Applications/iShot.app/Contents/Resources/DefaultPreferences.plist` | 默认偏好设置 |
| `/Applications/iShot.app/Contents/_MASReceipt/receipt` | App Store 收据 |
| `~/Library/Group Containers/4K6FWZU8C4.group.cn.better365/Library/Preferences/4K6FWZU8C4.group.cn.better365.plist` | **付费状态缓存 (漏洞核心)** |
| `~/Library/Preferences/cn.better365.ishot.plist` | 用户偏好设置 |

### 8.3 水印资源确认

Assets.car 中提取的水印相关资源:
- `needBuyWatermark.png` — 付费提示水印图
- `iShotPro.png` — iShot Pro 图标
- `icon_pro` — Pro 标识图标

### 8.4 相关产品 ID

| 产品 ID | 类型 |
|---------|------|
| `ishotfeixuqidingyue20220212` | 非续期订阅 (买断?) |
| `ishotmonth20220301` | 月度订阅 |
| `ishotyear20220301` | 年度订阅 |
| `cn.better365.iShotPro` | iShot Pro 独立应用 Bundle ID |

---

## 9. 结论

iShot v2.6.7 的付费水印保护机制完全依赖于一个本地明文布尔标志 (`iShotHavePurchased`)，存储在用户可写的 App Group Container Plist 中。该标志没有任何完整性保护（无签名、无哈希、无 Keychain 辅助验证、无定期服务端校验）。这是一个典型的**本地信任漏洞**。

**核心问题**：应用的付费验证采用了"服务端验证一次 → 本地永久缓存"的模式，而缓存本身没有防篡改保护。这导致攻击者只需修改一个 Plist 键值即可永久绕过付费水印。

**建议**：立即引入状态签名机制并配合 Keychain 双重验证，中长期考虑移除本地持久化缓存，改为每次启动时实时验证 App Store 收据。
