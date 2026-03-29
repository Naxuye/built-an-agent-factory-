# Naxuye Agent Factory

> 🚧 **Alpha - Under Active Development**

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>

## English

Naxuye is a **LangGraph-based AI Agent factory**. Describe what you want in natural language — the factory handles requirement analysis, architecture design, code generation, quality audit, smoke testing, and deployment registration automatically. The output is a standalone, runnable Python agent.

All registered agents are managed through **Nomos**, a Telegram Bot-based agent manager that supports remote invocation, health monitoring, and hot reloading.

<img width="950" height="947" alt="image" src="https://github.com/user-attachments/assets/ec92efb0-9ec7-4329-b469-018e9ec9fe75" />
<img width="950" height="947" alt="image" src="https://github.com/user-attachments/assets/90f800e3-571d-428d-babf-4776d3f1f31d" />

### Features

- **Natural Language Driven** — Describe your need in one sentence, the factory understands, decomposes, and builds it
- **Multi-LLM Collaboration** — Supports DeepSeek, Alibaba Cloud Qwen, Zhipu GLM with automatic failover
- **Triple Quality Gate** — PostChecker static analysis → LLM deep audit → Sandbox smoke test
- **Batch Production** — Large agents are split into batches; failed components are automatically reworked
- **Skills System** — 5 built-in skills (http_request, llm_call, web_scraper, file_io, json_parser) that generated agents can call directly, eliminating third-party dependency issues
- **Error Memory** — SQLite-based error pattern database; the factory learns from past mistakes and injects lessons into future builds
- **Template Engine** — 5 specialized code templates (api_integration, data_processing, llm_call, main, tool) for different agent types
- **Telegram Manager (Nomos)** — Produce agents, invoke them, check status, hot-reload — all from your phone
- **Process Isolation** — Each agent runs in an independent sandbox with timeout and memory limits

### Architecture

```
naxuye-agent/
├── .env                              # Environment variables (API keys)
├── main.py                           # Factory CLI entry point
├── langgraph_workflow.py              # LangGraph graph orchestration
├── workflow_state.py                  # Global state definition
├── workflow_nodes.py                  # Node wrapper functions
│
├── commander/                         # Command layer
│   ├── intent_parser.py               # Intent parsing
│   ├── planner.py                     # Strategic decomposition
│   ├── reviewer.py                    # LLM code audit
│   ├── post_checker.py                # Static analysis (AST + regex)
│   ├── smoke_test.py                  # Smoke test (import + health + run)
│   ├── mindset.py                     # Signing, archiving, Nomos registration
│   ├── logic_core_extractor.py        # Code polishing
│   ├── api_router.py                  # Multi-LLM smart routing
│   └── smart_client.py               # Auto proxy/direct connection
│
├── pillow/                            # Production layer
│   └── agent_builder.py               # LLM code generation engine
│
├── scout/                             # Intelligence layer
│   └── intelligence_fetcher.py        # Tavily search + LLM intelligence distillation
│
├── skills/                            # Built-in skill library
│   ├── __init__.py                    # Auto-discovery & registry
│   ├── manifest.json                  # Skill manifest for Planner
│   ├── http_request.py                # HTTP requests with retry
│   ├── llm_call.py                    # Multi-provider LLM calls
│   ├── web_scraper.py                 # Web scraping & extraction
│   ├── file_io.py                     # File read/write with safety checks
│   └── json_parser.py                 # Fault-tolerant JSON parsing
│
├── templates/                         # Code templates
│   ├── agent_template.py              # Base skeleton (fallback)
│   ├── template_api_integration.py    # API integration template
│   ├── template_data_processing.py    # Data processing template
│   ├── template_llm_call.py           # LLM call template
│   ├── template_main.py              # Multi-component coordinator
│   └── template_tool.py              # Tool/utility template
│
├── configs/                           # Configuration
│   ├── naxuye_config_v26.py           # Power grid (multi-LLM node config)
│   ├── resource_grid.py               # Concurrency & timeout settings
│   └── error_memory.py                # Error pattern database (SQLite)
│
├── Nomos/                             # Agent manager (Telegram Bot)
│   ├── core.py                        # Main process entry
│   ├── broker.py                      # Message relay (Request-Ack-Push)
│   ├── command.py                     # Command definitions
│   ├── registry.py                    # Agent registry
│   ├── sandbox.py                     # Process sandbox (isolation + monitoring)
│   └── telegram.py                    # Telegram Bot interface
│
└── agent_factory/                     # Output directory (auto-generated)
    └── weather_agent_SAFE_xxx/
```

### Factory Pipeline

```
User Input → Intent Parser → Dispatcher → Planner → Scout
                                                       ↓
                                                 Batch Scheduler
                                                       ↓
                                              ┌──→ Pillow (code gen)
                                              │        ↓
                                              │    Reviewer (audit)
                                              │        ↓
                                              │   ┌─ score < 80 ──→ rework (max 6x) ─→ Pillow
                                              │   ├─ next batch ──→ Batch Scheduler
                                              │   ├─ rebuild ────→ Planner
                                              │   └─ all passed ──→ Smoke Test
                                              │                        ↓
                                              │                   ┌─ failed ──→ Pillow
                                              │                   └─ passed ──→ Mindset
                                              │                                   ↓
                                              │                              ┌─ rejected ──→ Planner
                                              │                              └─ approved ──→ Logistic
                                              │                                                ↓
                                              └─ error ──────────────────────────────────→ Planner
                                                                                           ↓
                                                                                          END
```

**Full pipeline:**

1. **Intent Parser** — Clean input, initialize state
2. **Dispatcher** — Select LLM tier based on task complexity
3. **Planner** — Deep requirement analysis, decompose into component list
4. **Scout** — Tavily search + LLM intelligence distillation
5. **Batch Scheduler** — Schedule component production in batches
6. **Pillow** — Concurrent LLM code generation with automatic failover
7. **Reviewer** — PostChecker static analysis + LLM deep audit
8. **Smoke Test** — Verify import / health() / run() in temp sandbox
9. **Mindset** — Manual or auto approval → code polishing → archiving → Nomos registration
10. **Logistic** — Generate delivery manifest, pipeline ends

### Quick Start

#### Prerequisites

- Python 3.11+
- At least one LLM API key (DeepSeek / Alibaba Cloud / Zhipu)

#### Installation

```bash
git clone https://github.com/Naxuye/built-an-agent-factory.git
cd built-an-agent-factory

pip install -r requirements.txt
```

#### Configuration

Create a `.env` file in the project root:

```env
DEEPSEEK_API_KEY=your_key_here
NAXUYE_WORKSPACE=path/to/agent_factory
```

Optional:
```env
ZHIPUAI_API_KEY=your_key
DASHSCOPE_API_KEY=your_key
TAVILY_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

#### Run Factory (CLI mode)

```bash
python main.py
```

Enter your request, e.g.: `Build me a weather query agent`

#### Run Nomos (Telegram manager)

```bash
python -m Nomos.core
```

Telegram Bot commands:

| Command | Description |
|---------|-------------|
| `/factory <request>` | Trigger factory to produce a new agent |
| `/list` | List all registered agents |
| `/start <agent> <params>` | Invoke an agent |
| `/status <agent>` | Check agent health |
| `/stop <agent>` | Stop an agent |
| `/logs <agent>` | View recent logs |
| `/reload <agent>` | Hot-reload (re-produce) |

### Demo

**Produce a translation agent:**

```
/factory Build a Chinese-English translation agent
```

**Invoke:**

```
/start translation_agent {"input": "星星之火，可以燎原"}
```

**Result:**

```json
{
  "status": "success",
  "result": "A spark can start a prairie fire.",
  "timestamp": 1773923583.84
}
```

Video Demo: https://youtube.com/shorts/Lpa1MBS6m68?si=fmGW0e4MDFxk6VL5

### Supported LLM Providers

| Provider | Models | Tier |
|----------|--------|------|
| DeepSeek | deepseek-reasoner, deepseek-chat | STRATEGIC / ENGINEERING / BASE |
| Alibaba Cloud | qwen3-max, qwen3.5-flash | ENGINEERING / BASE |
| Zhipu | glm-4.7, glm-4-plus, glm-4-flash | STRATEGIC / ENGINEERING / BASE |

Automatic round-robin with failover across all tiers.

### Roadmap

- [ ] Multi-component coordination via `main.py` (framework-level orchestration)
- [ ] Auto-inject error_memory rules into generation prompts
- [ ] Agent-to-agent collaboration
- [ ] Parallel production & partial repair
- [ ] Web UI (replace CLI)
- [ ] Docker containerization
- [ ] PostgreSQL (replace SQLite)

### License

[MIT](LICENSE)

### Disclaimer

This project is in early Alpha. The quality of generated agents depends on the underlying LLM's code generation capability. Generated code should be reviewed before production deployment.

---

<a name="中文"></a>

## 中文

Naxuye 是一个基于 LangGraph 的 **AI Agent 自动化工厂**。输入一句自然语言需求，工厂自动完成需求分析、架构拆解、代码生产、质量审计、冒烟测试、归档注册的完整流程，产出可独立运行的 Agent。

通过 Telegram Bot（**Nomos 管家系统**）统一管理所有已注册的 Agent，实现远程调用、状态监控、热更新。

<img width="950" height="947" alt="image" src="https://github.com/user-attachments/assets/ec92efb0-9ec7-4329-b469-018e9ec9fe75" />
<img width="950" height="947" alt="image" src="https://github.com/user-attachments/assets/90f800e3-571d-428d-babf-4776d3f1f31d" />

### 功能特性

- **自然语言驱动** — 一句话描述需求，工厂自动理解、拆解、生产
- **多 LLM 协作** — 支持 DeepSeek、阿里云通义、智谱 GLM，自动容错切换
- **三重质检** — PostChecker 静态校验 → LLM 深度审计 → Sandbox 冒烟测试
- **分批生产** — 大型 Agent 自动拆分批次生产，失败组件自动重工
- **Skills 系统** — 5 个内置技能（http_request、llm_call、web_scraper、file_io、json_parser），生成的 Agent 直接调用，无需处理第三方依赖
- **错误记忆** — 基于 SQLite 的错误模式数据库，工厂从历史错误中学习，将经验注入后续生产
- **模板引擎** — 5 个专用代码模板（api_integration、data_processing、llm_call、main、tool），适配不同 Agent 类型
- **Telegram 管家（Nomos）** — 手机上即可触发生产、调用 Agent、查看状态、热更新
- **进程隔离** — 每个 Agent 在独立沙箱中运行，超时/内存溢出自动 kill

### 项目结构

```
naxuye-agent/
├── .env                              # 环境变量（API keys）
├── main.py                           # 工厂命令行入口
├── langgraph_workflow.py              # LangGraph 图编排
├── workflow_state.py                  # 全局状态定义
├── workflow_nodes.py                  # 节点 wrapper 函数
│
├── commander/                         # 指挥层
│   ├── intent_parser.py               # 意图解析
│   ├── planner.py                     # 战略拆解（需求分析 → 组件设计）
│   ├── reviewer.py                    # LLM 代码审计
│   ├── post_checker.py                # 静态校验（AST + 正则）
│   ├── smoke_test.py                  # 冒烟测试（import + health + run）
│   ├── mindset.py                     # 签署归档 + Nomos 注册
│   ├── logic_core_extractor.py        # 代码抛光
│   ├── api_router.py                  # 多 LLM 智能路由
│   └── smart_client.py               # 国内/海外自动直连/代理
│
├── pillow/                            # 生产层
│   └── agent_builder.py               # LLM 代码生成引擎
│
├── scout/                             # 侦察层
│   └── intelligence_fetcher.py        # Tavily 搜索 + LLM 情报提纯
│
├── skills/                            # 内置技能库
│   ├── __init__.py                    # 自动发现与注册
│   ├── manifest.json                  # Skill 清单（供 Planner 参考）
│   ├── http_request.py                # HTTP 请求（带重试）
│   ├── llm_call.py                    # 多供应商 LLM 调用
│   ├── web_scraper.py                 # 网页抓取与提取
│   ├── file_io.py                     # 文件读写（带安全校验）
│   └── json_parser.py                 # 容错 JSON 解析
│
├── templates/                         # 代码模板
│   ├── agent_template.py              # 基础骨架（兜底）
│   ├── template_api_integration.py    # API 集成模板
│   ├── template_data_processing.py    # 数据处理模板
│   ├── template_llm_call.py           # LLM 调用模板
│   ├── template_main.py              # 多组件协调器
│   └── template_tool.py              # 工具类模板
│
├── configs/                           # 配置层
│   ├── naxuye_config_v26.py           # 算力矩阵（多 LLM 节点配置）
│   ├── resource_grid.py               # 并发信号量 + 超时配置
│   └── error_memory.py                # 错误记忆数据库（SQLite）
│
├── Nomos/                             # 管家系统（Telegram Bot）
│   ├── core.py                        # 主进程入口
│   ├── broker.py                      # 消息中转（Request-Ack-Push）
│   ├── command.py                     # 指令集定义
│   ├── registry.py                    # Agent 注册表管理
│   ├── sandbox.py                     # 进程沙箱（隔离执行 + 资源监控）
│   └── telegram.py                    # Telegram Bot 接入
│
└── agent_factory/                     # 产出目录（自动生成）
    └── weather_agent_SAFE_xxx/
```

### 生产流水线

```
用户需求 → 意图解析 → 调度器 → 规划器 → 侦察兵
                                              ↓
                                         批次调度器
                                              ↓
                                     ┌──→ Pillow（代码生成）
                                     │        ↓
                                     │    Reviewer（审计）
                                     │        ↓
                                     │   ┌─ 得分 < 80 ──→ 重工（最多6次）─→ Pillow
                                     │   ├─ 下一批次 ──→ 批次调度器
                                     │   ├─ 重新规划 ──→ 规划器
                                     │   └─ 全部通过 ──→ 冒烟测试
                                     │                      ↓
                                     │                 ┌─ 失败 ──→ Pillow
                                     │                 └─ 通过 ──→ Mindset（签署）
                                     │                                ↓
                                     │                           ┌─ 拒签 ──→ 规划器
                                     │                           └─ 通过 ──→ Logistic（归档）
                                     │                                         ↓
                                     └─ 归档异常 ────────────────────────→ 规划器
                                                                          ↓
                                                                         END
```

**完整流程：**

1. **Intent Parser** — 清洗输入，初始化状态
2. **Dispatcher** — 根据任务复杂度选择算力等级
3. **Planner** — 深度理解需求，拆解为组件列表，设计架构
4. **Scout** — Tavily 搜索 + LLM 提纯技术情报
5. **Batch Scheduler** — 分批调度组件生产
6. **Pillow** — 并发调用 LLM 生成代码，失败自动切换备用节点
7. **Reviewer** — PostChecker 静态校验 + LLM 深度审计
8. **Smoke Test** — 在临时沙箱中验证 import / health() / run()
9. **Mindset** — 人工或自动签署 → 代码抛光 → 文件归档 → Nomos 注册
10. **Logistic** — 生成交付清单，流程结束

### 快速开始

#### 前置条件

- Python 3.11+
- 至少一个 LLM API key（DeepSeek / 阿里云 / 智谱）

#### 安装

```bash
git clone https://github.com/Naxuye/built-an-agent-factory.git
cd built-an-agent-factory

pip install -r requirements.txt
```

#### 配置

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your_key_here
NAXUYE_WORKSPACE=path/to/agent_factory
```

可选：
```env
ZHIPUAI_API_KEY=your_key
DASHSCOPE_API_KEY=your_key
TAVILY_API_KEY=your_key
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

#### 运行工厂（命令行模式）

```bash
python main.py
```

输入需求，例如：`帮我写一个天气查询 agent`

#### 运行 Nomos（Telegram 管家模式）

```bash
python -m Nomos.core
```

Telegram Bot 指令：

| 指令 | 说明 |
|------|------|
| `/factory <需求>` | 触发工厂生产新 Agent |
| `/list` | 列出所有已注册 Agent |
| `/start <agent> <参数>` | 调用指定 Agent |
| `/status <agent>` | 检查 Agent 健康状态 |
| `/stop <agent>` | 停止 Agent |
| `/logs <agent>` | 查看最近日志 |
| `/reload <agent>` | 热更新重新生产 |

### 演示

**生产天气查询 Agent：**

```
/factory 帮我写一个天气查询agent，用 wttr.in
```

**调用：**

```
/start weather_agent {"input": "北京天气"}
```

**结果：**

```json
{
  "status": "success",
  "result": "北京: ☀️ +22°C, 湿度 45%, 风速 12km/h 西北风",
  "timestamp": 1773923583.84
}
```

视频演示：https://youtube.com/shorts/Lpa1MBS6m68?si=fmGW0e4MDFxk6VL5

### 支持的 LLM 供应商

| 供应商 | 模型 | 层级 |
|--------|------|------|
| DeepSeek | deepseek-reasoner, deepseek-chat | STRATEGIC / ENGINEERING / BASE |
| 阿里云 | qwen3-max, qwen3.5-flash | ENGINEERING / BASE |
| 智谱 | glm-4.7, glm-4-plus, glm-4-flash | STRATEGIC / ENGINEERING / BASE |

节点自动轮询，失败自动切换备用节点。

### 路线图

- [ ] 多组件协调层 `main.py`（框架级编排）
- [ ] error_memory 规则自动注入生成 prompt
- [ ] Agent 间协作调用
- [ ] 并行生产与局部修复
- [ ] Web UI（替代命令行）
- [ ] Docker 容器化
- [ ] PostgreSQL（替代 SQLite）

### 许可证

[MIT](LICENSE)

### 免责声明

本项目处于早期 Alpha 阶段，工厂生产的 Agent 质量取决于 LLM 的代码生成能力，不保证所有生产结果可直接用于生产环境。建议对生成的代码进行人工审查后再部署。
