"""Demo 2 —— Tool Calling Agent（原生函数调用）

模式本质：不靠文本格式解析，而是用模型 API 原生的 tool calling：
模型直接返回结构化的 tool_calls（函数名 + JSON 参数），框架执行后把结果回灌。
比 ReAct 更稳、更省 token，是目前生产首选，且支持单轮并行多工具调用。

本 demo 写两段对照：
  Part A —— 低层原理：llm.bind_tools() + 手动看 tool_calls + 回灌 ToolMessage（看清原理）。
  Part B —— 高层封装：langchain 1.x 统一入口 create_agent（替代已移除的 create_tool_calling_agent）。

运行：
    conda activate cv && python -m tests.module.langchain_demo.demo2_tool_calling

验证点：Part A 能打印模型一次返回的结构化 tool_calls（含并行调用），参数 JSON 正确；
Part B 高层 agent 自动完成调用并给出最终回答。
"""

from langchain_core.messages import HumanMessage, ToolMessage
from langchain.agents import create_agent

from src.common.logger import logger
from tests.module.langchain_demo._common import build_llm, EXTRACT_TOOLS, fmt_messages

TOOLS = {t.name: t for t in EXTRACT_TOOLS}


def part_a_bind_tools():
    """低层原理对照：手动驱动一轮 tool calling。"""
    logger.info("=" * 60)
    logger.info("[Part A] bind_tools 低层原理对照")
    logger.info("=" * 60)

    llm = build_llm(temperature=0)
    llm_with_tools = llm.bind_tools(EXTRACT_TOOLS)

    question = (
        "候选人 2019 年入职、2024 年离职；他做过 3 个项目：['推荐系统','风控平台','数据看板']；"
        "电话是 (010) 8888-6666。请算出工作年限、项目数量，并清洗电话号码。"
    )
    messages = [HumanMessage(content=question)]

    # 第一轮：模型决定调用哪些工具（可能并行多个）
    logger.info("[Part A 第1轮] 发送给 LLM 的消息:\n{}", fmt_messages(messages))
    ai_msg = llm_with_tools.invoke(messages)
    logger.info("模型本轮返回 tool_calls（结构化、可并行）：")
    for tc in ai_msg.tool_calls:
        logger.info("  - {} 参数={}", tc["name"], tc["args"])
    messages.append(ai_msg)

    # 框架角色：逐个执行工具，把结果以 ToolMessage 回灌
    for tc in ai_msg.tool_calls:
        tool = TOOLS[tc["name"]]
        result = tool.invoke(tc["args"])
        logger.info("  执行 {} -> {}", tc["name"], result)
        messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    # 第二轮：把工具结果交回模型，得到自然语言最终回答
    logger.info("[Part A 第2轮] 发送给 LLM 的消息:\n{}", fmt_messages(messages))
    final = llm_with_tools.invoke(messages)
    logger.success("[Part A] 最终回答：{}", final.content)


def part_b_create_agent():
    """高层封装：create_agent 自动完成 思考->调用工具->汇总 的循环。"""
    logger.info("=" * 60)
    logger.info("[Part B] create_agent 高层封装（langchain 1.x 统一入口）")
    logger.info("=" * 60)

    llm = build_llm(temperature=0)
    agent = create_agent(model=llm, tools=EXTRACT_TOOLS)

    question = (
        "候选人 2020 年入职、2026 年离职，技能列表 ['Python','SQL','Docker','Linux']，"
        "电话 +86 138-1234-5678。请告诉我工作年限、技能数量、标准化后的电话。"
    )
    part_b_msgs = [HumanMessage(content=question)]
    logger.info("[Part B] 发送给 Agent 的消息:\n{}", fmt_messages(part_b_msgs))
    result = agent.invoke({"messages": part_b_msgs})
    final_msg = result["messages"][-1]
    logger.success("[Part B] 最终回答：{}", final_msg.content)


if __name__ == "__main__":
    part_a_bind_tools()
    part_b_create_agent()
