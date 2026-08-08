---
name: html-format
description: >
  HTML 代码格式化。USE WHEN 用户说 格式化html、美化html、html格式化、单行html转多行、
  format html、prettify html、minified html、html 代码太长了、html 一行看不清楚。
  自动识别文件类型（web-clone JSON 包装 / SingleFile / 普通 minified / DOM 序列化），
  选择最优策略格式化。
metadata:
  version: "2.4.2"
  use_case: 格式化任何单行/压缩的 HTML 文件，并抽离内联 base64 图片/字体（语义命名）与内联 <style> CSS（独立 .css 文件，默认 css/ 子目录）
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
- HTML 内的 `data:` URI 被替换为相对路径
- 按内容 `sha256` 在同一目录内**去重**（相同资源只存一份）
- 序号从目录内已有文件的最大序号**续接**，可安全重复运行、不覆盖已有资源
- 没有任何内联 base64 的文件会被直接跳过，不额外写盘

### 文件名：默认按上下文语义命名（v2.2.0）

抽取出的文件名**默认根据上下文含义生成**，而非随机/无意义序号。脚本按以下
优先级从资源所在位置推断命名线索：

1. `<img alt="...">` 的 **alt 文本**（最贴近图片含义，支持中文）
2. 元素的 **id** 属性
3. 元素的 **class** 属性（取第一个 class 词）
4. `<link rel="...">` 的 **rel** → 固定可读名：`icon`→`favicon`、`apple-touch-icon`→`apple-touch-icon`、`mask-icon`→`mask-icon`
5. 位于 `<style>` 内 `background-image: url(data:...)` 时，取 **CSS 选择器**（如 `.hero-banner`）
6. `@font-face` 块内的字体，取 **font-family + font-weight/style**
   （如 `noto-sans-tc-100.woff2`，而不是无信息量的 `font-face.woff2`）

推断不到时回退为 `源文件前缀_序号`（如 `01_0003.png`）。同目录内同名不同内容
自动追加 `-2`/`-3` 后缀。示例输出：
`favicon.ico`、`apple-touch-icon.png`、`网站主logo.png`、`avatar-img.png`、
`hero-banner.webp`、`noto-sans-tc-100-3.woff2`。

> 想退回纯序号命名（确定性、便于复现旧输出），加 `--sequential`：
> `python3 format.py --sequential .`

> 说明：未加引号的属性（如 `<link rel=icon href=data:...>`）也能正确抽取，
> 正则已规避把后续属性（`sizes=`/`rel=`）误吞为 base64 的历史问题。

## 内联 CSS 抽离（v2.4.0 新增，默认开启）

默认**抽取**（base64 抽离仍是默认主流程）。加 `--extract-css` 同样显式开启；
如需关闭可加 `--no-extract-css`。开启时，会在
base64 抽离之后，把 HTML 内联的 `<style>` 样式抽成独立 `.css` 文件，并在原处
插入 `<link rel="stylesheet" href="...">` 引用，从而让 HTML 进一步瘦身、样式
便于复用。在 yuurewards SingleClone 三文件上实测：HTML 由 600KB 缩到 ~42KB
（↓93%），跨文件去重后再净省 ~159KB。

关键设计（均已在真实 SingleFile 页面验证）：

- **srcdoc 安全**：`<iframe srcdoc="...">` 属性值里内嵌的 `<style>` 属于 iframe
  自身文档，绝不当作当前页面样式抽出（否则会破坏 iframe 渲染）。扫描时跳过
  srcdoc 覆盖区间。
- **跳过运行时 CSS**：带 `data-emotion` / `data-styled` 等属性的 `<style>`（常由
  JS 注入/替换）保留原位不抽，避免破坏交互。
- **跨文件去重**：每个块内容按 sha256 计算；出现在多个文件的共享块只写一份
  `shared-<sha12>.css`，被各 HTML 以 `<link>` 引用。仅当前文件独有的块写成
  `<stem>-<n>.css`。
- **路径零风险**：默认 `.css` 写到 **`css/` 子目录**，并自动把 css 内
  `url(images|fonts)` 改写为 `../images/`、`../fonts/`（已验证改写后路径真实可达）；
  若用 `--css-dir .` 则退回与 HTML 同级（`url` 原样有效），`--css-dir <其他>` 可指定
  任意子目录名。
- **顺序保持**：按原文档顺序生成 `<link>`，CSS 层叠顺序不变。
- 块内若含 `url(data:image/svg+xml,...)`（URL 编码的内联 SVG）会原样保留在
  `.css` 中，不受影响。

```bash
python3 format.py .                              # 默认抽到 css/ 子目录
python3 format.py --no-extract-css .             # 关闭内联 CSS 抽离
python3 format.py --css-dir . .                  # 退回与 HTML 同级的 .css
python3 format.py --no-css-dedup .               # 关闭跨文件去重，每块独立成文件
```

## prettier 的定位方式（v2.3.0）

Type A/C/D 需要 prettier。脚本**不再直接调用 `npx prettier`**——npx 每次都会
向 registry 解析最新版本，本机缓存里即使已有 prettier 也会因版本号不同重新下载，
离线/弱网时会长时间挂起甚至被系统杀掉，导致格式化整体失败。

改为按以下顺序探测（`--version` 能跑通即采用）：

1. 环境变量 `PRETTIER_BIN`（显式指定，优先级最高）
2. 当前目录 `node_modules/.bin/prettier`（项目本地依赖）
3. `PATH` 上的全局 `prettier`
4. npx 缓存中已下载的 prettier（`~/.npm/_npx/*/node_modules/prettier`，离线可用）
5. `npx --yes prettier`（联网下载，最后兜底）

运行时会打印实际使用的 prettier 路径。全部不可用时会给出明确提示，并自动
回退到纯 Python 结构化格式化（不会中断，只是排版略粗）。

## 依赖

- Python 3（标准库，base64 抽离/语义命名无需第三方库）
- Node.js + prettier（仅 Type A/C/D 需要；按上述顺序定位，离线也能用缓存版本）
