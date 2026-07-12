# ARM64 Binary Patching Primer

Quick reference for common ARM64 (AArch64) instruction patch patterns used in macOS
application security audits. All patches modify the Mach-O binary directly.

---

## Prerequisites

### Locating Instructions

```bash
# 1. Find the binary
ls /path/to/Target.app/Contents/MacOS/

# 2. Determine architecture and fat offset
file /path/to/Target.app/Contents/MacOS/<binary>
otool -f /path/to/Target.app/Contents/MacOS/<binary>

# 3. For single-architecture arm64 binary: fat_offset = 0
#    For Universal binary: fat_offset comes from otool -f output

# 4. Disassemble around target address
otool -tV /path/to/Target.app/Contents/MacOS/<binary> | head -200

# 5. Calculate file offset: file_offset = fat_offset + (VM_addr - 0x100000000)
```

### Reading / Writing Bytes

```bash
# Read 4 bytes at offset (hex dump)
xxd -s <offset> -l 4 -p <binary>

# Write 4 bytes at offset
echo "<hex>" | xxd -r -p | dd of=<binary> bs=1 seek=<offset> conv=notrunc
```

---

## Patch Pattern 1: CBZ → B (Conditional Branch → Unconditional Branch)

**Use Case**: The application checks a condition (e.g., `isPurchased == false`) and
branches to show a watermark or restriction. Transform the conditional branch into
an unconditional branch so it *always* skips the restriction.

### Encoding

```
CBZ Xt, imm19        (Compare and Branch on Zero)
Encoding: 10110100 1xxxxxxxxx xxxxxxxxxx xxxxxxx0
          ^^^^^^^^ ^^--- imm19 ---^^  ^-- Rt --^

B   imm26            (Unconditional Branch)
Encoding: 000101xx xxxxxxxxxx xxxxxxxxxx xxxxxxxx
          ^^^^^^-- ^^------- imm26 ----------^^
```

### Transformation

Since both CBZ and B encode the branch offset in the same format (PC-relative,
in units of 4-byte instructions), the offset bits are directly compatible.

```
CBZ X0, +0xC8  →  B +0xC8
0x34 00 06 48     0x14 00 00 32

Breakdown:
  CBZ: 0x34 = 0011 0100 → Compare and Branch on Zero
  B:   0x14 = 0001 0100 → Unconditional Branch
```

### Manual Calculation

```
# Given: CBZ X0, target_addr  (at VM address current_addr)
# Step 1: Calculate offset in instructions
offset = (target_addr - current_addr) / 4

# Step 2: CBZ encoding
# Bits [31:24] = 0x34 (for 32-bit)
# Bits [23:5]  = imm19 (offset)
# Bits [4:0]   = Rt (register number, X0 = 0)

# Step 3: B encoding
# Bits [31:26] = 0x05 (000101)
# Bits [25:0]  = imm26 (offset)
```

### Example

```bash
# Original: CBZ X0, +0xC8  →  0x34000648
# Patched:  B   +0xC8      →  0x14000032

# Read original
xxd -s 0x23615C -l 4 -p /path/to/binary
# Output: 48000634  (little-endian: 0x34000648)

# Write patch (little-endian bytes)
echo "32000014" | xxd -r -p | dd of=/path/to/binary bs=1 seek=0x23615C conv=notrunc
```

---

## Patch Pattern 2: CBNZ → NOP (Skip Conditional Branch)

**Use Case**: "If not purchased, show restriction dialog." Replace with NOP so the
restriction code is never reached.

### Encoding

```
CBNZ Xt, imm19
Encoding: 10110101 1xxxxxxxxx xxxxxxxxxx xxxxxxx0

NOP
Encoding: 11010101 00000011 00100000 00011111  →  0xD503201F
```

### Example

```bash
# CBNZ X0, loc_xxx  →  0x35000040  (example)
# → NOP             →  0xD503201F

echo "1f2003d5" | xxd -r -p | dd of=/path/to/binary bs=1 seek=<offset> conv=notrunc
```

> **Note**: NOP replaces 4 bytes. If the branch instruction is followed by code that
> should be skipped, you may need to NOP a larger block. A 4-byte NOP only removes
> the branch decision, not the guarded code.

---

## Patch Pattern 3: MOVZ Change Return Value

**Use Case**: A function returns `false` (0) for unpaid users. Patch the return
register to always hold `true` (1).

### Encoding

```
MOVZ Xd, #imm16{, LSL #shift}
Encoding: 1 10 100101 xx xxxxxxxxxxxxxxxx xxxxx
          ^ ^^ ^^^^^^ ^^ ^------ imm16 ------^^ Rd

X0 = 0:  0xD2800000  (MOVZ X0, #0)
X0 = 1:  0xD2800020  (MOVZ X0, #1, LSL #0)
```

### Common Patterns

| Desired | Instruction | Machine Code |
|---------|------------|--------------|
| Return `false` | `MOVZ X0, #0` | `0xD2800000` |
| Return `true` | `MOVZ X0, #1` | `0xD2800020` |
| Return `false` | `MOV W0, #0` | `0x52800000` |
| Return `true` | `MOV W0, #1` | `0x52800020` |

### Example

```bash
# Function returns bool: MOVZ X0, #0 (false) → MOVZ X0, #1 (true)
# 0xD2800000 → 0xD2800020

echo "200080d2" | xxd -r -p | dd of=/path/to/binary bs=1 seek=<offset> conv=notrunc
```

> **Caution**: Changing a function return value may have side effects if the same
> function is used for multiple purposes. Verify via disassembly that the function
> is solely used for the targeted check.

---

## Patch Pattern 4: TBNZ → NOP + NOP (Bit Test and Branch)

**Use Case**: A single bit flag is tested before executing a restriction. NOP out
the test + branch entirely.

### Encoding

```
TBNZ Xt, #imm6, label
Encoding: 0x37xxxxxx (approximate; varies by register and offset)

Size: 4 bytes. If target address is far, linker may have emitted a
      TBNZ + B pair (8 bytes total).
```

### Example

```bash
# TBNZ X0, #0, loc  →  NOP
# + filler (if any) →  NOP

# Read 8 bytes and NOP both
echo "1f2003d51f2003d5" | xxd -r -p | dd of=/path/to/binary bs=1 seek=<offset> conv=notrunc
```

---

## Patch Pattern 5: Ret Immediate (Return Constant from Function)

**Use Case**: Entire function body replaced to always return `true`.

### Encoding

```
MOVZ X0, #1    ; 0xD2800020  — set return value
RET            ; 0xD65F03C0  — return
```

Total: 8 bytes.

### Example

```bash
# Replace function entry point with:
# MOVZ X0, #1 + RET
echo "200080d2c0035fd6" | xxd -r -p | dd of=/path/to/binary bs=1 seek=<function_offset> conv=notrunc
```

---

## Patch Pattern 6: B.cond → B (Conditional Branch → Unconditional)

**Use Case**: Similar to CBZ→B but for condition-code branches (B.EQ, B.NE, B.LT, etc.).

### Encoding

```
B.cond imm19
Encoding: 01010100 xxxxxxxxxx xxxxxxxxxx xxx0xxxx
          ^^^^^^^^^ ^^--- imm19 ---^^  ^cond^

B imm26
Encoding: 000101xx xxxxxxxxxx xxxxxxxxxx xxxxxxxx
```

### Transformation

Strip the condition bits, converting to unconditional branch with same offset:

```
B.EQ target  →  B target
0x54000040   →  0x14000010  (example; actual encoding depends on offset)
```

---

## Verification After Patching

```bash
# 1. Verify patch applied correctly
xxd -s <offset> -l 4 -p <binary>

# 2. Verify code signature is broken (expected)
codesign -vvv /path/to/Target.app
# Expected: code object is not signed at all / invalid signature

# 3. Re-sign
sudo codesign --force --deep --sign - /path/to/Target.app

# 4. Reset TCC permissions (signature identity changed)
tccutil reset All <bundle-id>
```

---

## ARM64 Quick Encoding Reference

| Opcode | Mnemonic | 32-bit Encoding (hex) |
|--------|----------|----------------------|
| `NOP` | No operation | `0xD503201F` |
| `RET` | Return | `0xD65F03C0` |
| `MOVZ X0, #0` | Move zero to X0 | `0xD2800000` |
| `MOVZ X0, #1` | Move 1 to X0 | `0xD2800020` |
| `MOV W0, #0` | Move zero to W0 | `0x52800000` |
| `MOV W0, #1` | Move 1 to W0 | `0x52800020` |
| `B loc` | Branch (unconditional) | `0x14xxxxxx` |
| `CBZ X0, loc` | Compare branch zero | `0x34xxxxxx` |
| `CBNZ X0, loc` | Compare branch non-zero | `0x35xxxxxx` |
| `B.EQ loc` | Branch if equal | `0x54xxxxx0` |
| `B.NE loc` | Branch if not equal | `0x54xxxxx1` |

> The `xx` in encoding represents offset bits — actual values depend on branch target.

---

## Safety Rules

1. **Always backup** before patching: `cp <binary> <binary>.bak`
2. **Verify with dry-run** — check offsets via `otool -tV` before writing
3. **Test one patch at a time** — compound patches make debugging difficult
4. **Check for checksums** — some apps hash their binary; patching will trigger anti-tamper
5. **Document every patch** with VM address, file offset, original bytes, and new bytes
6. **Be aware of fat binary layout** — wrong slice offset = corrupt binary
