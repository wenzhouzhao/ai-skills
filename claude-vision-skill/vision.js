#!/usr/bin/env node
/**
 * 独立识图脚本 — 支持多个多模态大模型，自动选举 + 故障转移。
 *
 * 核心能力:
 *   1. 多 provider: 在 providers.json（或旧版 .env 单配置）里列出所有可用视觉模型。
 *   2. 智能选举: 每次运行根据各 provider 的历史「成功率」与「平均耗时」算出一个
 *      权重分，优先选用又快又稳的；并带 epsilon 探索，避免永远不试次优者。
 *   3. 故障转移: 选举出的首选若失败（429 限流 / 401 鉴权失败 / 网络错等），
 *      自动按顺序尝试下一个，直到成功或全部失败。
 *   4. 在线学习: 每次调用的成功/失败与耗时写入 .vision_stats.json，随使用越选越准。
 *
 * 用法:
 *   node vision.js <图片路径> [问题]
 *   node vision.js --url <图片链接> [问题]
 *   node vision.js --clipboard [问题]
 *   node vision.js --provider zhipu "<图>" "描述这张图"   # 强制指定 provider
 *   node vision.js --list                                 # 列出所有 provider
 *   node vision.js --stats                                # 打印选举统计表
 *   node vision.js --reset-stats                          # 清空统计
 *
 * 配置:
 *   - 多 provider 模式: 同目录 providers.json（优先）
 *   - 单 provider 模式: 环境变量 或 同目录 .env（向后兼容 VISION_ 与 DASHSCOPE_ 前缀）
 *   - 无第三方依赖（内置 .env / providers.json 解析，无需 dotenv）
 */

const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");
const os = require("os");
const { execFileSync } = require("child_process");

// ---- 选举算法参数（可在此调参） ----
const ELECTION = {
  alpha: 1.0, // 成功率权重（越大越看重稳定）
  beta: 0.7, // 速度权重（越大越看重快）
  refLatency: 30000, // 参考延迟(ms)：达到该耗时速度分=0.5
  epsilon: 0.15, // 探索概率：每次以该概率打乱顺序，避免冷落次优 provider
  maxLatencySamples: 20, // 每个 provider 保留最近 N 次耗时用于平均
  publicUrlBoost: 1.6, // 当输入是公网图片 URL 时，对"仅支持公开 URL"的 provider 加权，使其优先被选中
  timeoutMs: 120000, // 单次请求超时(ms)，超时视为失败并自动故障转移
};

const STATS_FILE = path.join(__dirname, ".vision_stats.json");

// ---- 配置加载（无需 dotenv，自动读取 .env / providers.json） ----
function loadEnv() {
  for (const dir of [process.cwd(), __dirname]) {
    const f = path.join(dir, ".env");
    if (!fs.existsSync(f)) continue;
    try {
      const txt = fs.readFileSync(f, "utf8");
      for (const line of txt.split(/\r?\n/)) {
        const m = line.match(/^\s*([\w.-]+)\s*=\s*(.*)\s*$/);
        if (!m || m[1] in process.env) continue;
        let val = m[2];
        if (
          (val.startsWith('"') && val.endsWith('"')) ||
          (val.startsWith("'") && val.endsWith("'"))
        ) {
          val = val.slice(1, -1);
        }
        process.env[m[1]] = val;
      }
    } catch {}
  }
}
loadEnv();
// 兼容 dotenv（若已安装）
try { require("dotenv").config(); } catch {}
try { require("dotenv").config({ path: path.join(__dirname, ".env") }); } catch {}

/**
 * 读取 provider 列表。
 * - 优先 providers.json（多 provider 模式）
 * - 否则由 .env 的 VISION_ 与 DASHSCOPE_ 前缀构造单个 provider（向后兼容）
 */
function loadProviders() {
  const pj = path.join(__dirname, "providers.json");
  if (fs.existsSync(pj)) {
    try {
      const cfg = JSON.parse(fs.readFileSync(pj, "utf8"));
      const list = (cfg.providers || []).map((p) => ({
        name: p.name || "unnamed",
        apiKey: p.apiKey || "",
        model: p.model || "",
        baseUrl: p.baseUrl || "https://api.openai.com/v1",
        localImage: p.localImage !== false, // 默认支持本地 base64 图
      }));
      if (list.length) return list;
      console.error("providers.json 为空，回退到 .env 单配置。");
    } catch (e) {
      console.error("providers.json 解析失败:", e.message, "回退到 .env 单配置。");
    }
  }
  // 单 provider 模式（旧行为）
  const baseUrl =
    process.env.VISION_BASE_URL ||
    process.env.DASHSCOPE_BASE_URL ||
    "https://open.bigmodel.cn/api/paas/v4";
  const apiKey =
    process.env.VISION_API_KEY ||
    process.env.DASHSCOPE_API_KEY ||
    "YOUR_API_KEY_HERE";
  const model = process.env.VISION_MODEL || "glm-4.6v-flash";
  return [
    { name: "default", apiKey, model, baseUrl, localImage: true },
  ];
}

function maskKey(k) {
  if (!k || k.length < 8) return "***";
  return k.slice(0, 4) + "…" + k.slice(-4);
}
// 判断 provider 是否已配置有效 Key（占位符 YOUR_API_KEY_HERE 视为未配置）
function hasKey(p) {
  return !!p.apiKey && p.apiKey !== "YOUR_API_KEY_HERE";
}

// ---- 统计读写（同步，降低并发竞争窗口） ----
function loadStats() {
  try {
    return JSON.parse(fs.readFileSync(STATS_FILE, "utf8"));
  } catch {
    return {};
  }
}
function saveStats(stats) {
  try {
    fs.writeFileSync(STATS_FILE, JSON.stringify(stats, null, 2));
  } catch {}
}
function recordResult(stats, name, ok, latencyMs) {
  const s = stats[name] || { success: 0, fail: 0, latencies: [] };
  if (ok) {
    s.success += 1;
    s.latencies = s.latencies.concat(latencyMs).slice(-ELECTION.maxLatencySamples);
  } else {
    s.fail += 1;
  }
  stats[name] = s;
}

// ---- 选举 ----
function avgLatency(s) {
  if (!s.latencies || !s.latencies.length) return null;
  return s.latencies.reduce((a, b) => a + b, 0) / s.latencies.length;
}
function scoreOf(stats, name) {
  const s = stats[name] || { success: 0, fail: 0, latencies: [] };
  const sr = (s.success + 1) / (s.success + s.fail + 2); // Laplace 平滑，冷启动=0.5
  const avg = avgLatency(s);
  const speed = avg == null ? 1 : 1 / (1 + avg / ELECTION.refLatency);
  return Math.pow(sr, ELECTION.alpha) * Math.pow(speed, ELECTION.beta);
}
function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
/**
 * 返回本次尝试的 provider 顺序（已排除能力不匹配者）。
 * inputIsLocal=true 时，localImage=false 的 provider 会被跳过（如 Agnes 仅支持公开 URL）。
 */
function electOrder(stats, providers, inputIsLocal, forceName) {
  if (forceName) {
    const p = providers.find((x) => x.name === forceName);
    if (!p) {
      console.error(`未找到 provider: ${forceName}。可用:`, providers.map((x) => x.name).join(", "));
      process.exit(1);
    }
    if (inputIsLocal && p.localImage === false) {
      console.error(`provider ${forceName} 不支持本地图片（仅限公开 URL），但当前输入是本地文件。`);
      process.exit(1);
    }
    return [p];
  }
  const usable = providers.filter(
    (p) => !(inputIsLocal && p.localImage === false),
  );
  const skipped = providers.length - usable.length;
  if (skipped) {
    console.error(`（跳过 ${skipped} 个不支持本地图片的 provider）`);
  }
  // 过滤掉未配置 Key 的 provider，避免白打一次 401 才转移
  const candidates = usable.filter(hasKey);
  if (!candidates.length) {
    console.error("没有已配置 API Key 的可用 provider（请先在 providers.json / .env 填入 Key）。");
    process.exit(1);
  }
  let order;
  const isPublicUrl = !inputIsLocal; // 输入是公网图片 URL（非本地文件/剪贴板）
  // 公网 URL 场景下，对"仅支持公开 URL"的 provider 加权，使其优先被选中
  const effScore = (p) =>
    scoreOf(stats, p.name) * (isPublicUrl && p.localImage === false ? ELECTION.publicUrlBoost : 1);
  // 公网 URL 输入时不做随机探索，保证 URL 原生 provider 稳定优先（满足"公网图优先选中"诉求）
  const explore = !isPublicUrl && Math.random() < ELECTION.epsilon;
  if (explore) {
    order = shuffle(usable); // 探索：随机打乱
  } else {
    order = candidates.slice().sort(
      (a, b) => effScore(b) - effScore(a) || a.name.localeCompare(b.name),
    );
  }
  if (isPublicUrl) {
    console.error("（公网图片 URL 输入：优先选 URL 原生 provider）");
  }
  return order;
}

// ---- 参数解析（保留旧 flags） ----
function parseArgs() {
  const argv = process.argv.slice(2);
  let imageSource = "", prompt = "", isUrl = false, useClipboard = false, noFallback = false;
  let forceProvider = null, listOnly = false, statsOnly = false, resetStats = false;

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--clipboard") {
      useClipboard = true;
    } else if (a === "--no-fallback") {
      noFallback = true;
    } else if (a === "--list") {
      listOnly = true;
    } else if (a === "--stats") {
      statsOnly = true;
    } else if (a === "--reset-stats") {
      resetStats = true;
    } else if (a === "--provider" && argv[i + 1]) {
      forceProvider = argv[++i];
    } else if (a === "--url" && argv[i + 1]) {
      isUrl = true;
      imageSource = argv[++i];
    } else if (a && !a.startsWith("--") && useClipboard && !prompt) {
      prompt = a;
    } else if (a && !a.startsWith("--") && !imageSource) {
      imageSource = a;
    } else if (a && !a.startsWith("--") && imageSource && !prompt) {
      prompt = a;
    }
  }
  if (/^https?:\/\//i.test(imageSource)) isUrl = true;
  if (!prompt) prompt = "请详细描述这张图片的内容。";
  return { imageSource, prompt, isUrl, useClipboard, noFallback, forceProvider, listOnly, statsOnly, resetStats };
}

function getClipboardReader() {
  if (process.platform === "darwin") {
    return (outPath) => {
      execFileSync("/usr/bin/swift", [path.join(__dirname, "clipboard.swift"), outPath], { stdio: "pipe" });
      return outPath;
    };
  }
  if (process.platform === "win32") {
    return (outPath) => {
      execFileSync(
        "powershell",
        ["-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass", "-File", path.join(__dirname, "clipboard.ps1"), "-OutFile", outPath],
        { stdio: "pipe", windowsHide: true },
      );
      return outPath;
    };
  }
  return null;
}
function readClipboardImage() {
  const reader = getClipboardReader();
  if (!reader) throw new Error(`剪贴板读取暂不支持当前平台: ${process.platform}（目前支持 macOS / Windows）`);
  const outPath = path.join(os.tmpdir(), `vision-clipboard-${Date.now()}.png`);
  return reader(outPath);
}
function resolveImageUrl(source, isUrl) {
  if (isUrl) return source;
  const resolved = path.resolve(source);
  if (!fs.existsSync(resolved)) throw new Error(`文件不存在: ${resolved}`);
  const ext = path.extname(resolved).toLowerCase().replace(".", "");
  const mimeMap = { jpg: "jpeg", jpeg: "jpeg", png: "png", gif: "gif", webp: "webp", bmp: "bmp" };
  const data = fs.readFileSync(resolved);
  return `data:image/${mimeMap[ext] || "jpeg"};base64,${data.toString("base64")}`;
}
function buildRequestUrl(base) {
  const u = (base || "").replace(/\/+$/, "");
  if (/chat\/completions$/i.test(u)) return u;
  return u + "/chat/completions";
}

function request(provider, payload) {
  const url = new URL(buildRequestUrl(provider.baseUrl));
  const body = JSON.stringify(payload);
  const transport = url.protocol === "https:" ? https : http;
  const timeoutMs = parseInt(process.env.VISION_TIMEOUT_MS || String(ELECTION.timeoutMs), 10) || ELECTION.timeoutMs;

  return new Promise((resolve, reject) => {
    const req = transport.request(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${provider.apiKey}`,
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
    }, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        clearTimeout(timer);
        if (res.statusCode >= 400) return reject(new Error(`API ${res.statusCode}: ${data.slice(0, 300)}`));
        try {
          resolve(JSON.parse(data)?.choices?.[0]?.message?.content || data);
        } catch { resolve(data); }
      });
    });
    const timer = setTimeout(() => {
      req.destroy(new Error(`请求超时（${timeoutMs}ms），已自动故障转移`));
    }, timeoutMs);
    req.on("error", (err) => { clearTimeout(timer); reject(err); });
    req.write(body);
    req.end();
  });
}

function printStats(providers) {
  const stats = loadStats();
  console.error("\n=== 选举统计（成功率 / 平均耗时 / 评分）===");
  const rows = providers.map((p) => {
    const s = stats[p.name] || { success: 0, fail: 0, latencies: [] };
    const total = s.success + s.fail;
    const sr = total ? ((s.success / total) * 100).toFixed(0) + "%" : "—";
    const avg = avgLatency(s);
    const lat = avg == null ? "—" : (avg / 1000).toFixed(1) + "s";
    return { name: p.name, sr, lat, score: scoreOf(stats, p.name).toFixed(3) };
  });
  rows.sort((a, b) => parseFloat(b.score) - parseFloat(a.score));
  for (const r of rows) {
    console.error(`  ${r.name.padEnd(10)} 成功率 ${r.sr.padStart(4)}  平均 ${r.lat.padStart(6)}  评分 ${r.score}`);
  }
  console.error("=========================================\n");
}

// 宿主模型已支持原生视觉时，可由以下方式显式关闭本 skill，避免多余的识图调用：
//   1. 环境变量 VISION_SKIP=1 / true
//   2. providers.json 顶层 "enabled": false
function isSkillDisabled() {
  if (/^(1|true|yes)$/i.test(process.env.VISION_SKIP || "")) return true;
  const pj = path.join(__dirname, "providers.json");
  if (fs.existsSync(pj)) {
    try {
      const cfg = JSON.parse(fs.readFileSync(pj, "utf8"));
      if (cfg.enabled === false) return true;
    } catch {}
  }
  return false;
}

async function main() {
  const providers = loadProviders();
  const args = parseArgs();

  if (args.resetStats) {
    saveStats({});
    console.error("已清空选举统计。");
    return;
  }
  if (args.listOnly) {
    console.error("可用 provider:");
    for (const p of providers) {
      console.error(`  - ${p.name}  (model=${p.model}, localImage=${p.localImage})  key=${maskKey(p.apiKey)}`);
    }
    return;
  }
  if (args.statsOnly) {
    printStats(providers);
    return;
  }
  // 模型本身已多模态：跳过本 skill（--list/--stats 等只读调试命令不受此限制）
  if (isSkillDisabled()) {
    console.error(
      "SKIPPED: 宿主模型已支持原生视觉（VISION_SKIP=1 或 providers.json enabled=false）。" +
      "请勿调用本 skill，直接用模型自身能力识图。",
    );
    return;
  }

  const { imageSource, prompt, isUrl, useClipboard, noFallback, forceProvider } = args;

  // 校验强制指定的 provider 配置完整
  if (forceProvider) {
    const p = providers.find((x) => x.name === forceProvider);
    if (!p) {
      console.error(`未找到 provider: ${forceProvider}`);
      process.exit(1);
    }
    if (!p.apiKey || p.apiKey === "YOUR_API_KEY_HERE") {
      console.error(`provider ${forceProvider} 未配置 API Key。`);
      process.exit(1);
    }
  } else if (!providers.some(hasKey)) {
    console.error("请至少配置一个 provider 的 API Key（providers.json 或 .env）。");
    process.exit(1);
  }

  let source = imageSource;
  const tryClipboard = () => {
    try {
      source = readClipboardImage();
      console.error("（未提供可用图片路径，已自动回退读取系统剪贴板）");
      return true;
    } catch (err) {
      console.error("剪贴板读取失败:", err.message);
      return false;
    }
  };
  const showUsage = () => {
    console.error("用法: node vision.js <图片路径> [问题]");
    console.error("      node vision.js --url <图片链接> [问题]");
    console.error("      node vision.js --clipboard [问题]");
  };

  if (useClipboard) {
    if (imageSource || isUrl) {
      console.error("--clipboard 不能和图片路径或 --url 同时使用。");
      process.exit(1);
    }
    if (!tryClipboard()) process.exit(1);
  } else if (source && !isUrl) {
    const resolved = path.resolve(source);
    if (!fs.existsSync(resolved)) {
      if (noFallback) { console.error(`文件不存在: ${resolved}`); process.exit(1); }
      if (!tryClipboard()) process.exit(1);
    }
  } else if (!source) {
    if (noFallback) { showUsage(); process.exit(1); }
    if (!tryClipboard()) process.exit(1);
  }
  if (!source) { showUsage(); process.exit(1); }

  const inputIsLocal = !isUrl; // 剪贴板图也落地为本地文件(base64)
  const imageUrl = resolveImageUrl(source, isUrl);
  const stats = loadStats();
  const order = electOrder(stats, providers, inputIsLocal, forceProvider);
  const maxTokens = parseInt(process.env.VISION_MAX_TOKENS || "1024", 10);

  console.error(`尝试顺序: ${order.map((p) => p.name).join(" → ")}`);

  let lastErr = null;
  for (const p of order) {
    const t0 = Date.now();
    try {
      const result = await request(p, {
        model: p.model,
        messages: [{ role: "user", content: [
          { type: "image_url", image_url: { url: imageUrl } },
          { type: "text", text: prompt },
        ]}],
        stream: false,
        max_tokens: maxTokens,
      });
      const dt = Date.now() - t0;
      recordResult(stats, p.name, true, dt);
      saveStats(stats);
      console.error(`✓ 使用 ${p.name}（耗时 ${(dt / 1000).toFixed(1)}s，key=${maskKey(p.apiKey)}）`);
      console.log(result);
      return;
    } catch (err) {
      const dt = Date.now() - t0;
      recordResult(stats, p.name, false, dt);
      lastErr = err;
      const msg = err.message || err.code || "网络错误";
      console.error(`✗ ${p.name} 失败（${(dt / 1000).toFixed(1)}s）: ${msg.slice(0, 120)}`);
    }
  }
  saveStats(stats);
  console.error("所有 provider 均失败。最后错误:", lastErr ? lastErr.message : "未知");
  process.exit(1);
}

main();
