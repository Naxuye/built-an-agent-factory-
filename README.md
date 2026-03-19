# Naxuye Agent Factory

> 🚧 **Alpha - Under Active Development** | 核心流程已跑通，生产质量持续优化中

Naxuye 是一个基于 LangGraph 的 **AI Agent 自动化工厂**。输入一句自然语言需求，工厂自动完成需求分析、架构拆解、代码生产、质量审计、冒烟测试、归档注册的完整流程，产出可独立运行的 Agent。

通过 Telegram Bot（Nomos 管家系统）统一管理所有已注册的 Agent，实现远程调用、状态监控、热更新。

<img width="950" height="947" alt="image" src="https://github.com/user-attachments/assets/ec92efb0-9ec7-4329-b469-018e9ec9fe75" />
<img width="950" height="947" alt="image" src="https://github.com/user-attachments/assets/90f800e3-571d-428d-babf-4776d3f1f31d" />


## Features

- **自然语言驱动**：一句话描述需求，工厂自动理解、拆解、生产
- **多 LLM 协作**：支持 DeepSeek、阿里云通义、智谱 GLM 多节点轮询，自动容错切换
- **工业级质控**：PostChecker 静态校验 → LLM 深度审计 → Sandbox 冒烟测试，三重质检
- **分批生产**：大型 Agent 自动拆分批次并行生产，失败组件自动重工
- **Telegram 管家**：通过 Bot 远程触发生产、调用 Agent、查看状态、热更新
- **进程隔离**：每个 Agent 在独立沙箱中运行，超时/内存溢出自动 kill

## Architecture

```
naxuye-agent/
├── .env                              # 环境变量（API keys）
└── workspace/
    ├── main.py                       # 工厂命令行入口
    ├── langgraph_workflow.py          # LangGraph 图编排
    ├── workflow_state.py              # 全局状态定义
    ├── workflow_nodes.py              # 节点 wrapper 函数
    │
    ├── commander/                    # 指挥层
    │   ├── intent_parser.py          # 意图解析
    │   ├── planner.py                # 战略拆解（需求分析 → 组件设计）
    │   ├── reviewer.py               # LLM 代码审计
    │   ├── post_checker.py           # 静态校验（AST + 正则）
    │   ├── smoke_test.py             # 冒烟测试（import + health + run）
    │   ├── mindset.py                # 签署归档 + Nomos 注册
    │   ├── logic_core_extractor.py   # 代码抛光
    │   ├── api_router.py             # 多 LLM 智能路由
    │   └── smart_client.py           # 国内/海外自动直连/代理
    │
    ├── pillow/                       # 生产层
    │   └── agent_builder.py          # LLM 代码生成引擎
    │
    ├── scout/                        # 侦察层
    │   └── intelligence_fetcher.py   # Tavily 搜索 + LLM 情报提纯
    │
    ├── Nomos/                        # 管家系统
    │   ├── core.py                   # 主进程入口
    │   ├── broker.py                 # 消息中转（Request-Ack-Push）
    │   ├── command.py                # 指令集定义
    │   ├── registry.py               # Agent 注册表管理
    │   ├── sandbox.py                # 进程沙箱（隔离执行 + 资源监控）
    │   ├── telegram.py               # Telegram Bot 接入
    │   └── agent_map.json            # 注册表数据
    │
    ├── configs/                      # 配置层
    │   ├── naxuye_config_v26.py      # 算力矩阵（多 LLM 节点配置）
    │   └── resource_grid.py          # 并发信号量 + 超时配置
    │
    ├── templates/                    # 模板
    │   └── agent_template.py         # Agent 代码骨架
    │
    └── agent_factory/                # 产出目录（自动生成）
        ├── translation_agent_SAFE_xxx/
        ├── weather_agent_SAFE_xxx/
        └── ...
```

## Factory Pipeline

```
用户需求 → Intent Parser → Dispatcher → Planner → Scout
                                                      ↓
         END ← Logistic ← Mindset ← SmokeTest ← Reviewer ← Pillow
                                        ↑                      ↓
                                        └──── 重工 (max 6次) ──┘
```

**完整流程：**

1. **Intent Parser** — 清洗输入，初始化状态
2. **Dispatcher** — 判断算力等级，选择 LLM 节点
3. **Planner** — 深度理解需求，拆解为组件列表，设计架构
4. **Scout** — Tavily 搜索 + LLM 提纯技术情报
5. **Batch Scheduler** — 分批调度组件生产
6. **Pillow** — 并发调用 LLM 生成代码，失败自动切换备用节点
7. **Reviewer** — PostChecker 静态校验 + LLM 深度审计
8. **Smoke Test** — 在临时沙箱中验证 import / health() / run()
9. **Mindset** — 人工或自动签署 → 代码抛光 → 文件归档 → Nomos 注册
10. **Logistic** — 生成交付清单，流程结束

## Quick Start

### Prerequisites

- Python 3.11+
- 至少一个 LLM API key（DeepSeek / 阿里云 / 智谱）

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/naxuye-agent.git
cd naxuye-agent

pip install -r requirements.txt
```

### Configuration

复制环境变量模板并填入 API keys：

```bash
cp .env.template .env
```

必填项：
```env
DEEPSEEK_API_KEY=your_key_here
NAXUYE_WORKSPACE=path/to/workspace/agent_factory
```

### Run Factory (命令行模式)

```bash
cd workspace
python main.py
```

输入需求，例如：`帮我写一个中英文翻译agent`

### Run Nomos (Telegram 管家模式)

```bash
cd workspace
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

## Demo

**生产翻译 Agent：**

```
/factory 帮我写一个中英文翻译agent
```

**调用：**

```
/start translation_agent {"input": "星星之火，可以燎原"}
```

**结果：**

```json
{
  "status": "success",
  "result": "A spark can start a prairie fire.",
  "timestamp": 1773923583.84
}
```
https://youtube.com/shorts/Lpa1MBS6m68?si=fmGW0e4MDFxk6VL5

## Supported LLM Providers

| Provider | Models | Tier |
|----------|--------|------|
| DeepSeek | deepseek-reasoner, deepseek-chat, deepseek-coder | STRATEGIC / ENGINEERING / BASE |
| 阿里云 | qwen3-max, qwen3.5-plus, qwen3-coder-plus, qwen3.5-flash | STRATEGIC / ENGINEERING / BASE |
| 智谱 | glm-5, glm-4-plus, glm-4-flash | STRATEGIC / ENGINEERING / BASE |

节点自动轮询，失败自动切换备用节点。

## Roadmap

- [ ] 提升 Planner 对复杂需求的理解能力
- [ ] 生产 Agent 的代码质量优化（减少 LLM 幻觉）
- [ ] Agent 间协作调用
- [ ] Web UI 替代命令行
- [ ] 自动化集成测试（不只是冒烟测试）
- [ ] 支持更多 LLM 提供商

## License

[MIT](LICENSE)

## Disclaimer

本项目处于早期 Alpha 阶段，工厂生产的 Agent 质量取决于 LLM 的代码生成能力，不保证所有生产结果可直接用于生产环境。建议对生成的代码进行人工审查后再部署。
