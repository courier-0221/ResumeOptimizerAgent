"""Demo 3 —— Plan-and-Execute Agent（先规划再执行）

模式本质：把「规划」和「执行」拆开。
1. Planner：先让 LLM 把大任务拆成有序子步骤清单（plan）。
2. Executor：逐步执行每个子步骤（每步可再调工具），已完成步骤的结果作为后续上下文。
3. Replan：每执行完一步，回看进度，决定「结束并给结论」还是「更新剩余计划」。

适合步骤多、依赖强的长任务，规划与执行解耦后更可控、可观测。
实现用 LangGraph StateGraph：planner -> executor -> replan -> (executor | END)。

运行：
    conda activate cv && python -m tests.module.langchain_demo.demo3_plan_execute

验证点：能打印 Planner 生成的步骤清单；Executor 逐步执行且后续步骤能用到前序结果；
Replan 能判断收尾并产出最终优化建议。
"""

import operator
from typing import Annotated, List, Tuple

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END

from src.common.logger import logger
from tests.module.langchain_demo._common import build_llm, ALL_TOOLS, fmt_messages

MAX_STEPS = 6  # 安全上限，避免 replan 循环不收敛


# ===== 图状态 =====
class PlanState(TypedDict):
    input: str                                   # 原始任务（岗位 + 简历信息）
    plan: List[str]                              # 待执行步骤
    past_steps: Annotated[List[Tuple[str, str]], operator.add]  # (步骤, 结果)
    response: str                                # 最终结论


# ===== 结构化输出模型 =====
class Plan(BaseModel):
    """任务拆解出的有序步骤清单。"""
    steps: List[str] = Field(description="为完成任务需要依次执行的步骤，每条一句话")


class ReplanResult(BaseModel):
    """回看进度后的决策。"""
    done: bool = Field(description="是否已完成全部必要步骤、可以给最终结论")
    response: str = Field(default="", description="done=True 时给用户的最终中文优化建议")
    remaining_steps: List[str] = Field(
        default_factory=list, description="done=False 时，剩余还需执行的步骤"
    )


# 执行单步用的 tool-agent（带全部工具）
_executor_agent = create_agent(model=build_llm(temperature=0), tools=ALL_TOOLS)


def plan_node(state: PlanState) -> dict:
    llm = build_llm(temperature=0)
    planner = llm.with_structured_output(Plan, method="function_calling")
    prompt = (
        "你是简历优化任务的规划者。请把下面的任务拆成有序、可执行的步骤"
        "（解析简历 -> 拉取岗位技能 -> 分析匹配差距 -> 产出优化建议）。\n\n"
        f"任务：{state['input']}"
    )
    plan = planner.invoke(prompt)
    logger.info("=" * 60)
    logger.info("[Planner] 生成计划：")
    for i, s in enumerate(plan.steps, 1):
        logger.info("  {}. {}", i, s)
    return {"plan": plan.steps}


def execute_node(state: PlanState) -> dict:
    task = state["plan"][0]
    done_summary = "\n".join(f"- {s} => {r}" for s, r in state["past_steps"]) or "（无）"
    msg = (
        f"原始任务：{state['input']}\n"
        f"已完成步骤与结果：\n{done_summary}\n\n"
        f"现在请只完成这一步并给出简短结果：{task}"
    )
    exec_msgs = [HumanMessage(content=msg)]
    logger.info("[Executor] 发送给 Agent 的消息:\n{}", fmt_messages(exec_msgs))
    result = _executor_agent.invoke({"messages": exec_msgs})
    answer = result["messages"][-1].content
    logger.info("[Executor] 执行步骤「{}」-> {}", task, answer)
    return {"past_steps": [(task, answer)]}


def replan_node(state: PlanState) -> dict:
    # 安全上限：步数过多直接收尾
    if len(state["past_steps"]) >= MAX_STEPS:
        summary = "\n".join(f"- {s} => {r}" for s, r in state["past_steps"])
        return {"response": f"（达到步数上限，汇总已完成结果）\n{summary}"}

    llm = build_llm(temperature=0)
    replanner = llm.with_structured_output(ReplanResult, method="function_calling")
    done_summary = "\n".join(f"- {s} => {r}" for s, r in state["past_steps"])
    prompt = (
        f"原始任务：{state['input']}\n"
        f"原计划：{state['plan']}\n"
        f"已完成步骤与结果：\n{done_summary}\n\n"
        "请判断：是否已经能给出『简历优化建议』的最终结论？\n"
        "若可以，done=True 并在 response 写出中文最终优化建议；\n"
        "若还需继续，done=False 并在 remaining_steps 给出剩余步骤。"
    )
    decision = replanner.invoke(prompt)
    if decision.done:
        logger.success("[Replan] 判定完成，产出最终结论。")
        return {"response": decision.response}
    logger.info("[Replan] 仍需继续，剩余步骤：{}", decision.remaining_steps)
    return {"plan": decision.remaining_steps}


def _should_continue(state: PlanState) -> str:
    if state.get("response"):
        return END
    if not state.get("plan"):
        return END
    return "executor"


def build_graph():
    g = StateGraph(PlanState)
    g.add_node("planner", plan_node)
    g.add_node("executor", execute_node)
    g.add_node("replan", replan_node)
    g.add_edge(START, "planner")
    g.add_edge("planner", "executor")
    g.add_edge("executor", "replan")
    g.add_conditional_edges("replan", _should_continue, {"executor": "executor", END: END})
    return g.compile()


if __name__ == "__main__":
    app = build_graph()
    task = (
        "候选人技能 ['Python','Docker','Linux','SQL']，工作经历 2019-2024；"
        "目标岗位『后端开发工程师』。请分析匹配度并给出简历优化建议。"
    )
    final = app.invoke(
        {"input": task, "plan": [], "past_steps": [], "response": ""},
        config={"recursion_limit": 30},
    )
    logger.success("=" * 60)
    logger.success("[Plan-and-Execute] 最终结论：\n{}", final["response"])
