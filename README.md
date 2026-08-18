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
├── ishot-security-audit/     # iShot 付费水印安全审计
│   ├── SKILL.md              # Claude Code 入口
│   ├── codex.md              # Codex 入口
│   ├── ishot_security_tester.py  # 核心攻击脚本
│   └── references/           # 审计报告
├── macos-app-security-audit/ # 通用 macOS 应用安全审计方法论
│   ├── SKILL.md              # Claude Code 入口
│   ├── codex.md              # Codex 入口
│   ├── scripts/              # 辅助脚本（信息收集）
│   └── references/           # 参考文档（攻击面分类、二进制 patch 速查、报告模板）
├── claude-vision-skill/      # 多模态大模型识图（图片→文字），多 provider 智能选举 + 故障转移
│   ├── SKILL.md              # Claude Code 入口
│   ├── vision.js             # 核心脚本（OpenAI 兼容 vision API）
│   ├── providers.example.json  # 多 provider 配置范例（无密钥）
│   ├── .env.example          # 单 provider 配置范例（无密钥）
│   └── README.md             # 详细文档
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

### ishot-security-audit

iShot 付费水印安全审计与绕过复现。ARM64 二进制 CBZ→B patch 攻击、Plist 篡改分析、重签名与权限重置。

```bash
sudo python3 ishot-security-audit/ishot_security_tester.py auto
```

### macos-app-security-audit

通用 macOS 应用安全审计方法论（playbook 型 skill）。覆盖信息收集、攻击面映射、ARM64 二进制 patch、dylib 注入、网络重放、Keychain 操纵、时间篡改、重签名等完整攻击面，含标准化漏洞报告模板。不绑定任何具体应用。

```bash
bash macos-app-security-audit/scripts/macos_recon.sh /path/to/Target.app
```

### claude-vision-skill

让没有识图能力的模型获得识图能力——把图片发给有 vision 的模型，用文字描述回来。支持多 provider 智能选举（按历史成功率 + 平均耗时）+ 故障转移；公网图片 URL 输入时，优先选中「仅支持公开 URL」的 provider。

```bash
node claude-vision-skill/vision.js "<图片路径>" "描述这张图"
# 或公网图片：
node claude-vision-skill/vision.js --url "https://example.com/img.png" "描述这张图"
```

> 📌 基于 https://github.com/asuojun/claude-vision-skill 二次开发（已新增多模型选举、故障转移、公网 URL 优先）

## 安装方式

### Claude Code

```bash
# 符号链接（推荐，可同步更新）
ln -s $(pwd)/html-format ~/.claude/skills/html-format
ln -s $(pwd)/web-clone ~/.claude/skills/web-clone
ln -s $(pwd)/ishot-security-audit ~/.claude/skills/ishot-security-audit
ln -s $(pwd)/macos-app-security-audit ~/.claude/skills/macos-app-security-audit
ln -s $(pwd)/claude-vision-skill ~/.claude/skills/claude-vision-skill
```

### Codex (OpenAI)

```bash
mkdir -p <你的项目>/.codex/commands/
cp html-format/codex.md <你的项目>/.codex/commands/html-format.md
cp web-clone/codex.md <你的项目>/.codex/commands/web-clone.md
cp ishot-security-audit/codex.md <你的项目>/.codex/commands/ishot-security-audit.md
cp macos-app-security-audit/codex.md <你的项目>/.codex/commands/macos-app-security-audit.md
# claude-vision-skill 暂无 Codex 入口（仅提供 SKILL.md / vision.js）
```

## 开发新 Skill

1. 在 `ai-skills/` 下创建新目录 `my-skill/`
2. 编写核心脚本 `my-skill/script.py`（或 js/mjs）
3. 创建 Claude Code 入口 `my-skill/SKILL.md`（含 YAML frontmatter）
4. 创建 Codex 入口 `my-skill/codex.md`
5. 更新本 README 的技能列表

## License

MIT
