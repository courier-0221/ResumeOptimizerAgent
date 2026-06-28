"""Demo 4 —— Multi-Agent / Supervisor（多智能体协作）

模式本质：一个 Supervisor（主管）负责「路由 / 调度」，把任务分派给多个专职子 Agent，
根据当前进度决定下一个该谁干，直到任务完成。每个子 Agent 有独立职责与独立工具集。

本 demo 的「简历优化小团队」：
  - ParserAgent ：把简历文本抽成结构化字段（工具：计算/计数/电话清洗）
  - AnalystAgent：分析与岗位的匹配度、找差距（工具：岗位技能/匹配/打分）
  - WriterAgent ：产出优化建议（工具：建议生成）
  - Supervisor  ：决定下一步交给谁、何时 FINISH（只做路由）

实现用 LangGraph StateGraph：supervisor -> {parser|analyst|writer} -> supervisor -> ... -> END。

运行：
    conda run -n cv python -m tests.module.langchain_demo.demo4_supervisor

验证点：能打印 Supervisor 每一步的路由决策（交给哪个子 Agent）；三个子 Agent 各自产出，
最终汇总出完整优化结果。
"""

import operator
from typing import Annotated, List, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END

from src.common.logger import logger
from tests.module.langchain_demo._common import (
    build_llm,
    SKILL_TOOLS,
    EXTRACT_TOOLS,
    WRITER_TOOLS,
    fmt_messages,
)

WORKERS = ["parser", "analyst", "writer"]


class TeamState(TypedDict):
    task: str
    messages: Annotated[List[str], operator.add]    # 各 worker 的产出
    completed: Annotated[List[str], operator.add]    # 已完成的 worker
    next: str


class Route(BaseModel):
    """主管的路由决策。"""
    next: Literal["parser", "analyst", "writer", "FINISH"] = Field(
        description="下一个该执行的 worker；全部完成后返回 FINISH"
    )


# 三个专职子 Agent，各自只带本职工具
parser_agent = create_agent(model=build_llm(temperature=0), tools=EXTRACT_TOOLS)
analyst_agent = create_agent(model=build_llm(temperature=0), tools=SKILL_TOOLS)
writer_agent = create_agent(model=build_llm(temperature=0), tools=WRITER_TOOLS)


def supervisor_node(state: TeamState) -> dict:
    llm = build_llm(temperature=0)
    router = llm.with_structured_output(Route, method="function_calling")
    prompt = (
        "你是简历优化团队的主管，负责调度三个子 Agent：\n"
        "- parser：把简历抽成结构化字段（工作年限、项目数、电话等）\n"
        "- analyst：分析候选人与目标岗位的技能匹配度、找出差距\n"
        "- writer：根据差距产出最终简历优化建议\n\n"
        f"任务：{state['task']}\n"
        f"已完成的 worker：{state['completed'] or '（无）'}\n\n"
        "请按 parser -> analyst -> writer 的顺序调度（每个只需执行一次）；"
        "当三者都完成后返回 FINISH。只返回下一个该执行的 worker。"
    )
    route = router.invoke(prompt)
    logger.info("[Supervisor] 决策下一步 -> {}", route.next)
    return {"next": route.next}


def _run_worker(agent, role: str, state: TeamState, instruction: str) -> dict:
    context = "\n".join(state["messages"]) or "（暂无前序结果）"
    msg = f"任务：{state['task']}\n前序结果：\n{context}\n\n你的职责：{instruction}"
    worker_msgs = [HumanMessage(content=msg)]
    logger.info("[{}] 发送给 Agent 的消息:\n{}", role, fmt_messages(worker_msgs))
    result = agent.invoke({"messages": worker_msgs})
    answer = result["messages"][-1].content
    logger.info("[{}] 产出 -> {}", role, answer)
    return {"messages": [f"[{role}] {answer}"], "completed": [role]}


def parser_node(state: TeamState) -> dict:
    return _run_worker(parser_agent, "parser", state,
                       "抽取候选人的工作年限、项目数量、标准化电话等结构化信息。")


def analyst_node(state: TeamState) -> dict:
    return _run_worker(analyst_agent, "analyst", state,
                       "分析候选人技能与目标岗位的匹配度，给出匹配分与缺失技能。")


def writer_node(state: TeamState) -> dict:
    return _run_worker(writer_agent, "writer", state,
                       "综合前序结果，产出一句话简历优化建议。")


def _route(state: TeamState) -> str:
    nxt = state["next"]
    return END if nxt == "FINISH" else nxt


def build_graph():
    g = StateGraph(TeamState)
    g.add_node("supervisor", supervisor_node)
    g.add_node("parser", parser_node)
    g.add_node("analyst", analyst_node)
    g.add_node("writer", writer_node)
    g.add_edge(START, "supervisor")
    # 每个 worker 干完回到 supervisor 再决策
    for w in WORKERS:
        g.add_edge(w, "supervisor")
    g.add_conditional_edges(
        "supervisor", _route,
        {"parser": "parser", "analyst": "analyst", "writer": "writer", END: END},
    )
    return g.compile()


if __name__ == "__main__":
    app = build_graph()
    task = (
        "候选人简历：技能 ['Python','Docker','Linux']，工作经历 2019-2024，"
        "做过 3 个项目，电话 (010) 8888-6666；目标岗位『后端开发工程师』。"
    )
    final = app.invoke(
        {"task": task, "messages": [], "completed": [], "next": ""},
        config={"recursion_limit": 30},
    )
    logger.success("=" * 60)
    logger.success("[Supervisor] 团队最终产出汇总：")
    for m in final["messages"]:
        logger.success("  {}", m)
