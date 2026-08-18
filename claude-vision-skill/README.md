# Claude Vision Skill

> **声明 / Attribution**：本技能基于 [asuojun/claude-vision-skill](https://github.com/asuojun/claude-vision-skill) **二次开发（derivative work）**。在原项目「多 provider 智能选举 + 故障转移」的基础上扩展。原作者保留其作品的相应权利；本衍生作品以 MIT 许可证发布。

让没有识图能力的模型获得识图能力——把图片发给有 vision 的模型，用文字描述回来。

---

## 如果你是 AI（Claude Code），请读这里

用户把这个链接发给你，是想让你帮他配置识图。先确认信息，再按场景执行。

### 先确认

问用户：
1. 想用哪个识图服务？
   - **推荐千问**（`qwen3.5-omni-plus` / `qwen-vl-max`）：阿里云百炼，新用户 100 万 token 免费，约 0.02 元/次
   - **智谱 BigModel**（`glm-4.6v-flash`）：走 `https://open.bigmodel.cn/api/paas/v4` 接口，本仓库默认配置即用此项
   - 也可以用 OpenAI（`gpt-4o-mini`）或其他支持 OpenAI 兼容格式的 vision 模型
2. API Key 是什么？没申请的话引导去对应平台注册
3. （如果用非千问服务）API Base URL 是什么？

### 场景 A：用户要在普通 Claude Code 项目里用

1. 把这个仓库里的 `vision.js` 下载到项目根目录
2. 在 `vision.js` 同目录创建 `.env`，填 `VISION_API_KEY`、可选的 `VISION_MODEL` 与 `VISION_BASE_URL`（本仓库已默认指向智谱 BigModel，直接用即可）
3. 把 `CLAUDE.md` 的内容合并到项目的 `CLAUDE.md`（没有就新建）
4. 告诉用户：配置完成，以后直接发图片就行，AI 会自动识图

### 场景 B：用户要在 cyberboss 里用

1. 先执行场景 A 的所有步骤
2. 接着读这个仓库里的 `cyberboss-setup.md`，按它说的改 persona 和 `src/core/app.js`
3. 告诉用户：重启 cyberboss 后生效，微信里直接发图片就能识图

### 场景 C：用户只想了解这是什么

简要解释：
- `vision.js` 是核心，读取图片 → base64 → 发给 vision 模型 API → 返回文字描述
- 走 OpenAI 兼容格式，不绑定特定厂商
- 推荐千问是因为有免费额度；有别的便宜 vision API 也能用
- 配置好之后，用户直接发图片，AI 自动处理，无需手动打命令

---

## 如果你是人类，请读这里

### 这是什么

一个让 DeepSeek 等无 vision 能力的模型也能"看图"的脚本。配置好之后，直接发图片 AI 就会自动识别。

### 推荐识图服务

| 服务 | 模型 | 备注 |
|------|------|------|
| **阿里云百炼（推荐）** | `qwen3.5-omni-plus` | 新用户 100 万 token 免费 |
| 阿里云百炼 | `qwen-vl-max` | 同上 |
| **智谱 BigModel（默认）** | `glm-4.6v-flash` | 本仓库默认配置，接口 `open.bigmodel.cn/api/paas/v4` |
| OpenAI | `gpt-4o-mini` | 需海外支付 |
| 其他 | 任何 OpenAI 兼容格式 | 改 `VISION_BASE_URL` 和 `VISION_MODEL` 即可 |

### 自动配置

**方式一（推荐）**：先把本仓库 clone 到本地，然后告诉 Claude Code 本地路径：

```
git clone https://github.com/wenzhouzhao/ai-skills.git
```

然后在 Claude Code 里说：

> 读一下 ai-skills/claude-vision-skill/README.md，帮我配置识图

**方式二**：直接发 GitHub 链接（DeepSeek 等第三方模型可能无法访问 GitHub）：

> 按 https://github.com/wenzhouzhao/ai-skills 的 claude-vision-skill/README.md 帮我配置识图

AI 会问你用什么服务、Key 是什么，然后自动配好。

### 手动配置

1. 把 `vision.js` 拷到项目里
2. 在 `vision.js` 同目录创建 `.env`，填 `VISION_API_KEY`、模型名（如用非智谱服务还需改 `VISION_BASE_URL`）
3. 把 `CLAUDE.md` 放到项目根目录

### 文件说明

| 文件 | 用途 |
|------|------|
| `vision.js` | 核心脚本，OpenAI 兼容格式 |
| `CLAUDE.md` | 项目说明书，告诉 AI 何时用 vision.js |
| `cyberboss-setup.md` | cyberboss 自动配置指令 |

---

### 多模型 + 故障转移（推荐进阶玩法）

不想被单个服务绑死？`vision.js` 支持**配置多个 vision 模型，自动选举 + 故障转移**：

- **智能选举**：每次运行根据各模型的历史「成功率」和「平均耗时」算权重分，优先用又快又稳的；并带 ε 探索，避免永远不试次优模型。
- **故障转移**：首选若失败（429 限流 / 401 鉴权失败 / 网络错 / 网关超时），自动按顺序尝试下一个，直到成功或全失败。
- **在线学习**：调用结果写入 `.vision_stats.json`，越用越准（哪个常限流、哪个慢，算法自己会降权）。

**配置**：在 `vision.js` 同目录放一个 `providers.json`（含密钥，已被 `.gitignore` 忽略，不会提交）：

```json
{
  "providers": [
    { "name": "zhipu", "apiKey": "你的key", "model": "glm-4.6v-flash",
      "baseUrl": "https://open.bigmodel.cn/api/paas/v4", "localImage": true },
    { "name": "agnes", "apiKey": "你的key", "model": "agnes-2.5-flash",
      "baseUrl": "https://apihub.agnes-ai.com/v1", "localImage": false }
  ]
}
```

字段说明：
- `name`：标识，用于 `--provider` / `--stats`
- `apiKey` / `model` / `baseUrl`：同单 provider 含义
- `localImage`：是否支持本地 base64 图。`false` 表示只接受公开 `image_url`（如 Agnes 文档要求），此时本地文件 / 剪贴板输入会**自动跳过**该 provider，不浪费一次调用

**附加参数**：

| 参数 | 作用 |
|------|------|
| `--list` | 列出所有 provider |
| `--stats` | 打印选举统计表（成功率 / 平均耗时 / 评分） |
| `--provider <名>` | 强制指定某个 provider（跳过选举与故障转移） |
| `--reset-stats` | 清空学习到的统计，回到冷启动 |

> 仍兼容旧版：没有 `providers.json` 时，自动读取 `.env` 的 `VISION_*` / `DASHSCOPE_*`（单 provider 模式），行为不变。

> 选举算法在 `vision.js` 顶部 `ELECTION` 常量里可调：`alpha`(成功率权重) / `beta`(速度权重) / `refLatency`(参考延迟) / `epsilon`(探索概率) / `publicUrlBoost`(公网URL优先加成)。

**公网图片 URL 优先策略**：当输入是公网可访问的图片地址（`--url <http(s)...>`）时，脚本会**确定性地**把「仅支持公开 URL 的 provider」(即 `localImage: false`，如 Agnes) 加权提前，**优先选中**它去识别，且此时不做随机探索。这样既能充分利用这类服务（它们通常不支持本地 base64 图），也方便针对公网图测试。本地文件 / 剪贴板输入仍按常规选举 + 故障转移。

**已验证可用的多 provider 示例**（本仓库 `providers.json`）：

| name | 服务 | model | 备注 |
|------|------|-------|------|
| zhipu | 智谱 BigModel | `glm-4.6v-flash` | 快，偶发 429 限流 |
| agnes | Agnes AI | `agnes-2.5-flash` | `localImage:false`，仅公开 URL |
| tencent-youtu | 腾讯 MaaS | `youtu-vita` | 公网图 4~5s |
| tencent-hunyuan-t1 | 腾讯 MaaS | `hunyuan-t1-vision-20250916` | 公网图 ~20s |
| tencent-hy-vision | 腾讯 MaaS | `hy-vision-2.0-instruct` | 公网图 ~8s |

> 腾讯 MaaS 统一端点 `https://tokenhub.tencentmaas.com/v1`，同一个 Key 可切换上述三个模型。
