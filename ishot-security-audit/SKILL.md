---
name: ishot-security-audit
description: >
  iShot 付费水印安全审计与绕过复现。USE WHEN 用户说 iShot 水印、iShot 破解、
  iShot 付费绕过、iShot 安全审计、iShot 二进制 patch、截图水印绕过、
  ishot watermark bypass、ishot crack、ishot security test。
  覆盖 Plist 篡改攻击(无效)、ARM64 CBZ→B 二进制 patch 攻击(有效)、
  重签名与权限重置、恢复流程。所有操作使用 macOS 系统自带工具。
metadata:
  version: "1.0.0"
  author: security-team
  use_case: iShot 长截图付费水印安全审计与攻击复现
---

# iShot Security Audit · iShot 付费水印安全审计

对 iShot v2.6.7 付费水印功能进行完整安全审计，复现绕过攻击，评估防护有效性。

## 核心发现

| 项目 | 结论 |
|------|------|
| 能否绕过付费水印 | **能** |
| 有效攻击方式 | ARM64 二进制指令 patch（CBZ → B） |
| 无效攻击方式 | Plist 篡改 `iShotHavePurchased`（启动时重置） |
| patch 字节数 | 3 处 × 4 字节 = 12 字节 |
| 攻击难度 | **低**（5 分钟内可完成） |
| 所需工具 | 全部 macOS 系统自带（otool / xxd / codesign） |

## 技能脚本

核心攻击逻辑封装在 `ishot_security_tester.py`，AI 工具只负责调用脚本，不重复实现逻辑。

### 工具脚本

```bash
cd <本skill目录> && python3 ishot_security_tester.py <命令>
```

| 命令 | 说明 | 需要 sudo |
|------|------|----------|
| `auto` | 一键自动攻击（验证 + patch） | 是 |
| `dry-run` | 仅验证 patch 点，不修改文件 | 否 |
| `attack` | 执行 CBZ→B 二进制 patch 攻击 | 是 |
| `plist` | Plist 篡改攻击测试（验证该路径无效） | 否 |
| `restore` | 从备份恢复原始二进制 | 是 |
| `status` | 查看当前 patch 状态 | 否 |
| `report` | 生成测试报告 | 否 |

### 标准工作流

```bash
# 第一步：查看当前状态
python3 ishot_security_tester.py status

# 第二步：验证攻击可行性（不修改文件）
python3 ishot_security_tester.py dry-run

# 第三步：执行攻击
sudo python3 ishot_security_tester.py attack

# 第四步：重签名 + 重置权限（攻击后签名失效）
sudo codesign --force --deep --sign - /Applications/iShot.app
tccutil reset ScreenCapture cn.better365.ishot
```

## 攻击原理

### 漏洞根因

水印控制链路为纯本地布尔变量，无 HMAC 签名、无加密保护、无服务端兜底：

```
[启动] → ApplePurchaseManager 验证收据 → 写入 iShotHavePurchased
                                                   ↓
[每次截图] → 读取 g_needWatermark 全局变量 → CBZ 判断 → 叠加/跳过水印
```

### Plist 篡改（无效路径）

`iShotHavePurchased` 是**输出标记**而非**输入开关**。每次启动时该值被无条件重置为 `false`，仅在收据验证成功后才写回 `true`。直接修改 Plist 无效，但此路径有记录价值。

```bash
# PoC: 篡改会被启动流程覆盖
python3 ishot_security_tester.py plist
```

### ARM64 CBZ→B Patch（有效路径）

将三处水印条件跳转（CBZ）替换为无条件跳转（B），使程序永远跳过水印绘制块。

| # | 功能 | VM 地址 | Fat 偏移 | CBZ → B |
|---|------|--------|---------|---------|
| 1 | 长截图水印 | `0x10001A15C` | `0x23615C` | `0x34000648` → `0x14000032` |
| 2 | 全屏带壳截图水印 | `0x10005F6C0` | `0x27B6C0` | `0x340005A8` → `0x1400002D` |
| 3 | 普通截图水印 | `0x1000B2858` | `0x2CE858` | `0x34000648` → `0x14000032` |

## 恢复流程

```bash
# 从备份恢复原始二进制
sudo python3 ishot_security_tester.py restore

# 重签名恢复
sudo codesign --force --deep --sign - /Applications/iShot.app

# 可选：删除备份文件
sudo rm /Applications/iShot.app/Contents/MacOS/iShot.bak_watermark_security_test
```

## 重签名与权限

patch 后原始 Apple Developer ID 签名失效，需 ad-hoc 重签名。签名变更导致系统将 iShot 识别为新应用，之前授予的权限失效，需重新授权：

```bash
sudo codesign --force --deep --sign - /Applications/iShot.app
tccutil reset ScreenCapture cn.better365.ishot
```

## Patch 持久性

| 场景 | Patch 是否保留 |
|------|-------------|
| 重启电脑 | 保留 |
| 注销/切换用户 | 保留 |
| macOS 系统更新 | 保留 |
| App Store 更新 iShot | **丢失** |
| 手动重新安装 iShot | **丢失** |
| 手动执行 restore | **丢失** |

## 审计环境

| 项目 | 值 |
|------|-----|
| macOS | 14.6 |
| 架构 | Apple Silicon (ARM64) |
| iShot 版本 | v2.6.7 (Build 20260128001) |
| Bundle ID | cn.better365.ishot |
| App Group | 4K6FWZU8C4.group.cn.better365 |

## 参考文档

| 文档 | 内容 |
|------|------|
| `references/attack-reproduction.md` | 攻击复现完整报告（步骤、脚本源码、修复建议） |
| `references/binary-reverse-engineering.md` | ARM64 二进制逆向详细记录（CBZ 定位、fat binary 结构、踩坑） |
| `references/plist-i-analysis.md` | Plist 篡改分析 + IAP 流程逆向 + 攻击面总结 |

## 依赖

- Python 3（标准库）
- macOS 系统自带工具：`otool`、`xxd`、`strings`、`codesign`、`tccutil`
