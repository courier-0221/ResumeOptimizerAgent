# LangChain 四种 Agent 模式 Demo 设计（待 review）

> 目标：用 **LangChain** 框架、**deepseek-v4-pro** 模型，分别实现并验证四种常用 Agent 模式。
> 本文档先给出每个 demo 的「功能 / 设计 / 涉及接口」，review 通过后再落地代码到本目录。
>
> 统一约定：
> - 模型走项目现有的 `ChatOpenAI`（OpenAI 兼容协议）+ DeepSeek `base_url`，复用 `src/common/config.py` 的 `Config`。
> - 日志复用 `src/common/logger.py` 的 `logger`。
> - 每个 demo 一个独立文件，文件内 `if __name__ == "__main__"` 可直接跑；不依赖 Redis / FastAPI。
> - 所有「工具（tool）」用**本地假数据 / 纯函数**实现，不调真实外部服务，保证离线可跑、结果稳定、省 token。
> - demo 主题统一围绕项目业务「简历优化」，便于直观理解，也方便后续迁移到 `src/core`。

---

## 0. 模型接入与前置说明（运行环境：conda `cv`）

> ⚠️ 实测环境为 **langchain 1.x**（cv 环境：langchain 1.3.2 / langchain-core 1.4.x / langgraph 1.2.x）。
> langchain 1.x **已移除经典 agent API**（`create_react_agent` / `create_tool_calling_agent` / `AgentExecutor`），
> `langchain.agents` 只保留统一入口 `create_agent`（底层基于 LangGraph、走原生 tool calling）。
> 因此各 demo 按 1.x 落地：
> - ReAct → **手写 Thought/Action/Observation 推理循环**（最能体现该模式本质，且不依赖被移除的 API）。
> - Tool Calling → `llm.bind_tools()` 原理对照 + `create_agent` 高层封装。
> - Plan-and-Execute / Supervisor → **LangGraph `StateGraph`** 自建图。

DeepSeek 的 OpenAI 兼容接口支持 **function/tool calling**，因此 Tool Calling / Supervisor 这类依赖原生工具调用的模式可以直接用。

```python
from langchain_openai import ChatOpenAI
from src.common.config import Config

cfg = Config()
llm = ChatOpenAI(
    model=cfg.MODEL_NAME,            # deepseek-v4-pro
    api_key=cfg.DEEPSEEK_API_KEY,
    base_url=cfg.DEEPSEEK_BASE_URL,  # https://api.deepseek.com
    temperature=0,                   # demo 求稳定，用 0
)
```

需要确认的依赖（详见文末「依赖与运行」）：
- `langchain` / `langchain-openai` / `langchain-core`：已在 `requirements.txt`。
- `langgraph`：**Plan-and-Execute** 与 **Multi-Agent/Supervisor** 推荐用它实现，需新增。
- `langchain-experimental`（可选）：仅当我们不想引入 langgraph，用它的旧版 `PlanAndExecute`。

---

## 1. ReAct Agent —— 「推理 + 行动」循环

### 思路
ReAct = **Reasoning + Acting**。模型按 `Thought → Action → Observation` 的循环边想边做：自己决定下一步调哪个工具、用什么参数，看到工具返回（Observation）后再继续推理，直到给出 `Final Answer`。其「思考过程」靠 prompt 约束输出固定文本格式来驱动。

### Demo 功能：简历-岗位匹配问答助手
输入一个自然语言问题，例如：
> “候选人会 Python 和 Docker，应聘『后端开发工程师』，匹配度怎么样？还缺哪些技能？”

Agent 自己决定依次调用工具，最终给出匹配结论。

### 工具设计（本地纯函数）
| 工具 | 入参 | 作用 |
|---|---|---|
| `get_jd_skills(job_title)` | 岗位名 | 返回该岗位要求技能列表（查内置 dict） |
| `match_skills(candidate, required)` | 两个技能列表 | 返回命中 / 缺失技能 |
| `score_match(hit, total)` | 命中数 / 总数 | 返回 0-100 匹配分 |

### 关键接口（langchain 1.x 落地）
- 经典 `create_react_agent`/`AgentExecutor` 已移除 → **手写 ReAct 循环**：`ChatOpenAI` + 本地 ReAct prompt + 文本解析（Thought/Action/Action Input/Observation/Final Answer）。
- 工具用 `@tool`，循环里 `tool.invoke(args)` 执行。
- 本地内置 ReAct prompt（不联网拉 hub），逐轮打印推理链。

### 验证点
- 终端能看到完整 `Thought/Action/Observation` 推理链。
- 多步工具调用顺序正确，最终答案包含匹配分与缺失技能。

---

## 2. Tool Calling Agent —— 原生函数调用

### 思路
不靠文本格式解析，而是用模型 API 原生的 **tool calling**：模型直接返回结构化的 `tool_calls`（函数名 + JSON 参数），由框架执行后把结果回灌。比 ReAct 更稳、更省 token，是目前生产首选。支持**单轮并行多工具调用**。

### Demo 功能：简历信息抽取 + 计算小助手
输入一段简历纯文本片段，让 Agent 通过工具抽取结构化字段并做计算，例如：
> “这是候选人简历：……（含 2019-2024 工作经历、3 个项目）。算下他的总工作年限，并统计项目数量。”

### 工具设计
| 工具 | 入参 | 作用 |
|---|---|---|
| `calc_work_years(start_year, end_year)` | 起止年份 | 计算工作年限 |
| `count_items(items)` | 字符串列表 | 统计数量（项目数 / 技能数） |
| `normalize_phone(raw)` | 原始电话串 | 清洗成标准格式 |

工具用 `@tool` 装饰器声明，参数类型 + docstring 会自动生成给模型的 schema。

### 关键接口（langchain 1.x 落地）
- `langchain_core.tools.tool`（`@tool` 装饰器）
- **原理对照（低层）**：`llm.bind_tools([...])` → 看 `response.tool_calls` → 手动执行 → 回灌 `ToolMessage` → 再次 `invoke` 拿最终答案。
- **高层封装**：`from langchain.agents import create_agent`（1.x 统一入口，替代已移除的 `create_tool_calling_agent` + `AgentExecutor`）。

### 验证点
- 模型一次返回结构化 `tool_calls`，参数 JSON 正确。
- 演示并行调用（同一轮里既算年限又数项目）。

---

## 3. Plan-and-Execute Agent —— 先规划再执行

### 思路
把「规划」和「执行」拆成两段：
1. **Planner**：先让 LLM 把大任务拆成有序子步骤清单（plan）。
2. **Executor**：逐步执行每个子步骤（每步可再调工具 / 小 agent），并把已完成步骤的结果作为上下文带给下一步。

适合步骤多、依赖关系强的长任务，规划与执行解耦后更可控、可观测。

### Demo 功能：简历优化任务编排（贴合项目主流程）
输入：`job_title` + 一段简历文本。期望 Planner 自动产出类似计划：
```
1. 解析简历，抽取结构化字段
2. 拉取岗位要求技能
3. 分析匹配度，找出差距
4. 针对差距给出简历优化建议
```
Executor 按计划逐条执行，每步调用对应工具，最后汇总成一份「优化建议」。

### 工具设计
复用第 1、2 节的工具（`get_jd_skills` / `match_skills` 等）+ 一个 `summarize_suggestions(...)`。

### 实现（已定：LangGraph `StateGraph`）
- `from langgraph.graph import StateGraph, START, END`
- State：`input` / `plan: list[str]` / `past_steps: list[tuple]` / `response`。
- 节点：`planner`（`llm.with_structured_output(Plan)` 产出步骤）→ `executor`（执行当前步、可调工具）→ `replan`（判断结束或更新 plan）。
- `add_conditional_edges` 控制 `executor → replan → executor/END` 循环，逐步打印。

### 验证点
- 能打印出 Planner 生成的步骤清单。
- Executor 按步骤执行且后续步骤能用到前序结果。

---

## 4. Multi-Agent / Supervisor —— 多智能体协作

### 思路
一个 **Supervisor（主管）** Agent 负责「路由 / 调度」，把任务分派给多个**专职子 Agent**，根据当前进度决定下一个该谁干，直到任务完成。每个子 Agent 有独立职责、独立工具集。

### Demo 功能：简历优化「小团队」
三个专职子 Agent + 一个 Supervisor：
| 角色 | 职责 | 工具 |
|---|---|---|
| `ParserAgent` | 把简历文本抽成结构化字段 | `calc_work_years` / `count_items` |
| `AnalystAgent` | 分析与岗位的匹配度、找差距 | `get_jd_skills` / `match_skills` / `score_match` |
| `WriterAgent` | 产出优化后的要点 / 建议 | `summarize_suggestions` |
| `Supervisor` | 决定下一步交给谁，何时结束 | —（只做路由） |

流程示意：
```
Supervisor → ParserAgent → Supervisor → AnalystAgent → Supervisor → WriterAgent → 结束
```

### 实现（已定：手写 LangGraph supervisor 图）
- `StateGraph` + supervisor 节点用 `llm.with_structured_output(Route)` 选择下一个 worker（`parser`/`analyst`/`writer`/`FINISH`）。
- 三个 worker 节点各用 `create_agent`（带各自工具子集）执行。
- `add_conditional_edges` 按 supervisor 决策路由，打印每步调度。

### 验证点
- 能打印 Supervisor 每一步的路由决策（交给了哪个子 Agent）。
- 三个子 Agent 各自产出，最终汇总出完整优化结果。

---

## 5. 目录与文件规划

```
tests/module/langchain_demo/
├── design.md                 # 本文档
├── README.md                 # 跑法说明（review 后补）
├── __init__.py
├── _common.py                # 共享：build_llm() + 本地工具集（避免重复）
├── demo1_react.py            # ReAct
├── demo2_tool_calling.py     # Tool Calling（含 bind_tools 原理对照）
├── demo3_plan_execute.py     # Plan-and-Execute
└── demo4_supervisor.py       # Multi-Agent / Supervisor
```

设计要点：
- **`_common.py` 收口**：`build_llm()` 与全部本地工具（`get_jd_skills` 等）只写一份，四个 demo 共享，避免重复、便于对比四种模式「同样的工具、不同的编排」。
- 每个 demo 文件顶部用注释写清：这是哪种模式、解决什么、看哪几行输出验证。
- 默认 `temperature=0`，并在无 `DEEPSEEK_API_KEY` 时友好报错提示。

---

## 6. 依赖与运行

新增依赖（已在 cv 环境安装）：
- `langgraph`（1.x，Plan-and-Execute / Supervisor 必需）。

运行方式（每个 demo 独立，在项目根目录、cv 环境）：
```bash
conda run -n cv python -m tests.module.langchain_demo.demo1_react
```

环境变量：复用项目 `.env` 的 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `MODEL_NAME`。

---

## 7. Review 结论（已确认）
1. ✅ 业务场景统一用「简历优化」，不变。
2. ✅ 第 3、4 节统一用 **LangGraph**。
3. ✅ 第 2 节增加 `bind_tools` 底层对照。
4. ❌ 不单独写 README。
5. ✅ 需真实联网调用 deepseek-v4-pro 跑通验证。
6. 📌 运行环境为 conda `cv`（langchain 1.x），经典 agent API 已移除，落地按第 0 节说明适配。
