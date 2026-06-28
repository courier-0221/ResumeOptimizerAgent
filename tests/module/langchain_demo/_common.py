"""langchain_demo 共享模块。

收口两样东西，供四个 demo 复用：
1. build_llm()：基于项目 Config 构造接 DeepSeek 的 ChatOpenAI（OpenAI 兼容协议）。
2. 一组「简历优化」业务工具（@tool）：本地纯函数 / 假数据，离线可跑、结果稳定、省 token。

四个 demo 用同一套工具，只是「编排方式」不同，方便横向对比四种 Agent 模式。
"""

import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import ChatMessage
from langchain_core.tools import tool

from src.common.config import Config
from src.common.logger import logger, setup_logger

# 初始化日志（demo 默认 INFO，避免刷屏；想看细节可改 DEBUG）
setup_logger(level="INFO")


def build_llm(temperature: float = 0.0, **kwargs) -> ChatOpenAI:
    """构造接 DeepSeek 的 ChatOpenAI。

    demo 默认 temperature=0 求稳定可复现。无 API Key 时直接报错提示。

    注意：DeepSeek 思考模式默认开启，但思考模式不支持「强制 tool_choice」，
    而结构化输出（with_structured_output(method="function_calling")）会强制 tool_choice。
    因此这里按项目 Config（ENABLE_THINKING 默认 False）显式关闭思考模式，
    与 src/core/agent.py 行为一致，保证 Plan/Supervisor 的结构化输出可用。
    """
    cfg = Config()
    if not cfg.DEEPSEEK_API_KEY:
        raise RuntimeError(
            "缺少 DEEPSEEK_API_KEY，请在项目根目录 .env 中配置后再运行 demo。"
        )
    extra_body = {
        "thinking": {"type": "enabled" if cfg.ENABLE_THINKING else "disabled"}
    }
    logger.info(
        "build_llm — model={}, base_url={}, temperature={}, thinking={}",
        cfg.MODEL_NAME,
        cfg.DEEPSEEK_BASE_URL,
        temperature,
        extra_body["thinking"]["type"],
    )
    return ChatOpenAI(
        model=cfg.MODEL_NAME,
        api_key=cfg.DEEPSEEK_API_KEY,
        base_url=cfg.DEEPSEEK_BASE_URL,
        temperature=temperature,
        extra_body=extra_body,
        **kwargs,
    )


# ===== 调试工具：将 LangChain messages 格式化为 OpenAI 协议风格 =====

# OpenAI 协议全量 role 固定映射（ChatMessage 使用对象自身的 .role 属性，不在此表）
_ROLE_MAP: dict[str, str] = {
    "system": "system",       # SystemMessage
    "human": "user",          # HumanMessage
    "ai": "assistant",        # AIMessage
    "tool": "tool",           # ToolMessage（function calling 工具结果）
    "function": "function",   # FunctionMessage（旧版 function calling，已废弃但仍支持）
}


def fmt_messages(msgs: list) -> str:
    """将 LangChain messages 序列格式化为 OpenAI 协议风格的 JSON 字符串，供调试日志使用。

    支持全量 role：
      system / user / assistant / tool / function；
      ChatMessage 使用其自身 .role 属性（任意字符串，满足扩展需求）。
    额外字段：
      ToolMessage / FunctionMessage 附带 tool_call_id；
      AIMessage 若含 tool_calls 也一并输出。
    """
    def _to_openai(m) -> dict:
        role = m.role if isinstance(m, ChatMessage) else _ROLE_MAP.get(m.type, m.type)
        entry: dict = {"role": role, "content": m.content}
        if hasattr(m, "tool_call_id") and m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        if hasattr(m, "tool_calls") and m.tool_calls:
            entry["tool_calls"] = m.tool_calls
        return entry

    return json.dumps([_to_openai(m) for m in msgs], ensure_ascii=False, indent=2)


# ===== 本地「假数据」：各岗位要求技能 =====
JD_SKILLS: dict[str, list[str]] = {
    "后端开发工程师": ["Python", "MySQL", "Redis", "Docker", "Kubernetes", "微服务", "Linux"],
    "前端开发工程师": ["JavaScript", "React", "TypeScript", "CSS", "Webpack", "HTTP"],
    "数据分析师": ["SQL", "Python", "Excel", "Tableau", "统计学", "数据可视化"],
}


# ===== 业务工具（@tool）：参数类型 + docstring 会自动生成给模型的 schema =====
@tool
def get_jd_skills(job_title: str) -> list[str]:
    """根据岗位名称（如『后端开发工程师』）返回该岗位要求的技能列表。"""
    return JD_SKILLS.get(job_title, [])


@tool
def match_skills(candidate_skills: list[str], required_skills: list[str]) -> dict:
    """对比候选人技能与岗位要求技能，返回 {hit: 命中技能, missing: 缺失技能}。"""
    cand = {s.strip().lower() for s in candidate_skills}
    hit = [s for s in required_skills if s.strip().lower() in cand]
    missing = [s for s in required_skills if s.strip().lower() not in cand]
    return {"hit": hit, "missing": missing}


@tool
def score_match(hit_count: int, total_count: int) -> int:
    """根据命中技能数 hit_count 与岗位要求技能总数 total_count，计算 0-100 的匹配分。"""
    if total_count <= 0:
        return 0
    return round(hit_count / total_count * 100)


@tool
def calc_work_years(start_year: int, end_year: int) -> int:
    """计算工作年限 = end_year - start_year。"""
    return max(0, end_year - start_year)


@tool
def count_items(items: list[str]) -> int:
    """统计列表元素个数（如项目数、技能数）。"""
    return len(items)


@tool
def normalize_phone(raw: str) -> str:
    """把原始电话字符串清洗成纯数字标准格式（去掉空格、连字符、括号等）。"""
    return "".join(ch for ch in raw if ch.isdigit())


@tool
def summarize_suggestions(missing_skills: list[str], job_title: str) -> str:
    """根据缺失技能列表与目标岗位，生成一句话简历优化建议。"""
    if not missing_skills:
        return f"候选人技能已较好覆盖『{job_title}』要求，建议突出量化业绩。"
    skills = "、".join(missing_skills)
    return f"应聘『{job_title}』，建议补充并在简历中体现：{skills}。"


# 工具集合：按用途分组，供不同 demo 取用
SKILL_TOOLS = [get_jd_skills, match_skills, score_match]          # 匹配分析类
EXTRACT_TOOLS = [calc_work_years, count_items, normalize_phone]   # 信息抽取/计算类
WRITER_TOOLS = [summarize_suggestions]                            # 建议生成类
ALL_TOOLS = SKILL_TOOLS + EXTRACT_TOOLS + WRITER_TOOLS
