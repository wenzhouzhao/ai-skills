# AI Skills

跨平台 AI 编程助手技能库，一套脚本 + 多工具入口。

支持 **Claude Code** · **Codex (OpenAI)** · 后续扩展更多工具。

## 目录结构

```
ai-skills/
├── README.md
├── html-format/            # HTML 单行格式化
│   ├── SKILL.md            # Claude Code 入口
│   ├── codex.md            # Codex 入口
│   └── format.py           # 核心脚本（共享）
└── (更多 skills...)
```

核心原则：**脚本即真相** — 每个 skill 的核心逻辑放在独立脚本中，AI 工具的入口文件只负责调用脚本，不重复实现逻辑。

## 已收录 Skills

### html-format

单行/压缩 HTML 格式化，自动识别 4 种格式类型并选择最优策略：

| 类型 | 特征 | 策略 |
|------|------|------|
| A | web-clone JSON 包装 | 提取 → prettier |
| B | SingleFile (base64 内联) | Python 结构化换行 |
| C | 普通 minified HTML | prettier |
| D | DOM 序列化 (void 标签错误) | 修复 → prettier |

```bash
python3 html-format/format.py .
```

## 安装方式

### Claude Code

将 skill 目录复制或链接到 Claude Code 的 skills 目录：

```bash
# 方式一：复制
cp -r html-format ~/.claude/skills/

# 方式二：符号链接（推荐，可同步更新）
ln -s $(pwd)/html-format ~/.claude/skills/html-format
```

然后输入 `/html-format` 或 "格式化 html" 即可触发。

### Codex (OpenAI)

将 `codex.md` 复制到项目的 `.codex/commands/` 目录：

```bash
mkdir -p <你的项目>/.codex/commands/
cp html-format/codex.md <你的项目>/.codex/commands/html-format.md
```

使用时在 Codex 中输入 `/html-format`。

## 开发新 Skill

1. 在 `ai-skills/` 下创建新目录 `my-skill/`
2. 编写核心脚本 `my-skill/script.py`
3. 创建 Claude Code 入口 `my-skill/SKILL.md`（含 YAML frontmatter）
4. 创建 Codex 入口 `my-skill/codex.md`
5. 更新本 README 的技能列表

入口文件模板：

```markdown
# Claude Code: SKILL.md
---
name: my-skill
description: 简短描述。USE WHEN 用户说 xxx。
---
# Skill Name
...
```bash
python3 <本skill目录>/script.py <参数>
```
```

## License

MIT
