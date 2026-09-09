# 迷你 Agent（agent-demo）

我的第一个agent项目
一个**零第三方依赖**的 Python 迷你 Agent，不到 200 行代码，但包含真实 Agent 的全部核心部件：

- 调用真实大模型 API（OpenAI 兼容格式，DeepSeek / 通义 / 各类中转站都能用）
- 三个工具：计算器、获取当前时间、读文件
- 完整的 Agent Loop（思考 → 调工具 → 拿结果 → 再思考）
- 内置 Mock 假模型：不配 API、不花钱，也能看到 Agent 完整跑起来

## 运行

```bash
# Mock 模式：先看懂机制（推荐从这里开始）
py agent.py --mock

# 真实模式：先把 .env.example 复制为 .env，填入你的 API 配置
py agent.py
```

试试问它：

```text
现在几点？
帮我算 (3+5)*12 + 100
读一下 README.md 的前几行
```

## 文件地图

| 文件 | 作用 | 你将从中学到 |
| --- | --- | --- |
| `agent.py` | Agent 主循环 + 命令行交互 | while 循环、列表、dict、函数、异常处理 |
| `tools.py` | 三个工具的实现与登记 | 函数参数、字典查表、AST 安全计算、路径处理 |
| `llm.py` | 大模型 API 客户端 | HTTP 请求、JSON、环境变量、API Key |
| `mock_llm.py` | 假模型（离线演示） | 正则表达式、API 返回的数据结构 |
| `.env` | API 配置（不进 Git） | 环境变量、密钥管理 |
| `.gitignore` | Git 忽略规则 | Git 基础 |

## Agent 是怎么跑起来的（数据流）

```text
你说："帮我算 (3+5)*12"
  │
  ▼
agent.py 把你的话放进 messages 列表，交给模型
  │
  ▼
模型看到工具说明书（TOOLS），决定："我要用 calculator，参数是 (3+5)*12"
  │  （注意：模型只是【提出请求】，它自己不会算！）
  ▼
agent.py 解析请求，调用 tools.py 里真正的 calculator() 函数
  │
  ▼
计算结果 "16" 追加到 messages，再次交给模型
  │
  ▼
模型看到结果，给出最终回答："答案是 16"
```

## 配套学习路线

本项目是 24 周学习计划的"教学样机"。知识总量不变，顺序变为：**先看到整机，再逐个拆零件**。

| 拆解对象 | 涉及知识 | 对应计划周 |
| --- | --- | --- |
| `tools.py` 的函数和字典 | 变量、函数、dict | 第1～2周 |
| `read_file` 的路径与安全 | 文件读写、异常 | 第3周 |
| `llm.py` 的 HTTP 请求 | 网络基础、JSON、API Key | 第7周、第13周 |
| `agent.py` 的主循环 | Agent Loop、Tool Calling | 第18～19周 |
| `.env` 与 `.gitignore` | 环境变量、Git | 第3周、第5周 |
| 计算器的 AST | 进阶：代码解析与安全 | 拓展内容 |

学完全部基础知识后，我们会把这个迷你 Agent 逐步升级成：带 RAG 知识库 → 带数据库 → 用 LangGraph 重写 → 最终变成求职主项目。
