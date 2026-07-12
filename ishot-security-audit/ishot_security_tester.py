#!/usr/bin/env python3
"""
================================================================================
iShot 付费水印安全测试工具 (iShot Security Tester)
================================================================================
版本: 1.0
作者: 安全测试团队
日期: 2026-07-12

用途: 模拟黑客攻击 iShot 付费水印功能，验证安全防护有效性。
      仅供内部安全审计使用，严禁外泄。

支持功能:
  - auto      自动检测版本、验证 patch 点、执行攻击 (一键式)
  - dry-run   仅验证 patch 点，不修改文件
  - attack    执行 CBZ→B 二进制 patch 攻击
  - plist     执行 Plist 篡改攻击 (验证该路径无效)
  - restore   从备份恢复原始二进制
  - status    查看当前 patch 状态
  - report    生成测试报告

用法:
  python3 ishot_security_tester.py auto              # 一键自动攻击
  python3 ishot_security_tester.py dry-run           # 仅验证不修改
  python3 ishot_security_tester.py attack            # 执行二进制 patch
  python3 ishot_security_tester.py plist             # Plist 篡改测试
  python3 ishot_security_tester.py restore           # 恢复原始版本
  python3 ishot_security_tester.py status            # 查看状态
  python3 ishot_security_tester.py report            # 生成测试报告

注意: attack/restore 需要 sudo 权限（修改 /Applications 下的文件）
================================================================================
"""

import os
import sys
import struct
import shutil
import hashlib
import subprocess
import time
import json
import plistlib
from pathlib import Path
from datetime import datetime


# ============================================================================
# 配置常量
# ============================================================================

class Config:
    ISHOT_APP = "/Applications/iShot.app"
    ISHOT_BIN = f"{ISHOT_APP}/Contents/MacOS/iShot"
    ISHOT_PLIST = f"{ISHOT_APP}/Contents/Info.plist"
    BACKUP_SUFFIX = ".bak_watermark_security_test"

    PLIST_PATH = os.path.expanduser(
        "~/Library/Group Containers/4K6FWZU8C4.group.cn.better365/"
        "Library/Preferences/4K6FWZU8C4.group.cn.better365.plist"
    )

    # Mach-O __TEXT 段虚拟地址基址
    TEXT_BASE = 0x100000000

    # Patch 点定义 (VM 地址)
    _PATCH_VM = [
        {"vm_addr": 0x10001A15C, "orig": 0x34000648, "patch": 0x14000032, "desc": "长截图水印"},
        {"vm_addr": 0x10005F6C0, "orig": 0x340005A8, "patch": 0x1400002D, "desc": "全屏带壳截图水印"},
        {"vm_addr": 0x1000B2858, "orig": 0x34000648, "patch": 0x14000032, "desc": "普通截图水印"},
    ]

    @classmethod
    def get_arm64_slice_offset(cls):
        """动态检测 ARM64 slice 在 fat binary 中的偏移"""
        try:
            result = subprocess.run(
                ["otool", "-f", cls.ISHOT_BIN],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.split("\n")
            capture = False
            for line in lines:
                if "architecture 1" in line:
                    capture = True
                    continue
                if capture and "cputype" in line:
                    cputype = int(line.strip().split()[1])
                    if cputype == 16777228:  # ARM64
                        continue
                    else:
                        capture = False
                if capture and "offset" in line:
                    return int(line.strip().split()[1])
        except Exception:
            pass
        # 兜底：常见默认值
        return 0x21C000

    @classmethod
    def get_patch_points(cls):
        """根据当前 ARM64 slice 偏移计算 fat offset"""
        offset = cls.get_arm64_slice_offset()
        points = []
        for pp in cls._PATCH_VM:
            fat_off = offset + (pp["vm_addr"] - cls.TEXT_BASE)
            points.append({
                **pp,
                "fat_offset": fat_off,
            })
        return points

    REPORT_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================================
# 颜色输出
# ============================================================================

class Color:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    CYAN = "\033[0;36m"
    BLUE = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    WHITE = "\033[1;37m"
    NC = "\033[0m"
    BOLD = "\033[1m"


def cprint(color, msg):
    print(f"{color}{msg}{Color.NC}")


# ============================================================================
# 工具函数
# ============================================================================

def banner():
    print(Color.RED)
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║     iShot 付费水印安全测试工具 v1.0              ║")
    print("  ║     仅供内部安全审计使用                          ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print(Color.NC)


def require_root():
    if os.geteuid() != 0:
        cprint(Color.YELLOW, "[!] 此操作需要 root 权限，请使用 sudo 运行")
        cprint(Color.CYAN, f"    sudo python3 {sys.argv[0]} {sys.argv[1] if len(sys.argv) > 1 else ''}")
        sys.exit(1)


def get_ishot_version():
    """获取 iShot 版本号"""
    try:
        with open(Config.ISHOT_PLIST, "rb") as f:
            plist = plistlib.load(f)
        short = plist.get("CFBundleShortVersionString", "unknown")
        build = plist.get("CFBundleVersion", "unknown")
        return f"{short} (Build {build})"
    except Exception:
        return "unknown"


def is_binary_patched():
    """检查二进制是否已被 patch"""
    if not os.path.exists(Config.ISHOT_BIN):
        return None
    with open(Config.ISHOT_BIN, "rb") as f:
        data = f.read()
    patched_count = 0
    for pp in Config.get_patch_points():
        actual = struct.unpack_from("<I", data, pp["fat_offset"])[0]
        if actual == pp["patch"]:
            patched_count += 1
        elif actual != pp["orig"]:
            return "unknown"  # 既非原始也非 patch，可能是不同版本
    if patched_count == 3:
        return True
    if patched_count == 0:
        return False
    return "partial"


def has_backup():
    """检查备份是否存在"""
    return os.path.exists(Config.ISHOT_BIN + Config.BACKUP_SUFFIX)


def sha256_short(filepath):
    """文件 SHA256 前 16 位"""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()[:16]


# ============================================================================
# 状态检查
# ============================================================================

def cmd_status():
    """显示当前状态"""
    banner()
    print(f"{Color.CYAN}═══ 环境信息 ═══{Color.NC}")
    print(f"  iShot 版本:   {get_ishot_version()}")
    print(f"  安装路径:     {Config.ISHOT_APP}")

    if not os.path.exists(Config.ISHOT_APP):
        cprint(Color.RED, f"  [✗] iShot 未安装")
        return

    print(f"  [✓] iShot 已安装")

    # 二进制状态
    patched = is_binary_patched()
    print(f"\n{Color.CYAN}═══ 二进制状态 ═══{Color.NC}")
    if patched is True:
        cprint(Color.RED, f"  状态: 已破解 (3处 CBZ→B 全部生效)")
    elif patched is False:
        cprint(Color.GREEN, f"  状态: 原始 (水印保护正常)")
    elif patched == "partial":
        cprint(Color.YELLOW, f"  状态: 部分 patch (异常)")
    elif patched == "unknown":
        cprint(Color.YELLOW, f"  状态: 未知版本 (patch 点不匹配)")
    else:
        cprint(Color.YELLOW, f"  状态: 无法检测")

    print(f"  SHA256:   {sha256_short(Config.ISHOT_BIN)}...")
    print(f"  备份存在: {'是' if has_backup() else '否'}")

    # Plist 状态
    print(f"\n{Color.CYAN}═══ Plist 状态 ═══{Color.NC}")
    if os.path.exists(Config.PLIST_PATH):
        try:
            with open(Config.PLIST_PATH, "rb") as f:
                plist = plistlib.load(f)
            purchased = plist.get("iShotHavePurchased", "N/A")
            print(f"  iShotHavePurchased: {purchased}")
            install_time = plist.get("AppStoreiShotInstallTime", "N/A")
            if install_time != "N/A":
                dt = datetime.fromtimestamp(install_time)
                print(f"  安装时间:           {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            cprint(Color.YELLOW, f"  无法读取 Plist")
    else:
        print(f"  Plist 文件不存在")

    # 进程状态
    print(f"\n{Color.CYAN}═══ 进程状态 ═══{Color.NC}")
    result = subprocess.run(["pgrep", "-x", "iShot"], capture_output=True, text=True)
    if result.returncode == 0:
        pids = result.stdout.strip().split("\n")
        print(f"  iShot 运行中, PID: {', '.join(pids)}")
    else:
        print(f"  iShot 未运行")


# ============================================================================
# Dry-Run: 验证 patch 点
# ============================================================================

def cmd_dry_run():
    """验证所有 patch 点是否匹配当前版本"""
    banner()
    print(f"{Color.CYAN}[*] 版本: {get_ishot_version()}{Color.NC}\n")

    if not os.path.exists(Config.ISHOT_BIN):
        cprint(Color.RED, f"[!] 找不到 iShot 二进制")
        sys.exit(1)

    with open(Config.ISHOT_BIN, "rb") as f:
        data = f.read()

    all_ok = True
    for pp in Config.get_patch_points():
        actual = struct.unpack_from("<I", data, pp["fat_offset"])[0]
        if actual == pp["patch"]:
            cprint(Color.RED, f"  [已破解] {pp['desc']} — 0x{pp['fat_offset']:06X}: 0x{actual:08X}")
        elif actual == pp["orig"]:
            cprint(Color.GREEN, f"  [可攻击] {pp['desc']} — 0x{pp['fat_offset']:06X}: 0x{actual:08X} (CBZ)")
        else:
            cprint(Color.YELLOW, f"  [不匹配] {pp['desc']} — 0x{pp['fat_offset']:06X}: 期望=0x{pp['orig']:08X}, 实际=0x{actual:08X}")
            all_ok = False

    print()
    if all_ok:
        patched = is_binary_patched()
        if patched is True:
            cprint(Color.RED, "结论: 当前版本已被破解")
        else:
            cprint(Color.GREEN, "结论: 所有 patch 点验证通过，可以执行攻击")
            print(f"       执行: sudo python3 {sys.argv[0]} attack")
    else:
        cprint(Color.YELLOW, "结论: patch 点不匹配，可能版本已更新，需重新逆向定位")


# ============================================================================
# Plist 篡改攻击 (验证无效)
# ============================================================================

def cmd_plist():
    """Plist 篡改攻击 PoC"""
    banner()
    print(f"{Color.CYAN}[*] Plist 篡改攻击测试{Color.NC}\n")

    if not os.path.exists(Config.PLIST_PATH):
        cprint(Color.RED, f"[!] Plist 文件不存在: {Config.PLIST_PATH}")
        sys.exit(1)

    # 读取当前状态
    with open(Config.PLIST_PATH, "rb") as f:
        plist = plistlib.load(f)
    purchased = plist.get("iShotHavePurchased", "N/A")
    print(f"  篡改前: iShotHavePurchased = {purchased}")

    # 备份
    backup_path = Config.PLIST_PATH + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(Config.PLIST_PATH, backup_path)
    cprint(Color.GREEN, f"  备份: {backup_path}")

    # 篡改
    plist["iShotHavePurchased"] = True
    with open(Config.PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)
    cprint(Color.YELLOW, f"  篡改后: iShotHavePurchased = True")

    # 重启 iShot
    subprocess.run(["killall", "iShot"], capture_output=True)
    time.sleep(2)
    subprocess.run(["open", "-a", "iShot"], capture_output=True)
    cprint(Color.GREEN, "  iShot 已重启")
    time.sleep(3)

    # 复查
    with open(Config.PLIST_PATH, "rb") as f:
        plist = plistlib.load(f)
    purchased_after = plist.get("iShotHavePurchased", "N/A")
    print(f"  启动后: iShotHavePurchased = {purchased_after}")

    print()
    if purchased_after in (False, 0, "0"):
        cprint(Color.RED, "结论: Plist 篡改失败 — 应用启动时重置了该值")
        cprint(Color.CYAN, "       iShotHavePurchased 是输出标记，非输入开关")
        print(f"       恢复: cp {backup_path} {Config.PLIST_PATH}")
    else:
        cprint(Color.GREEN, "结论: Plist 篡改成功 (异常情况)")


# ============================================================================
# 二进制 CBZ→B Patch 攻击
# ============================================================================

def cmd_attack():
    """执行二进制 patch 攻击"""
    banner()
    require_root()

    print(f"{Color.CYAN}[*] 版本: {get_ishot_version()}{Color.NC}\n")

    if not os.path.exists(Config.ISHOT_BIN):
        cprint(Color.RED, f"[!] 找不到 iShot 二进制")
        sys.exit(1)

    # 读取二进制
    cprint(Color.CYAN, "[Step 1/5] 读取二进制...")
    with open(Config.ISHOT_BIN, "rb") as f:
        data = bytearray(f.read())
    orig_hash = hashlib.sha256(data).hexdigest()
    print(f"  SHA256: {orig_hash[:16]}...")

    # 验证 patch 点
    cprint(Color.CYAN, "\n[Step 2/5] 验证 patch 点...")
    for pp in Config.get_patch_points():
        actual = struct.unpack_from("<I", data, pp["fat_offset"])[0]
        if actual == pp["patch"]:
            cprint(Color.RED, f"  [已破解] {pp['desc']} — 跳过")
        elif actual == pp["orig"]:
            cprint(Color.GREEN, f"  [可攻击] {pp['desc']} — 0x{actual:08X}")
        else:
            cprint(Color.RED, f"  [不匹配] {pp['desc']} — 版本可能已更新，中止")
            sys.exit(1)

    # 备份
    cprint(Color.CYAN, "\n[Step 3/5] 备份原始二进制...")
    backup_path = Config.ISHOT_BIN + Config.BACKUP_SUFFIX
    if not os.path.exists(backup_path):
        shutil.copy2(Config.ISHOT_BIN, backup_path)
        cprint(Color.GREEN, f"  备份: {backup_path}")
    else:
        cprint(Color.YELLOW, "  备份已存在，跳过")

    # 执行 patch
    cprint(Color.YELLOW, "\n[Step 4/5] 执行 CBZ → B patch...")
    for pp in Config.get_patch_points():
        actual = struct.unpack_from("<I", data, pp["fat_offset"])[0]
        if actual == pp["orig"]:
            struct.pack_into("<I", data, pp["fat_offset"], pp["patch"])
            cprint(Color.GREEN, f"  [OK] {pp['desc']}: 0x{pp['orig']:08X} → 0x{pp['patch']:08X}")

    # 写入
    with open(Config.ISHOT_BIN, "wb") as f:
        f.write(data)
    patched_hash = hashlib.sha256(data).hexdigest()
    print(f"  SHA256 (patch后): {patched_hash[:16]}...")

    # 自检
    cprint(Color.CYAN, "\n[Step 5/5] 写入自检 + 重启...")
    with open(Config.ISHOT_BIN, "rb") as f:
        verify = f.read()
    all_patched = True
    for pp in Config.get_patch_points():
        actual = struct.unpack_from("<I", verify, pp["fat_offset"])[0]
        if actual == pp["patch"]:
            cprint(Color.GREEN, f"  [✓] {pp['desc']}")
        else:
            cprint(Color.RED, f"  [✗] {pp['desc']}: 0x{actual:08X}")
            all_patched = False

    # 重启
    subprocess.run(["killall", "iShot"], capture_output=True)
    time.sleep(2)
    result = subprocess.run(["open", "-a", "iShot"], capture_output=True, text=True)

    print()
    if all_patched:
        cprint(Color.RED, "════════════════════════════════════════════")
        cprint(Color.RED, "  攻击成功！三处水印 CBZ→B 全部生效")
        cprint(Color.RED, "════════════════════════════════════════════")
    else:
        cprint(Color.YELLOW, "部分 patch 失败，请检查")

    print()
    print("  后续步骤:")
    print(f"    1. 重签名: sudo codesign --force --deep --sign - {Config.ISHOT_APP}")
    print(f"    2. 重置权限: tccutil reset ScreenCapture cn.better365.ishot")
    print(f"    3. 测试长截图/全屏带壳截图，验证水印是否消失")
    print(f"    4. 恢复: sudo python3 {sys.argv[0]} restore")

    if result.returncode != 0:
        print()
        cprint(Color.YELLOW, "  [!] iShot 可能因签名失效无法启动，请执行步骤 1")


# ============================================================================
# 恢复
# ============================================================================

def cmd_restore():
    """从备份恢复原始二进制"""
    banner()
    require_root()

    backup_path = Config.ISHOT_BIN + Config.BACKUP_SUFFIX
    if not os.path.exists(backup_path):
        cprint(Color.RED, f"[!] 未找到备份文件: {backup_path}")
        cprint(Color.YELLOW, "  提示: 如未备份，重新安装 iShot 即可恢复")
        sys.exit(1)

    cprint(Color.CYAN, "[*] 恢复原始二进制...")
    subprocess.run(["killall", "iShot"], capture_output=True)
    time.sleep(1)

    shutil.copy2(backup_path, Config.ISHOT_BIN)
    cprint(Color.GREEN, f"[+] 已恢复: {backup_path} → {Config.ISHOT_BIN}")

    # 验证
    patched = is_binary_patched()
    if patched is False:
        cprint(Color.GREEN, "[+] 验证通过: 三处 patch 点已还原")
    else:
        cprint(Color.YELLOW, "[-] 验证异常，请检查")

    print()
    print(f"  后续步骤:")
    print(f"    1. 重签名: sudo codesign --force --deep --sign - {Config.ISHOT_APP}")
    print(f"    2. 重新打开 iShot")


# ============================================================================
# 一键自动攻击
# ============================================================================

def cmd_auto():
    """一键自动攻击: dry-run → attack → 提示后续步骤"""
    banner()
    print(f"{Color.CYAN}[*] 版本: {get_ishot_version()}{Color.NC}")

    # 先检查状态
    patched = is_binary_patched()
    if patched is True:
        cprint(Color.RED, "\n[!] 当前已经是破解状态，无需重复攻击")
        print(f"    如需恢复: sudo python3 {sys.argv[0]} restore")
        return

    if patched == "unknown":
        cprint(Color.YELLOW, "\n[!] patch 点不匹配，可能版本已更新")
        print(f"    可执行 dry-run 查看详情: python3 {sys.argv[0]} dry-run")
        return

    # 执行 dry-run
    print(f"\n{Color.CYAN}[*] 验证 patch 点...{Color.NC}")
    with open(Config.ISHOT_BIN, "rb") as f:
        data = f.read()

    all_ok = True
    for pp in Config.get_patch_points():
        actual = struct.unpack_from("<I", data, pp["fat_offset"])[0]
        if actual == pp["orig"]:
            cprint(Color.GREEN, f"  [OK] {pp['desc']}")
        elif actual == pp["patch"]:
            cprint(Color.RED, f"  [已破] {pp['desc']}")
        else:
            cprint(Color.YELLOW, f"  [??] {pp['desc']}: 0x{actual:08X}")
            all_ok = False

    if not all_ok:
        cprint(Color.RED, "\n[!] 验证失败，中止攻击")
        sys.exit(1)

    # 需要 sudo
    if os.geteuid() != 0:
        cprint(Color.YELLOW, "\n[!] 需要 root 权限执行攻击")
        cprint(Color.CYAN, f"    请执行: sudo python3 {sys.argv[0]} attack")
        print(f"    或先 sudo 运行本命令: sudo python3 {sys.argv[0]} auto")
        sys.exit(1)

    # 确认
    print()
    cprint(Color.YELLOW, "即将修改 iShot 二进制文件，移除三处付费水印检查。")
    confirm = input("确认执行? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("已取消")
        return

    cmd_attack()

    # 提示重签名
    print()
    cprint(Color.CYAN, "════════════════════════════════════════════")
    cprint(Color.CYAN, "  请手动执行重签名（否则 iShot 无法启动）:")
    cprint(Color.WHITE, f"  sudo codesign --force --deep --sign - {Config.ISHOT_APP}")
    cprint(Color.WHITE, "  tccutil reset ScreenCapture cn.better365.ishot")
    cprint(Color.CYAN, "════════════════════════════════════════════")


# ============================================================================
# 生成测试报告
# ============================================================================

def cmd_report():
    """生成测试报告"""
    banner()
    print(f"{Color.CYAN}[*] 生成测试报告...{Color.NC}")

    version = get_ishot_version()
    patched = is_binary_patched()
    backup_exists = has_backup()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_name = f"ishot_security_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_path = os.path.join(Config.REPORT_DIR, report_name)

    status_text = {
        True: "已破解 (3处 CBZ→B 全部生效)",
        False: "原始状态 (水印保护正常)",
        "partial": "部分 patch (异常)",
        "unknown": "未知版本 (patch 点不匹配)",
        None: "未安装",
    }.get(patched, "未知")

    points = Config.get_patch_points()
    rows = "\n".join(
        f"| {i} | {p['desc']} | 0x{p['vm_addr']:X} | 0x{p['fat_offset']:X} | 0x{p['orig']:08X} | 0x{p['patch']:08X} |"
        for i, p in enumerate(points, 1)
    )

    report = f"""# iShot 付费水印安全测试报告

> 生成时间: {now}
> 工具版本: 1.0
> 测试目标: iShot {version}

---

## 测试结果

| 项目 | 结果 |
|------|------|
| iShot 版本 | {version} |
| 二进制状态 | {status_text} |
| SHA256 | {sha256_short(Config.ISHOT_BIN)}... |
| 备份存在 | {'是' if backup_exists else '否'} |

## Patch 点详情

| # | 功能 | VM 地址 | Fat 偏移 | 原始 (CBZ) | Patch (B) |
|---|------|--------|---------|-----------|----------|
{rows}

## 操作记录

| 命令 | 说明 |
|------|------|
| `python3 ishot_security_tester.py attack` | 执行攻击 |
| `python3 ishot_security_tester.py restore` | 恢复原始版本 |
| `sudo codesign --force --deep --sign - /Applications/iShot.app` | 重签名 |

---

*此报告由 iShot Security Tester v1.0 自动生成*
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    cprint(Color.GREEN, f"[+] 报告已生成: {report_path}")
    print()
    print(report)


# ============================================================================
# 帮助
# ============================================================================

def cmd_help():
    banner()
    print(f"{Color.CYAN}用法:{Color.NC}")
    print(f"  python3 {sys.argv[0]} <命令>\n")
    print(f"{Color.CYAN}命令:{Color.NC}")
    print(f"  {Color.WHITE}auto{Color.NC}      一键自动攻击 (验证 + 攻击)")
    print(f"  {Color.WHITE}dry-run{Color.NC}   仅验证 patch 点，不修改文件")
    print(f"  {Color.WHITE}attack{Color.NC}    执行 CBZ→B 二进制 patch 攻击 (需 sudo)")
    print(f"  {Color.WHITE}plist{Color.NC}     Plist 篡改攻击测试")
    print(f"  {Color.WHITE}restore{Color.NC}   从备份恢复原始二进制 (需 sudo)")
    print(f"  {Color.WHITE}status{Color.NC}    查看当前状态")
    print(f"  {Color.WHITE}report{Color.NC}    生成测试报告")
    print(f"  {Color.WHITE}help{Color.NC}      显示帮助\n")
    print(f"{Color.CYAN}示例:{Color.NC}")
    print(f"  # 第一步: 验证是否可以攻击")
    print(f"  python3 {sys.argv[0]} dry-run")
    print(f"")
    print(f"  # 第二步: 执行攻击")
    print(f"  sudo python3 {sys.argv[0]} attack")
    print(f"")
    print(f"  # 第三步: 重签名 (patch 后签名失效)")
    print(f"  sudo codesign --force --deep --sign - /Applications/iShot.app")
    print(f"  tccutil reset ScreenCapture cn.better365.ishot")
    print(f"")
    print(f"  # 恢复")
    print(f"  sudo python3 {sys.argv[0]} restore")
    print(f"  sudo codesign --force --deep --sign - /Applications/iShot.app")


# ============================================================================
# 入口
# ============================================================================

COMMANDS = {
    "auto": cmd_auto,
    "dry-run": cmd_dry_run,
    "attack": cmd_attack,
    "plist": cmd_plist,
    "restore": cmd_restore,
    "status": cmd_status,
    "report": cmd_report,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
}


def main():
    if len(sys.argv) < 2:
        cmd_help()
        return

    cmd = sys.argv[1].lower()
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        cprint(Color.RED, f"[!] 未知命令: {cmd}")
        cmd_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
