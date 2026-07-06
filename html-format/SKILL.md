---
name: html-format
description: >
  HTML 代码格式化。USE WHEN 用户说 格式化html、美化html、html格式化、单行html转多行、
  format html、prettify html、minified html、html 代码太长了、html 一行看不清楚。
  自动识别文件类型（web-clone JSON 包装 / SingleFile / 普通 minified / DOM 序列化），
  选择最优策略格式化。
metadata:
  version: "2.0.0"
  use_case: 格式化任何单行/压缩的 HTML 文件
---

# HTML Format · HTML 格式化

把单行/压缩/带包装的 HTML 变成缩进清晰、可读的多行 HTML。

## 使用方式

```bash
cd <目标目录> && python3 <本skill目录>/format.py .
```

或者指定具体文件：

```bash
python3 <本skill目录>/format.py a.html b.html
```

## 自动识别的 4 种类型

| 类型 | 特征 | 策略 |
|------|------|------|
| A | `Script ran on page` 头 (web-clone 产物) | JSON提取 → void修复 → prettier |
| B | `SingleFile` 头 (大量 base64 内联) | Python 结构化换行 |
| C | 普通单行 HTML | prettier |
| D | `<meta></meta>` 自闭合错误 | void修复 → prettier |

## 依赖

- Python 3（标准库）
- Node.js + prettier（Type A/C/D 需要，npx 自动下载）
