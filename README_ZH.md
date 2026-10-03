<div align="center">

# 🛡️ SYNAPSE SHIELD (突触之盾)

### 下一代开源行为生物识别与反爬虫/机器人防御引擎

**以隐私为先、零摩擦感知、自托管的 Cloudflare Turnstile 替代方案。**

🌐 **[ English ](README.md)** | **[ 简体中文 ](README_ZH.md)**

[![PyPI](https://img.shields.io/pypi/v/synapse-shield?color=00F0FF&label=pypi)](https://pypi.org/project/synapse-shield/)
[![License: MIT](https://img.shields.io/badge/License-MIT-00F0FF.svg)](https://opensource.org/licenses/MIT)
[![CI/CD](https://github.com/0xStoic-bit/Synapse_Shield/actions/workflows/ci.yml/badge.svg)](https://github.com/0xStoic-bit/Synapse_Shield/actions)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg?logo=python)](https://python.org)
[![Inference SLA](https://img.shields.io/badge/Latency-%3C0.5ms-10B981.svg)]()
[![Zero-PII](https://img.shields.io/badge/Privacy-100%25%20Zero--PII-success.svg)]()

<br/>

[核心特性](#-核心特性与安全架构-v092) • [系统架构](#-系统架构与时序图) • [快速上手](#-30秒快速上手) • [开发者接入](#-开发者接入指南) • [基准测试](#-对抗攻击仿真基准测试) • [数学理论](#-运动学与数学理论基础) • [媒体报道](#-媒体与社区报道-featured-on)

</div>

---

## ⚡ 概述 (Overview)

**Synapse Shield** 彻底告别了干扰用户体验的传统验证码（CAPTCHA，如九宫格选图、旋转拼图）以及昂贵的专有云 WAF，采用**亚毫秒级行为生物力学分析（Sub-millisecond Behavioral Biomechanics）**构建安全护盾。

通过精准评估人体神经肌肉的自然微颤（**加加速度 / Jerk: $\frac{da}{dt}$**）、基于菲茨定律（Fitts's Law）的终端减速模型、光标轨迹微分曲率 $\kappa(t)$ 以及毫秒级击键动力学（Keystroke Dynamics），Synapse Shield 能够在自动化爬虫、刷票脚本、撞库机器人与 LLM 自动化 Agent **触及后端业务逻辑前，毫秒内完成自主识别与无感拦截**。

---

## ✨ 核心特性与安全架构 (v0.9.2)

| 核心特性 | 功能与技术解析 |
| :--- | :--- |
| 📐 **微分曲率分析 ($\kappa(t)$ - 贝塞尔与 AI 机器人猎手)** | 利用微分几何计算轨迹一阶和二阶导数 $\kappa(t) = \frac{\|\dot{x}\ddot{y} - \dot{y}\ddot{x}\|}{(\dot{x}^2 + \dot{y}^2 + \epsilon)^{3/2}}$，通过 Rust AVX2 SIMD 高速识别平滑度异常的贝塞尔曲线（Bézier）与人工高斯抖动机器人 (v0.9.2)。 |
| ⌨️ **击键动力学与双字母组香农熵** | 深度分析按键保持时间（Dwell Time $T_d$）、按键间距飞逝时间（Flight Time $T_f$）以及高频双字母组合（Digraphs），结合 8-bin 直方图香农熵分析，阻击固定延时的机器人击键注入 (v0.9.2)。 |
| ⚡ **PyO3 零拷贝缓冲区 (Zero-Copy Buffer)** | Python 端的 NumPy `float64` 连续数组直接通过指针裸传递至 Rust 底层 SIMD 寄存器，规避跨语言内存复制损耗，实现微秒级极端性能 (v0.9.2)。 |
| 📱 **移动端电容触控生物力学** | 模拟多点触控形变物理学：追踪 `maxTouchPoints`、平均触控半径 ($\bar{r} \ge 3.0\text{ px}$)、形变方差 ($\sigma_r^2 > 0$) 与按压力度。真人手指触控享有 -15 风险补偿，针对无头移动模拟器施加 +60 风险拦截惩罚 (v0.9.0)。 |
| 🦀 **原生 Rust SIMD 运动学核心** | 通过 PyO3 实现高性能 C-ABI FFI，单趟 AVX2/NEON SIMD 矢量化并行处理 24 维运动学特征（延迟仅 $212.7\,\mu s$，吞吐达 ~4,700 ops/s）(v0.9.0)。 |
| ⚡ **微秒级性能基准套件** | 内置 CLI 命令（`synapse-shield benchmark`），一键评测 19D 运动学抽取 ($73.7\,\mu s$)、1D-CNN 推理 ($451.2\,\mu s$) 及全链路端到端评估 ($828.1\,\mu s$，~1,200 req/s)，支持 ASCII 与 JSON 报告输出 (v0.7.9)。 |
| 🧬 **拟真生物人轨迹生成引擎** | 基于菲茨定律的多峰子运动速度分解算法，模拟生理波谷、手臂生物力学弧度及惯性滤波神经肌肉微颤，达到 100% 拟真人验证精度 (v0.7.9)。 |
| 🛡️ **隔离权重与自举校准架构** | 运行期微调保存至本地 `./synapse_weights.npz`（或环境变量 `SYNAPSE_WEIGHTS_PATH`），彻底隔离包分发静态权重。`--bootstrap` 选项支持在全新环境下进行零样本自校准 (v0.7.9)。 |
| 🌊 **FFT 微颤频谱分析 (DSP 频域检测)** | 运用快速傅里叶变换（`np.fft.rfft`）分解速度序列，计算功率谱密度（PSD）中的频谱纯度（`spectral_purity`）与频谱熵，从频域上精准捕获合成谐波振荡微颤（$\sin(2\pi ft)$）(v0.7.8)。 |
| 🖐️ **子运动学分解 (Sub-Movement Decomposition)** | 将鼠标移动路径拆解为离散的弹道脉冲和末端修正脉冲。缺乏生理子运动（`submovement_count <= 1`）的多项式平滑轨迹将被标记为机器人 (v0.7.8)。 |
| 🔄 **会话级行为不变性检测 (Behavioral Invariance)** | 滑动窗口时序遥测追踪。防御使用固定随机数种子（Random Seed）或在会话中重复使用确定性运动模板的高级攻击者 (v0.7.8)。 |
| 🎯 **对抗性 AI 重训练流水线** | 内置对抗遥测生成器（`synapse_shield.adversarial`），以生成贝塞尔、正弦波、最小急动度（Flash & Hogan Minimum Jerk）曲线主动扩充 1D-CNN 训练集，消除分布外盲区 (v0.7.8)。 |
| 🛡️ **全面安全加固体系** | 彻底覆盖全攻击面防御：防存储型 XSS、带管理鉴权的 WebSocket 终端、Webhook 防 SSRF 与 DNS Rebinding 白名单，以及针对 Brave 浏览器 Farbling 机制的误报抑制 (v0.7.7)。 |
| ⚡ **亚毫秒级复合 SQLite 索引** | 采用复合索引（`idx_ip_strikes_ip_ts`）消除全表扫描，在高并发高负载 DDoS 流量下保持亚毫秒级拦截计数 (v0.7.7)。 |
| 🔄 **透明 Token 过期自动恢复** | 严格区分正常过期 Token（`HTTP 400 EXPIRED`）与恶意重放攻击，使客户端 SDK 能平滑重新协商挑战，避免正常用户因网络延迟被误封 IP (v0.7.7)。 |
| 🧱 **O(N) 复杂度击键 DoS 防御** | 采用队列化保持时间分析并实施严格输入边界约束（最多 150 次按键/滚动），化解算法复杂度耗竭攻击 (v0.7.7)。 |
| 🧪 **防投毒 AI 微调过滤** | 遥测数据摄取过滤器自动剔除被拦截流量或触发指纹偏斜的数据，保障主动学习数据集纯净度，维持模型高准确率 (v0.7.7)。 |
| 🔔 **Discord & Telegram 实时 Webhook 告警** | 毫秒级安全事件告警。当发生严重威胁拦截（BLOCK）或触发 IP 封锁时，通过非阻塞后台协程自动推送到指定频道 (v0.7.6)。 |
| ⚡ **分布式状态与 Redis 集群支持** | 企业级多机多节点架构支持（配置 `SYNAPSE_REDIS_URL`）。实现原子级跨节点防重放（`SET NX EX`）、同步 IP 隔离名单及自动降级至本地 SQLite (v0.7.5)。 |
| 🧩 **动态非阻塞客户端工作量证明 (PoW)** | 客户端秒级完成 SHA-256 密码学谜题计算，配备 UI 线程出让（Yielding）机制，绝不卡顿前端主界面，支持重试防重放 (v0.7.2)。 |
| 🛡️ **基于隐藏 Iframe 的原生原型解钩** | 高级反指纹伪装机制：通过创建隐藏沙箱 iframe 读取未被污染的原生浏览器原型（Canvas, WebGL），绕过攻击者的全局 Hook 伪造 (v0.7.2)。 |
| 🔒 **SDK 运行期对象冻结 (Immutability)** | 关键逻辑均经过 `Object.freeze` 保护，防止目标页面恶意脚本或 XSS 篡改内部状态 (v0.7.2)。 |
| 📱 **零卡顿移动端事件监听** | 全面使用被动触摸监听器（`{ passive: true }`），确保移动端 60 FPS 丝滑滚动体验 (v0.7.2)。 |
| 🪟 **滑动时间窗口 IP 封锁盾** | 60秒有状态滑动时间窗机制（阻击 SSRT-2026-004 绕过漏洞）。防止攻击者在连续违规后通过插入单次合法请求重置计数器。 |
| 🔄 **纯 NumPy 主动微调学习** | 提供内置 `synapse-shield retrain` 命令，直接从本地 SQLite 遥测日志在 3 秒内对 1D-CNN 全连接层完成迁移训练，无需笨重的 PyTorch/TensorFlow 运行环境。 |
| 🕵️ **反自动化隐身伪装检测** | 动态捕获无头浏览器特征（如 `navigator.webdriver` 属性覆盖）、伪造插件列表检测，以及针对 WebGL/Canvas API 原生 `toString` 的篡改检测。 |
| 🗄️ **自动化持续学习采集器** | 提供现成的 `store.html` 前端遥测采集组件（接入 `/api/collect_dataset`），以便在实际业务中持续收集真实真人行为数据。 |
| 🤖 **轻量级纯 NumPy 1D-CNN 微型大脑** | 序列分词器将运动学和键盘统计特征压缩为 8D 和 5D 张量结构，由 15KB 的纯 NumPy 1D-CNN 网络全权推理（无臃肿框架依赖）。 |
| 🛡️ **极值门控 (Max Gating 决策融合引擎)** | 动态统一启发式数学物理规则与 1D-CNN 的 AI 置信度评分。一旦任一引擎判定为机器行为，请求将无条件执行熔断拦截。 |
| 🔗 **零外部依赖的多模态分词器** | 采用晚期融合（Late Fusion）架构，将 5D 鼠标时序序列 `[dx, dy, dt, velocity, jerk]` 与 8D 静态击键/滚动特征深度融合。 |
| 🧩 **100% 全透明无感交互** | 没有任何令人反感的找红绿灯、选自行车、拼拼图或听音频任务。正常人类用户实现完全无感验证。 |
| ⚡ **异步非阻塞极低延迟 (<0.5 ms)** | 密集的 CPU 运动学特征提取交由 `asyncio.to_thread` 执行，在高并发流量下绝不阻塞主事件循环。 |
| 🔐 **密码学级防重放攻击保护** | 每一个验证会话均与单次签名的 **HMAC-SHA256** Nonce 强绑定。网络层截获的 Token 无法被第二次重放。 |
| 🧠 **菲茨定律减速运动学** | 通过分析光标在点击前的末端减速特征，精准拆穿贝塞尔平滑光标模拟工具（如 `ghost-cursor`）的人工伪装。 |
| ⚛️ **官方 React, Next.js & Vue 3 / Nuxt 3 支持** | 官方封装库（`synapse-shield-react` 与 `synapse-shield-vue`），提供专属 Hooks/Composables 与开箱即用的 `<SynapseProtect />` 组件。 |
| 🐍 **主流 Python Web 框架原生适配** | 提供针对 **FastAPI**、**Django**（`SynapseShieldMiddleware`）与 **Flask**（`@shield_protect_flask`）的原生中间件与路由装饰器。 |
| ♿ **无障碍友好模式 (Accessibility)** | 支持无障碍风险平滑适配（`accessibility_mode=True`），避免运动障碍人士或辅助设备使用者遭遇误拦截。 |
| 📈 **企业级 Prometheus 监控指标** | 内置 `/metrics` 端点，支持通过 `PROMETHEUS_MULTIPROC_DIR` 在 Gunicorn/Uvicorn 多进程集群下统一汇聚延迟与拦截率。 |
| 🔒 **100% 零隐私侵犯 (Zero-PII)** | 严格遵循隐私保护原则：绝不采集按键明文或表单输入内容，仅提取毫秒级相对时间戳差值（完全合规 GDPR 与数据安全规范）。 |
| 📊 **统计学泊松洪水攻击识别** | 采用泊松分布异常评估算法（Poisson Anomaly Detection），瞬时定位高频无头 API 洪水并实施动态 IP 惩罚。 |
| 💾 **SQLite WAL 机制与自动精简** | 内存级 TTL Nonce 缓存管理 + 启用 WAL 预写式日志（10秒忙等待超时），彻底杜绝异步后台任务中的数据库读写锁死。 |
| 🧱 **内存耗竭 DoS 防御** | 在数据流读取阶段（`await request.body()`）执行严密的 256KB/512KB 体积限制，免疫分块传输通胀 DoS 攻击。 |
| 🔑 **管理操作密码学鉴权** | 清理黑名单等管理操作接口（`/api/clear`）受 `SYNAPSE_ADMIN_SECRET` 密钥加密保护，严禁未授权篡改风控状态。 |

---

## 🏛️ 系统架构与时序图 (Architecture & Sequence Diagram)

```text
┌─────────────────┐             ┌─────────────────────┐             ┌─────────────────────────┐
│  客户端浏览器    │             │  FastAPI 网关服务   │             │  运动学与决策推理引擎   │
│  (synapse-sdk)  │             │  (Synapse Shield)   │             │  (SLA < 0.5ms)          │
└────────┬────────┘             └──────────┬──────────┘             └────────────┬────────────┘
         │                                 │                                     │
         │── 1. GET /api/challenge ───────►│                                     │
         │◄── 2. { nonce, ts, hmac_sig } ──│  (签发单次有效加密 Nonce)           │
         │                                 │                                     │
   [用户移动鼠标 / 击键]                   │                                     │
   [SDK 采样 50Hz 行为遥测数据]            │                                     │
         │                                 │                                     │
         │── 3. POST /api/score {token} ──►│  (1. 验证 HMAC-SHA256 签名)         │
         │                                 │  (2. 校验 60秒 TTL 时效性)          │
         │                                 │  (3. 校验 Nonce 防重放攻击)          │
         │                                 │                                     │
         │                                 │── 4. asyncio.to_thread ────────────►│ (24D 运动学抽取)
         │                                 │                                     │ (Jerk & 菲茨定律)
         │                                 │                                     │ (微分曲率 κ(t))
         │                                 │                                     │ (1D-CNN AI 推理)
         │                                 │                                     │ (泊松异常频次)
         │                                 │◄── 5. (bot_score, ALLOW/BLOCK) ─────│
         │                                 │                                     │
         │                                 │── 6. 异步写入 SQLite WAL 日志       │
         │◄── 7. HTTP 200 {ALLOW/BLOCK} ───│                                     │
```

---

## 🚀 30秒快速上手 (Quickstart)

### 方式 1：通过 PyPI 安装运行

```bash
pip install synapse-shield
```

直接从终端启动防御服务及 3D 实时监控驾驶舱（Cockpit）：

```bash
synapse-shield run --port 8000
```

执行 7 大攻击维度的全自动红队对抗安全测试：

```bash
synapse-shield test
```

基于本地 SQLite 累积的真实遥测数据自主重训练 1D-CNN AI 模型（主动学习）：

```bash
synapse-shield retrain --epochs 5 --lr 0.01
```

---

### 方式 2：克隆源码与本地开发

```bash
git clone https://github.com/0xStoic-bit/Synapse_Shield.git
cd Synapse_Shield
pip install -e .
python test_suite.py
```

在浏览器中访问 [http://127.0.0.1:8000](http://127.0.0.1:8000/) 即可打开**实时可视化安全驾驶舱（Live Security Cockpit）**。

---

### 方式 3：Docker 一键部署（推荐生产环境使用）

一行命令容器化运行完整的 Synapse Shield 协议栈，内置预配置的 SQLite WAL 持久卷与静态遥测收集服务：

```bash
# 后台静默启动容器
docker-compose up -d

# 实时查看访问日志与拦截记录
docker-compose logs -f
```

服务就绪后，Synapse API 及驾驶舱界面将在 [http://localhost:8000](http://localhost:8000) 开放访问。

---

## 🚨 实时 Webhook 告警 (Telegram & Discord)

Synapse Shield 配备零延迟后台 Webhook 告警通道。当拦截到高危自动化行为（如 `STEALTH_AUTOMATION` 隐身工具、`POISSON_FLOOD` 洪水攻击或频繁撞库）时，系统会第一时间向管理员手机推送通知。

### 配置 Telegram 告警
1. 打开 Telegram，私聊 **[@BotFather](https://t.me/BotFather)** 输入 `/newbot`。
2. 按照提示生成你的专属 **HTTP API Token**（如 `123456:ABC-DEF...`）。
3. 向你新建的机器人随意发送一条消息（如 "Hello"）以完成会话激活。
4. 私聊 **[@userinfobot](https://t.me/userinfobot)** 并点击 `START`，获取你的 **Chat ID**（如 `123456789`）。
5. 登录 Synapse Shield 驾驶舱后台（`http://127.0.0.1:8000`），点击 **WEBHOOKS** 标签页，填入 Token 与 Chat ID 即可完成绑定。

### 配置 Discord 告警
1. 进入你的 Discord 服务器设置 > **整合 (Integrations)** > **Webhooks** > **创建 Webhook**。
2. 复制生成的 **Webhook URL**。
3. 打开 Synapse Shield 驾驶舱后台，点击 **WEBHOOKS**，粘贴该 URL 并保存生效。

---

## 💻 开发者接入指南 (Developer Integration)

### 1. FastAPI 接入

可使用 `@shield_protect` 装饰器对单个端点进行细粒度防御，或使用全局中间件保护特定路径：

```python
from fastapi import FastAPI, Request
from synapse_shield import shield_protect, SynapseShieldMiddleware

app = FastAPI()

# 全局路径中间件防护
app.add_middleware(SynapseShieldMiddleware, protected_paths=["/api/auth"])

# 细粒度接口级防护
@app.post("/api/login")
@shield_protect(max_risk_score=50.0, accessibility_mode=False)
async def login(request: Request):
    return {"status": "authenticated"}
```

---

### 2. Django & Flask 接入

**Django (`settings.py`)**:

```python
MIDDLEWARE = [
    # ...
    'synapse_shield.django.SynapseShieldMiddleware',
]
SYNAPSE_SHIELD_PROTECTED_PATHS = ['/api/login']
SYNAPSE_SHIELD_MAX_RISK = 50.0
SYNAPSE_SHIELD_ACCESSIBILITY = False
```

**Flask**:

```python
from flask import Flask
from synapse_shield.flask import shield_protect_flask

app = Flask(__name__)

@app.route("/login", methods=["POST"])
@shield_protect_flask(max_risk_score=50.0)
def login():
    return {"status": "authenticated"}
```

---

### 3. React / Next.js 接入

安装专属 npm 包，支持 App Router (`"use client"`)：

```tsx
import { useSynapseShield, SynapseProtect } from 'synapse-shield-react';

export default function LoginForm() {
  const { getProtectedPayload } = useSynapseShield();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = getProtectedPayload();
    // 携带 payload.token 发起登录请求至业务后端
    await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: payload.token, username, password })
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <SynapseProtect />
      <button type="submit">登录</button>
    </form>
  );
}
```

---

### 4. Vue 3 / Nuxt 3 接入

官方封装的 Vue 3 Composable 及组件（`synapse-shield-vue`），完全兼容 Nuxt 3 SSR：

```vue
<script setup>
import { ref } from 'vue';
import { useSynapseShield, SynapseProtect } from 'synapse-shield-vue';

const { getProtectedPayload } = useSynapseShield();
const username = ref('');
const password = ref('');

const handleSubmit = async () => {
  const payload = getProtectedPayload();
  // 提交 payload.token 至后端
  await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: payload.token, username: username.value, password: password.value })
  });
};
</script>

<template>
  <form @submit.prevent="handleSubmit">
    <SynapseProtect />
    <input v-model="username" type="text" placeholder="用户名" />
    <input v-model="password" type="password" placeholder="密码" />
    <button type="submit">登录</button>
  </form>
</template>
```

---

### 5. 原生 JavaScript / HTML 接入

在传统静态页面或前后端不分离项目中引入超轻量级 SDK（`<5 KB`）：

```html
<script src="http://localhost:8000/static/synapse-sdk.js"></script>
<script>
  SynapseShield.init();
  
  async function handleLogin() {
    const payload = SynapseShield.getPayload();
    // 将 payload.token 附带在登录或提交请求中
  }
</script>
```

---

### 6. Prometheus 企业级可观测性

开箱即用的监控指标支持。服务通过 `/metrics` 端点自动暴露拦截率、平均推理延时及异常分布。在 Gunicorn/Uvicorn 多进程生产环境下，指定目录即可聚合：

```bash
export PROMETHEUS_MULTIPROC_DIR=/tmp/synapse_metrics
```

---

## 🤖 对抗攻击仿真基准测试 (Attack Simulation Benchmarks)

随时在控制台运行完整的红蓝对抗仿真基准套件：

```bash
synapse-shield test
```

| 攻击向量 (Attack Vector) | 模拟行为特征 (Simulated Signature) | 核心识别与拦截机制 | 风控裁决 | 风险评分 | 处理延迟 |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Selenium 爬虫脚本** | `navigator.webdriver = true` | WebDriver 原型与环境变量篡改嗅探 | 🔴 **BLOCK** | **100.0%** | **0.01 ms** |
| **直线型机器人 (Linear)** | 直线度 Straightness = 1.000，Jerk = 0 | 直线度超标阈值及无生理抖动特征 | 🔴 **BLOCK** | **100.0%** | **0.18 ms** |
| **贝塞尔平滑隐形脚本** | 数学拟合的平滑加减速轨迹 | 菲茨定律减速失真 + 差异化曲率方差极低 | 🔴 **BLOCK** | **90.0%** | **0.22 ms** |
| **机械打字注入脚本** | 固定时间间隔（如 50ms）按键注入 | 击键时差方差 $\text{Var}(T_f) < 1.0\text{ ms}^2$ | 🔴 **BLOCK** | **85.0%** | **0.15 ms** |
| **泊松洪水并发注入** | 500 毫秒内发起 8+ 次快速请求 | 泊松累积分布概率超限 ($P > 99\%$) | 🔴 **BLOCK** | **60.0%** | **0.08 ms** |
| **重放攻击 (Replay Attack)** | 窃取已使用的合法验证 Token 重发 | 单次加密 Nonce 数据库原子失效机制 | 🔴 **BLOCK** | **100.0%** | **0.05 ms** |
| **真人自然操作** | 包含生理加加速度与末端减速的有机曲线 | 符合生物动力学 Jerk 与菲茨定律分布 | 🟢 **ALLOW** | **0.0%** | **0.24 ms** |

---

## 🧠 运动学与数学理论基础 (Mathematical Foundations)

### 1. 加加速度 (Jerk) — 神经肌肉微颤指纹

$$\text{Jerk} = \frac{da}{dt} = \frac{d^3x}{dt^3}$$

人类手部肌群由于中枢神经系统的反馈调节，在进行光标定位时会不可避免地产生 8–12 Hz 的生理微颤（Jerk 呈现连续的高频波动）。而由计算机数学模型生成的路径（直线插值、三次多项式插值）其 Jerk 往往近似恒为零或呈阶跃式突变。

---

### 2. 菲茨定律末端减速指数 (Fitts's Law Deceleration)

$$\text{Terminal Decel Ratio} = \frac{\bar{v}_{\text{terminal (末端 25\%)}}}{v_{\text{peak}}}$$

人类大脑在控制手部接近预定点击目标时，会遵循菲茨定律产生反射性的减速修正动作（减速比通常 $< 0.40$）。缺乏末端制动的恒速或平滑匀速脚本会立刻暴露其人工合成属性。

---

### 3. 微分曲率分析 ($\kappa(t)$)

$$\kappa(t) = \frac{|\dot{x}\ddot{y} - \dot{y}\ddot{x}|}{(\dot{x}^2 + \dot{y}^2 + \epsilon)^{3/2}}$$

用于揭示数学贝塞尔曲线的微观几何缺陷。人手的自然动作会形成多段弹道子运动，其曲率变化率的方差 $\text{Var}(\dot{\kappa})$ 保持在合理生理区间；而单纯调用贝塞尔算法的爬虫脚本，其曲率变化率方差呈现病态平滑（$\text{Var}(\dot{\kappa}) < 10^{-8}$）。

---

### 4. 累积泊松反常概率分布 (Poisson Anomaly)

$$P(X < k) = \sum_{i=0}^{k-1} \frac{\lambda^i e^{-\lambda}}{i!}$$

用于刻画单位时间窗口内请求到达频次的统计学异常，智能过滤批量并发的撞库工具。

---

## 🌐 媒体与社区报道 (Featured On)

Synapse Shield 受到了全球安全与前沿技术社区的关注与技术剖析：

| 平台 / 来源 | 深度文章 / 报道链接 | 核心内容 |
| :--- | :--- | :--- |
| **Mfuns (二次元与前沿科技社区)** | [Synapse Shield 架构深度解析与安全加固 (v0.5.0)](https://www.mfuns.net/article/123158#%E4%B8%BB%E8%A6%81%E7%89%B9%E6%80%A7%E4%B8%8E%E5%8A%A0%E5%9B%BA-v0-5-0) | 深入解析行为生物识别原理、无感反爬虫架构、零知识隐私机制及系统安全加固策略 |

---

## 📁 仓库目录结构 (Repository Structure)

```text
Synapse_Shield/
├── .github/
│   └── workflows/
│       └── ci.yml             # 自动化 CI 测试矩阵 (Python 3.10, 3.11, 3.12)
├── crates/                    # 原生 Rust 高性能底层模块
│   └── synapse_core_rs/       # PyO3 + AVX2 SIMD 运动学核心扩展
│       ├── Cargo.toml
│       ├── benches/           # Criterion 微秒级性能基准测试
│       └── src/
│           ├── curvature.rs   # 微分曲率 κ(t) 矢量化计算
│           ├── keystrokes.rs  # 击键动力学与香农熵
│           ├── kinematics.rs  # 24维运动学指标抽取
│           └── lib.rs         # PyO3 FFI 导出层
├── src/
│   └── synapse_shield/
│       ├── __init__.py        # 顶层对外 API 导出
│       ├── cli.py             # CLI 命令行入口 (run / test / benchmark / retrain)
│       ├── engine.py          # 实时决策与泊松异常引擎 (Max Gating)
│       ├── features.py        # 运动学特征提取、菲茨定律与多模态分词
│       ├── models.py          # 纯 NumPy 1D-CNN 推理引擎 (零重型依赖)
│       ├── weights.npz        # 序列化的紧凑神经网络权重
│       ├── main.py            # 异步 FastAPI 网关与 SQLite WAL 记录器
│       ├── middleware.py      # @shield_protect 装饰器与中间件
│       ├── django.py          # Django 框架专用中间件适配器
│       ├── flask.py           # Flask 框架专用路由装饰器
│       ├── metrics.py         # Prometheus 企业级多进程导出器
│       ├── tokens.py          # HMAC-SHA256 挑战生成与防重放核心
│       ├── train.py           # 纯 NumPy 本地主动学习微调流水线
│       ├── adversarial.py     # 对抗性拟真人类/机器人时序生成器
│       └── static/            # 3D 监控驾驶舱与客户端 SDK
│           ├── index.html
│           └── synapse-sdk.js
├── synapse-shield-react/      # React / Next.js SDK 官方组件包
│   ├── src/
│   │   ├── SynapseProtect.tsx # "use client" 无感防护组件
│   │   ├── useSynapseShield.ts# React Hook 事件节流采样逻辑
│   │   └── index.ts
│   ├── package.json
│   └── tsconfig.json
├── synapse-shield-vue/        # Vue 3 / Nuxt 3 SDK 官方组件包
│   ├── src/
│   │   ├── SynapseProtect.vue # Vue 3 / Nuxt 3 专属无感防护组件
│   │   └── useSynapseShield.ts# Vue 3 Composable
├── tests/                     # Pytest 模块化测试套件 (91/91 测试全通过)
│   ├── test_features.py
│   ├── test_tokens.py
│   ├── test_engine.py
│   ├── test_rust_core.py
│   └── test_v092_curvature_keystrokes.py
├── pyproject.toml             # PEP 517/621 包分发规范定义
├── requirements.txt           # 核心依赖清单
├── LICENSE                    # MIT 开源许可证
├── README.md                  # 英文官方文档
└── README_ZH.md               # 简体中文官方文档
```

---

## 📜 开源协议 (License)

本项目基于 [MIT 许可证](https://opensource.org/licenses/MIT) 开源。欢迎自由用于商业项目与个人项目。
