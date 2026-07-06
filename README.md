# AI Skills

跨平台 AI 编程助手技能库，一套脚本 + 多工具入口。

支持 **Claude Code** · **Codex (OpenAI)** · 后续扩展更多工具。

## 目录结构

```
ai-skills/
├── README.md
├── html-format/              # HTML 单行格式化（原创）
│   ├── SKILL.md              # Claude Code 入口
│   ├── codex.md              # Codex 入口
│   └── format.py             # 核心脚本
├── web-clone/                # 网站复刻（来源见下）
│   ├── SKILL.md              # Claude Code 入口
│   ├── codex.md              # Codex 入口
│   ├── scripts/              # Node.js 辅助脚本
│   └── references/           # 参考文档
└── (更多 skills...)
```

核心原则：**脚本即真相** — 每个 skill 的核心逻辑放在独立脚本中，AI 工具的入口文件只负责调用脚本，不重复实现逻辑。

## 已收录 Skills

### html-format

单行/压缩 HTML 格式化，自动识别 4 种格式类型并选择最优策略。

```bash
python3 html-format/format.py .
```

### web-clone

网站复刻/克隆方法论。覆盖静态站、React/Vue/Next 内容站、WebGL/Canvas 重前端站三大分支。

> 📌 来源：https://github.com/Jane-xiaoer/claude-skill-web-clone （已获授权，MIT License）

## 安装方式

### Claude Code

```bash
# 符号链接（推荐，可同步更新）
ln -s $(pwd)/html-format ~/.claude/skills/html-format
ln -s $(pwd)/web-clone ~/.claude/skills/web-clone
```

### Codex (OpenAI)

```bash
mkdir -p <你的项目>/.codex/commands/
cp html-format/codex.md <你的项目>/.codex/commands/html-format.md
cp web-clone/codex.md <你的项目>/.codex/commands/web-clone.md
```

## 开发新 Skill

1. 在 `ai-skills/` 下创建新目录 `my-skill/`
2. 编写核心脚本 `my-skill/script.py`（或 js/mjs）
3. 创建 Claude Code 入口 `my-skill/SKILL.md`（含 YAML frontmatter）
4. 创建 Codex 入口 `my-skill/codex.md`
5. 更新本 README 的技能列表

## License

MIT
