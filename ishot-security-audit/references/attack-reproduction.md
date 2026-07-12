# iShot 长截图付费水印绕过 — 攻击复现完整报告

> **文档目的**: 供开发团队完整复现漏洞、评估风险、验证修复
> **审计版本**: iShot v2.6.7 (Build 20260128001)
> **Bundle ID**: cn.better365.ishot
> **审计日期**: 2026-07-12
> **审计人员**: 安全测试工程师

---

## 1. 测试结论

| 项目 | 结论 |
|------|------|
| 能否绕过付费水印 | **能** |
| 绕过方式 | ARM64 二进制指令 patch（CBZ → B） |
| patch 字节数 | 3 处 × 4 字节 = 12 字节 |
| 应用是否正常启动 | **正常**（重签名后） |
| 所需工具 | 全部 macOS 系统自带（otool / xxd / strings / codesign） |
| 攻击难度 | **低**（5 分钟内可完成） |
| 持久性 | 永久（直到应用更新） |

---

## 2. 漏洞根因

水印控制链路：

```
[启动] → ApplePurchaseManager 验证 App Store 收据 → 写入 iShotHavePurchased
                                                           ↓
[每次截图] → 读取 g_needWatermark 全局变量 (0x100195921) → CBZ 判断 → 叠加/跳过水印
```

**三个关键缺陷**：

1. **水印判断是纯本地布尔变量** — `g_needWatermark` 是一个 `__DATA` 段中的 `BOOL` 全局变量，无 HMAC 签名、无加密
2. **无水印拦截的服务端兜底** — 收据验证仅首次购买时执行一次，后续截图完全依赖本地状态
3. **二进制无完整性自检** — 无代码签名运行时校验、无反篡改检测

---

## 3. 攻击路径分析

测试了两种攻击向量：

| # | 攻击方式 | 效果 | 原因 |
|---|---------|------|------|
| 1 | Plist 篡改 `iShotHavePurchased` | **失败** | 每次启动时值被无条件重置为 `false`，仅在收据验证成功后写回 `true` |
| 2 | ARM64 二进制 CBZ → B 指令 patch | **成功** | 将三处水印条件跳转替换为无条件跳转，使水印绘制块永远不被执行 |

### 3.1 Plist 攻击为何失败

```
iShot 启动流程:
  iShotHavePurchased ← NO           ← 无条件重置
  ↓
  内部验证标志读取 (0x100196558)
  ↓
  仅当内部标志 = 1 时才写回 YES
```

`iShotHavePurchased` 是**输出标记**而非**输入开关**，直接修改无效。

### 3.2 二进制 Patch 攻击原理

ARM64 反汇编中三处水印条件跳转：

```asm
; 水印判断
adrp x8, #0x100195000
add  x8, x8, #0x921              ; → g_needWatermark (0x100195921)
ldrb w8, [x8]                     ; 读取 bool
cbz  w8, skip_watermark           ; ★ 若 false 则跳过水印 (CBZ = Compare and Branch if Zero)
; ... 水印绘制块 ...
skip_watermark:
; 正常截图流程
```

将 `CBZ` 替换为无条件跳转 `B`，程序将**永远跳过水印绘制块**。

---

## 4. 完整复现步骤

### 4.1 环境要求

- macOS (Apple Silicon / Intel 均可)
- iShot v2.6.7 (Build 20260128001) 已安装
- 终端 + sudo 权限
- 全部使用系统自带工具，无需安装第三方软件

### 4.2 执行步骤

**Step 1 — 进入脚本目录**
```bash
cd /path/to/iShot/skill/
```

**Step 2 — 干运行验证 patch 点**
```bash
python3 ishot_attack_cbz_patch.py dry-run
```

预期输出：三处全部显示 `验证通过`。如有失败说明版本不匹配。

**Step 3 — 执行 patch**
```bash
sudo python3 ishot_attack_cbz_patch.py
```

脚本自动完成：备份原始二进制 → 替换三处 CBZ 为 B → 自检验证 → 启动 iShot。

**Step 4 — 重新签名（patch 后签名失效）**
```bash
sudo codesign --force --deep --sign - /Applications/iShot.app
```

**Step 5 — 重置屏幕录制权限（签名变更导致权限失效）**
```bash
tccutil reset ScreenCapture cn.better365.ishot
```

**Step 6 — 验证**
- 重新打开 iShot
- 系统弹出屏幕录制权限请求，勾选允许
- 执行长截图 → 水印消失
- 执行全屏带壳截图 → 水印消失

**Step 7 — 恢复原始版本**
```bash
sudo python3 ishot_attack_cbz_patch.py restore
sudo codesign --force --deep --sign - /Applications/iShot.app
```

---

## 5. 代码签名问题说明

patch 修改了二进制内容，原始 Apple Developer ID 签名失效，macOS Gatekeeper 阻止启动。

- **现象**: 点击图标无响应
- **原因**: 签名校验失败（`codesign -v` 报错）
- **解决**: `sudo codesign --force --deep --sign - /Applications/iShot.app` 用 ad-hoc 签名替换

签名变更后，系统将 patch 后的 iShot 识别为新应用，之前授予的辅助功能/屏幕录制权限全部失效，需重新授权。

### 5.1 Patch 持久性说明

| 场景 | Patch 是否保留 | 说明 |
|------|-------------|------|
| 重启电脑 | **保留** | 修改的是磁盘上的二进制文件，重启不恢复 |
| 注销/切换用户 | **保留** | 同上 |
| App Store 更新 iShot | **丢失** | 更新会替换整个 .app bundle，恢复原始二进制 |
| 手动重新安装 iShot | **丢失** | 覆盖安装同理 |
| 手动执行 restore 命令 | **丢失** | 从备份恢复原始文件 |
| macOS 系统更新 | **保留** | 系统更新不触及第三方应用二进制 |

**关键结论**：patch 写入磁盘文件，属于永久性修改。只要不更新/重装 iShot，重启、关机、注销均不影响破解状态。

---

## 6. Patch 地址速查表

| # | 功能 | VM 地址 | Fat 文件偏移 | 操作码 (CBZ) | 操作码 (B) |
|---|------|--------|-------------|-------------|-----------|
| 1 | 长截图水印 | `0x10001A15C` | `0x23615C` | `0x34000648` | `0x14000032` |
| 2 | 全屏带壳截图水印 | `0x10005F6C0` | `0x27B6C0` | `0x340005A8` | `0x1400002D` |
| 3 | 截图水印 | `0x1000B2858` | `0x2CE858` | `0x34000648` | `0x14000032` |

Fat 文件偏移换算公式：

```
fat_offset = ARM64_slice_offset + (VM_address - TEXT_base)

ARM64_slice_offset = 0x21C000    (来自 otool -f)
TEXT_base          = 0x100000000 (Mach-O __TEXT 段基址)
```

---

## 7. 脚本清单

| 文件 | 功能 |
|------|------|
| `ishot_attack_cbz_patch.py` | 二进制 CBZ→B patch 工具（备份/验证/patch/恢复/干运行） |
| `ishot_attack_plist_tamper.sh` | Plist 篡改 PoC（验证绕过无效） |
| `ishot_attack_restore.sh` | Plist 恢复脚本 |

---

## 8. 恢复脚本完整源码

```bash
#!/bin/bash
# ============================================================
# iShot 攻击恢复脚本 - 从备份还原 Plist
# ============================================================

PLIST_DIR="$HOME/Library/Group Containers/4K6FWZU8C4.group.cn.better365/Library/Preferences"
PLIST_FILE="$PLIST_DIR/4K6FWZU8C4.group.cn.better365.plist"

echo "[*] 查找备份文件..."
BACKUPS=$(ls -t "${PLIST_FILE}.bak_"* 2>/dev/null || true)

if [ -z "$BACKUPS" ]; then
    echo "[!] 未找到备份文件"
    exit 1
fi

echo "[*] 可用的备份文件:"
ls -la "${PLIST_FILE}.bak_"* 2>/dev/null

LATEST=$(echo "$BACKUPS" | head -1)
echo ""
echo -n "[*] 使用最新备份恢复? [$LATEST] (y/n): "
read -r CONFIRM

if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
    killall iShot 2>/dev/null || true
    sleep 1
    cp "$LATEST" "$PLIST_FILE"
    echo "[+] 已恢复: $LATEST -> $PLIST_FILE"
    VAL=$(/usr/libexec/PlistBuddy -c "Print :iShotHavePurchased" "$PLIST_FILE" 2>/dev/null || echo "N/A")
    echo "[+] 当前状态: iShotHavePurchased = $VAL"
else
    echo "[-] 取消恢复"
fi
```

**二进制恢复**由 `ishot_attack_cbz_patch.py restore` 子命令完成（见第 9 节完整源码中的 `restore_from_backup` 函数），恢复后需重签名：

```bash
sudo python3 ishot_attack_cbz_patch.py restore
sudo codesign --force --deep --sign - /Applications/iShot.app
```

## 9. CBZ Patch 脚本完整源码

```python
#!/usr/bin/env python3
"""
================================================================
iShot 付费水印绕过 PoC - ARM64 二进制 CBZ→B Patch 攻击
================================================================
作者: 安全测试团队
日期: 2026-07-12
用途: 仅供 iShot 内部安全审计使用，禁止外泄
原理: 将三处水印条件跳转 (CBZ) 替换为无条件跳转 (B)，
      使程序永远跳过水印绘制块。
================================================================
"""

import os
import struct
import shutil
import hashlib
import sys
from pathlib import Path

# ---- 配置 ----
ISHOT_BIN = "/Applications/iShot.app/Contents/MacOS/iShot"
BACKUP_SUFFIX = ".bak_watermark_patch"

# ARM64 slice 在 fat binary 中的偏移 (来自 otool -f)
ARM64_SLICE_OFFSET = 0x21C000

# 三处水印条件跳转 (CBZ) 地址与 Patch 操作码
PATCH_POINTS = [
    {
        "vm_addr": 0x10001A15C,
        "fat_offset": 0x23615C,
        "original_hex": 0x34000648,
        "patch_hex": 0x14000032,
        "desc": "长截图水印叠加 (CBZ W8 +0xC8 → B +0xC8)",
    },
    {
        "vm_addr": 0x10005F6C0,
        "fat_offset": 0x27B6C0,
        "original_hex": 0x340005A8,
        "patch_hex": 0x1400002D,
        "desc": "全屏带壳截图水印 (CBZ W8 +0xB4 → B +0xB4)",
    },
    {
        "vm_addr": 0x1000B2858,
        "fat_offset": 0x2CE858,
        "original_hex": 0x34000648,
        "patch_hex": 0x14000032,
        "desc": "截图水印 (CBZ W8 +0xC8 → B +0xC8)",
    },
]

# ---- 颜色输出 ----
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def banner():
    print(RED)
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   iShot 水印绕过 PoC - ARM64 CBZ→B Patch    ║")
    print("  ║   仅供内部安全审计使用                        ║")
    print("  ╚══════════════════════════════════════════════╝")
    print(NC)


def check_env():
    import subprocess
    if not os.path.isfile(ISHOT_BIN):
        print(f"{RED}[!] 错误: 找不到 iShot 二进制: {ISHOT_BIN}{NC}")
        sys.exit(1)
    result = subprocess.run(["file", ISHOT_BIN], capture_output=True, text=True)
    if "universal" not in result.stdout.lower():
        print(f"{RED}[!] 错误: iShot 二进制不是 Universal (fat) 格式{NC}")
        sys.exit(1)
    print(f"{GREEN}[+] 二进制路径: {ISHOT_BIN}{NC}")
    print(f"{GREEN}[+] 格式: Universal (fat) binary{NC}")


def verify_bytes(data, offset, expected_hex, desc):
    actual = struct.unpack_from("<I", data, offset)[0]
    if actual != expected_hex:
        print(f"{RED}[!] 验证失败 [{desc}]{NC}")
        print(f"    文件偏移 0x{offset:06X}: 期望=0x{expected_hex:08X}, 实际=0x{actual:08X}")
        return False
    print(f"{GREEN}[+] 验证通过 [{desc}]{NC}")
    print(f"    偏移 0x{offset:06X}: 0x{actual:08X} (CBZ)")
    return True


def backup():
    backup_path = ISHOT_BIN + BACKUP_SUFFIX
    if os.path.exists(backup_path):
        print(f"{YELLOW}[-] 备份已存在, 跳过: {backup_path}{NC}")
        return backup_path
    print(f"{CYAN}[*] 备份原始二进制...{NC}")
    shutil.copy2(ISHOT_BIN, backup_path)
    print(f"{GREEN}[+] 备份完成: {backup_path}{NC}")
    return backup_path


def patch():
    print(f"{CYAN}[*] 读取二进制文件...{NC}")
    with open(ISHOT_BIN, "rb") as f:
        data = bytearray(f.read())
    original_hash = hashlib.sha256(data).hexdigest()
    print(f"    SHA256 (patch前): {original_hash[:16]}...")

    print(f"\n{CYAN}[*] 验证 patch 点...{NC}")
    all_ok = True
    for pp in PATCH_POINTS:
        if not verify_bytes(data, pp["fat_offset"], pp["original_hex"], pp["desc"]):
            all_ok = False
    if not all_ok:
        print(f"\n{RED}[!] patch 点验证失败, 可能版本不匹配, 中止{NC}")
        sys.exit(1)

    print(f"\n{CYAN}[*] 执行 CBZ → B patch...{NC}")
    for pp in PATCH_POINTS:
        struct.pack_into("<I", data, pp["fat_offset"], pp["patch_hex"])
        print(f"    [{pp['desc']}] 偏移 0x{pp['fat_offset']:06X}: 0x{pp['original_hex']:08X} → 0x{pp['patch_hex']:08X}")

    print(f"\n{CYAN}[*] 写入 patched 二进制...{NC}")
    with open(ISHOT_BIN, "wb") as f:
        f.write(data)
    patched_hash = hashlib.sha256(data).hexdigest()
    print(f"    SHA256 (patch后): {patched_hash[:16]}...")

    print(f"\n{CYAN}[*] 写入后自检...{NC}")
    with open(ISHOT_BIN, "rb") as f:
        verify = f.read()
    for pp in PATCH_POINTS:
        actual = struct.unpack_from("<I", verify, pp["fat_offset"])[0]
        status = f"{GREEN}✓{NC}" if actual == pp["patch_hex"] else f"{RED}✗{NC}"
        print(f"    [{status}] 0x{pp['fat_offset']:06X}: 0x{actual:08X}")

    return original_hash, patched_hash


def launch():
    print(f"\n{CYAN}[*] 重新启动 iShot...{NC}")
    import subprocess, time
    subprocess.run(["killall", "iShot"], capture_output=True)
    time.sleep(2)
    result = subprocess.run(["open", "-a", "iShot"], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"{GREEN}[+] iShot 启动成功{NC}")
    else:
        print(f"{RED}[!] iShot 启动失败: {result.stderr}{NC}")


def restore_from_backup():
    backup_path = ISHOT_BIN + BACKUP_SUFFIX
    if not os.path.exists(backup_path):
        print(f"{RED}[!] 未找到备份: {backup_path}{NC}")
        sys.exit(1)
    print(f"{CYAN}[*] 从备份恢复...{NC}")
    import subprocess
    subprocess.run(["killall", "iShot"], capture_output=True)
    import time
    time.sleep(1)
    shutil.copy2(backup_path, ISHOT_BIN)
    print(f"{GREEN}[+] 已恢复原始二进制{NC}")


def show_result(original_hash, patched_hash):
    print(f"\n{GREEN}════════════════════════════════════════════{NC}")
    print(f"{GREEN}  Patch 完成{NC}")
    print(f"{GREEN}════════════════════════════════════════════{NC}")
    print(f"")
    print(f"  攻击向量: ARM64 二进制 CBZ → B 指令替换")
    print(f"  目标文件: {ISHOT_BIN}")
    print(f"  Patch 前 SHA256: {original_hash}")
    print(f"  Patch 后 SHA256: {patched_hash}")
    print(f"")
    print(f"  Patch 点清单:")
    for pp in PATCH_POINTS:
        print(f"    - {pp['desc']}")
        print(f"      VM 0x{pp['vm_addr']:010X} / Fat 0x{pp['fat_offset']:06X}")
        print(f"      0x{pp['original_hex']:08X} → 0x{pp['patch_hex']:08X}")
    print(f"")
    print(f"  恢复命令: sudo python3 {__file__} restore")
    print(f"")


def main():
    banner()
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        restore_from_backup()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "dry-run":
        check_env()
        with open(ISHOT_BIN, "rb") as f:
            data = f.read()
        all_ok = True
        for pp in PATCH_POINTS:
            if not verify_bytes(data, pp["fat_offset"], pp["original_hex"], pp["desc"]):
                all_ok = False
        if all_ok:
            print(f"\n{GREEN}[+] 所有 patch 点验证通过, 可以执行 patch{NC}")
        else:
            print(f"\n{RED}[!] 验证失败, 请检查 iShot 版本{NC}")
        return
    if os.geteuid() != 0:
        print(f"{YELLOW}[!] 需要 root 权限, 请使用 sudo 运行{NC}")
        print(f"    sudo python3 {__file__}")
        print(f"    或干运行: python3 {__file__} dry-run")
        sys.exit(1)
    check_env()
    backup()
    original_hash, patched_hash = patch()
    launch()
    show_result(original_hash, patched_hash)


if __name__ == "__main__":
    main()
```

---

## 10. 修复建议（按优先级排序）

### P0 — 立即修复

1. **每次截图时实时验证 App Store Receipt**
   - 当前：仅在购买/恢复时验证一次，结果本地缓存
   - 改为：每次截图调用 `verifyReceipt`，失败则施加水印
   - 添加 3 秒内缓存以避免频繁网络请求

2. **Keychain + HMAC 签名保护付费标记**
   - 对 `iShotHavePurchased` 值做 HMAC-SHA256 签名
   - 同时存储到 Keychain（比 Plist 更难篡改）
   - 读取时交叉验证，不一致则回退未付费状态

### P1 — 短期改进

3. **二进制完整性自检**
   - 启动时计算 `__TEXT` 段哈希，与编译时嵌入的预期值比对
   - 不一致则拒绝运行或强制启用水印
   - 对水印控制逻辑使用控制流平坦化混淆

4. **反调试保护**
   - `ptrace(PT_DENY_ATTACH)` 阻止 lldb 附加
   - `sysctl` 检测调试器存在

### P2 — 长期架构改进

5. **服务端授权心跳**
   - 客户端定期向服务端发送心跳验证付费状态
   - 失败则重新启用全部限制

6. **关键函数内联**
   - 将水印判断逻辑内联到多个调用点
   - 增加 patch 成本（需修改所有内联副本）

---

## 11. 附录

### 11.1 测试环境

| 项目 | 值 |
|------|-----|
| macOS | 14.6 |
| 架构 | Apple Silicon (ARM64) |
| iShot 版本 | 2.6.7 (Build 20260128001) |
| iShot Bundle ID | cn.better365.ishot |
| 安装路径 | /Applications/iShot.app |
| App Group | 4K6FWZU8C4.group.cn.better365 |

### 11.2 关键文件

| 文件 | 用途 |
|------|------|
| `/Applications/iShot.app/Contents/MacOS/iShot` | 主二进制 (Universal) |
| `/Applications/iShot.app/Contents/Info.plist` | 应用配置 |
| `/Applications/iShot.app/Contents/Resources/Assets.car` | 资源包（含 needBuyWatermark.png） |
| `~/Library/Group Containers/4K6FWZU8C4.group.cn.better365/.../4K6FWZU8C4.group.cn.better365.plist` | 付费状态缓存 |

### 11.3 相关报告

| 报告 | 内容 |
|------|------|
| `iShot_水印安全审计技术报告.md` | ARM64 二进制逆向分析详细记录（CBZ 定位过程、fat binary 结构、踩坑记录） |
| `iShot_水印安全审计技术报告_v2.md` | Plist 篡改分析 + IAP 流程逆向 + 攻击面总结 |

### 11.4 测试 SHA256 记录

```
Patch 前: dc1daa3fb4e6f6191e8d9162efa5d8d48b97ce11f46edbf3b82b3dfa077c1995
Patch 后: 9be9c71b37c0b13f10d6b14a22770eb40aa1544bc59cb9d4b7198a8a8368a3f6
```
