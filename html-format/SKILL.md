---
name: html-format
description: >
  HTML 代码格式化。USE WHEN 用户说 格式化html、美化html、html格式化、单行html转多行、
  format html、prettify html、minified html、html 代码太长了、html 一行看不清楚。
  自动识别文件类型（web-clone JSON 包装 / SingleFile / 普通 minified / DOM 序列化），
  选择最优策略格式化。
metadata:
  version: "2.1.0"
  use_case: 格式化任何单行/压缩的 HTML 文件，并抽离内联 base64 图片/字体
---

# HTML Format · HTML 格式化

把单行/压缩/带包装的 HTML 变成缩进清晰、可读的多行 HTML。
额外能力：**自动把 HTML 内联的 base64 图片/字体抽离为独立文件**
（`images/` 与 `fonts/` 子目录），并把 HTML 中的 `data:` URI 替换为
相对路径引用，从而大幅减小 HTML 体积、便于版本管理与复用。

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

## base64 资源抽离（v2.1.0 新增）

格式化完成后，脚本会自动扫描所有 HTML 中的内联 `data:...;base64,` 资源并抽离：

- **图片** → `images/` 子目录（扩展名按 MIME 推断：png/jpg/webp/ico/svg/gif/avif/bmp/tif…）
- **字体** → `fonts/` 子目录（woff2/woff/ttf/otf/sfnt…）
- HTML 内的 `data:` URI 被替换为相对路径（如 `images/01_0001.png`）
- 按内容 `sha256` 在同一目录内**去重**（相同资源只存一份）
- 序号从目录内已有文件的最大序号**续接**，可安全重复运行、不覆盖已有资源
- 没有任何内联 base64 的文件会被直接跳过，不额外写盘

> 说明：未加引号的属性（如 `<link rel=icon href=data:...>`）也能正确抽取，
> 正则已规避把后续属性（`sizes=`/`rel=`）误吞为 base64 的历史问题。

## 依赖

- Python 3（标准库，base64 抽离无需第三方库）
- Node.js + prettier（Type A/C/D 格式化需要，npx 自动下载）
