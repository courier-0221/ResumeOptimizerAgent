"""Demo 1 —— ReAct Agent（推理 + 行动循环）

模式本质：模型按 `Thought → Action → Action Input → Observation` 的循环边想边做，
自己决定下一步调哪个工具、用什么参数，看到工具返回（Observation）后继续推理，
直到输出 `Final Answer`。

为什么手写循环：langchain 1.x 已移除经典的 `create_react_agent` / `AgentExecutor`。
手写一个最小 ReAct 循环，最能直观体现该模式的「文本推理链」本质，且不依赖被移除的 API。

运行：
    conda activate cv && python -m tests.module.langchain_demo.demo1_react

验证点：终端能看到完整 Thought/Action/Observation 链路，多步工具调用顺序正确，
最终答案包含匹配分与缺失技能。
"""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from src.common.logger import logger
from tests.module.langchain_demo._common import build_llm, SKILL_TOOLS, fmt_messages

# 工具注册表：name -> tool 对象（循环里按名字调用）
TOOLS = {t.name: t for t in SKILL_TOOLS}

# 内置 ReAct prompt（不联网拉 hub）。约束模型严格输出固定格式。
REACT_SYSTEM = """你是一个简历-岗位匹配分析助手。请用 ReAct 方式解决问题：边推理边调用工具。

可用工具：
- get_jd_skills(job_title: str) -> list[str]：返回岗位要求技能列表
- match_skills(candidate_skills: list[str], required_skills: list[str]) -> dict：返回 {hit, missing}
- score_match(hit_count: int, total_count: int) -> int：返回 0-100 匹配分

你必须严格按如下格式逐步输出，每次只输出一步：

Thought: 你的思考
Action: 工具名（上面三选一）
Action Input: 一个 JSON 对象，作为该工具的参数

当你拿到足够信息后，用下面的格式给出最终答案：

Thought: 我已经知道答案
Final Answer: 给用户的中文结论（必须包含匹配分和缺失技能）

注意：
1. Action Input 必须是合法 JSON，键名与工具参数名一致。
2. 一次只输出到 Action Input 为止，然后停下等待 Observation。
3. 不要编造 Observation。"""

# 解析模型输出的正则
_ACTION_RE = re.compile(r"Action:\s*(.+?)\s*[\r\n]+Action Input:\s*(\{.*?\}|\[.*?\]|.+)", re.DOTALL)
_FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)


def _parse(text: str):
    """从模型输出里解析出 (final_answer) 或 (tool_name, tool_args)。"""
    final = _FINAL_RE.search(text)
    if final:
        return "final", final.group(1).strip(), None

    m = _ACTION_RE.search(text)
    if not m:
        return "unknown", None, None

    tool_name = m.group(1).strip()
    raw_args = m.group(2).strip()
    # Action Input 之后若还有内容（模型多输出了），只取第一段 JSON
    try:
        # 截到第一个完整 JSON
        decoder = json.JSONDecoder()
        args, _ = decoder.raw_decode(raw_args)
    except json.JSONDecodeError:
        args = raw_args
    return tool_name, args, None


def run_react(question: str, max_steps: int = 6) -> str:
    llm = build_llm(temperature=0)
    messages = [SystemMessage(content=REACT_SYSTEM), HumanMessage(content=question)]

    logger.info("=" * 60)
    logger.info("[ReAct] 问题：{}", question)
    logger.info("=" * 60)

    for step in range(1, max_steps + 1):
        logger.info("[第{}步] 发送给 LLM 的消息:\n{}", step, fmt_messages(messages))
        # stop 在 Observation 处截断，避免模型自己幻想工具结果
        resp = llm.invoke(messages, stop=["Observation:"])
        # resp 的类型就是 AIMessage，type="ai"，role 在 fmt_messages 时会对应到 "assistant"
        text = resp.content
        logger.info("[第{}步] 模型输出:\n{}", step, text.strip())

        kind, payload, _ = _parse(text)

        if kind == "final":
            logger.success("[ReAct] 最终答案：{}", payload)
            return payload

        if kind == "unknown" or payload is None:
            logger.warning("[ReAct] 无法解析出 Action/Final，提前结束。")
            return text.strip()

        tool_name, tool_args = kind, payload
        tool = TOOLS.get(tool_name)
        if tool is None:
            observation = f"错误：不存在名为 {tool_name} 的工具。"
        else:
            try:
                observation = tool.invoke(tool_args)
            except Exception as e:  # 工具入参不合法等
                observation = f"工具执行出错：{e}"

        logger.info("[第{}步] 调用 {} 参数={} -> Observation={}", step, tool_name, tool_args, observation)

        # 把本步模型输出 + Observation 拼回上下文，进入下一轮推理
        messages.append(resp)
        messages.append(HumanMessage(content=f"Observation: {json.dumps(observation, ensure_ascii=False)}"))

    logger.warning("[ReAct] 达到最大步数仍未得到 Final Answer。")
    return "未能在限定步数内完成。"


if __name__ == "__main__":
    run_react(
        "候选人会 Python、Docker、Linux，应聘『后端开发工程师』，"
        "匹配度怎么样？还缺哪些技能？"
    )
