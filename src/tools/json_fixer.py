import json
import re


# 会让 pango/cairo 在 macOS 上崩溃的控制字符 / 不可见字符
_BAD_CHAR_RE = re.compile(
    "[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f"   # C0 控制符
    "\u200b-\u200f\u2028-\u202f\u2060-\u206f"          # 零宽 / 双向控制 / 不间断
    "\ufeff\ufff9-\ufffb"                              # BOM / interlinear
    "]"
)


def sanitize_text(value):
    """递归清除文本中的控制字符 / 零宽字符，避免 WeasyPrint(Pango) 崩溃。"""
    if isinstance(value, str):
        cleaned = _BAD_CHAR_RE.sub("", value)
        # 统一换行符
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
        return cleaned
    if isinstance(value, list):
        return [sanitize_text(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_text(v) for k, v in value.items()}
    return value


def robust_parse_json(llm_output: str, llm=None, max_retries: int = 2) -> dict:
    """多层容错的JSON解析策略"""
    json_str = extract_json_block(llm_output)

    # Layer 1: 直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Layer 2: 常见问题自动修复
    fixed = auto_fix_json(json_str)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Layer 3: 用 LLM 修复
    if llm and max_retries > 0:
        repair_prompt = (
            "以下JSON格式有误，请修复并只输出合法JSON，不要添加任何其他文字：\n"
            f"{json_str}"
        )
        repaired = llm.invoke(repair_prompt).content
        return robust_parse_json(repaired, llm=None, max_retries=0)

    raise ValueError(f"JSON解析失败，无法修复。原始输出前200字符：{llm_output[:200]}")


def extract_json_block(text: str) -> str:
    """从LLM输出中提取JSON内容"""
    # 去掉 ```json ... ``` 包裹
    pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 尝试找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]
    return text.strip()


def auto_fix_json(json_str: str) -> str:
    """自动修复常见JSON问题"""
    # 修复末尾多余逗号
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
    # 补全缺失的右括号
    open_braces = json_str.count("{") - json_str.count("}")
    open_brackets = json_str.count("[") - json_str.count("]")
    json_str += "}" * max(0, open_braces)
    json_str += "]" * max(0, open_brackets)
    return json_str


REQUIRED_FIELDS = ["basic_info", "education", "skills"]
OPTIONAL_FIELDS = [
    "self_evaluation",
    "work_experience",
    "internship",
    "projects",
    "language_ability",
    "certifications",
    "awards",
    "extra_sections",
]

# basic_info 中应包含的子字段及默认值
BASIC_INFO_FIELDS = {
    "name": "",
    "gender": "",
    "age": "",
    "phone": "",
    "email": "",
    "location": "",
    "job_intention": "",
    "expected_salary": "",
    "availability": "",
    "linkedin": "",
    "personal_site": "",
    "github": "",
    "portfolio": "",
}


def normalize_resume_schema(parsed: dict) -> dict:
    """规范化简历结构，确保下游流程兼容"""
    result = {}

    for field in REQUIRED_FIELDS:
        result[field] = parsed.get(field, {} if field == "basic_info" else [])

    # 补全 basic_info 子字段
    for key, default in BASIC_INFO_FIELDS.items():
        if key not in result["basic_info"]:
            result["basic_info"][key] = default

    for field in OPTIONAL_FIELDS:
        if field in parsed and parsed[field]:
            result[field] = parsed[field]

    # 兼容旧字段名：summary → self_evaluation
    if "summary" in parsed and not result.get("self_evaluation"):
        result["self_evaluation"] = parsed["summary"]

    if "self_evaluation" not in result:
        result["self_evaluation"] = ""
    if "extra_sections" not in result:
        result["extra_sections"] = {}

    # —— 技能分类兼容 ——
    # optimize 阶段会输出 skill_categories: [{"category": "...", "items": [...]}]
    # parse 阶段只有扁平 skills；若没有分类，模板会回退到扁平列表
    skill_categories = parsed.get("skill_categories")
    if skill_categories and isinstance(skill_categories, list):
        # 过滤掉空分类
        cleaned = [
            {"category": c.get("category", ""), "items": [i for i in c.get("items", []) if i]}
            for c in skill_categories
            if isinstance(c, dict) and c.get("items")
        ]
        if cleaned:
            result["skill_categories"] = cleaned
            # 若 skills 为空但有分类，扁平化一份兜底
            if not result.get("skills"):
                flat = []
                for c in cleaned:
                    flat.extend(c["items"])
                result["skills"] = flat

    # —— extra_sections 中文标签 ——
    # optimize 阶段会塞一个 "_labels" 子字典，PDF 渲染时优先用中文名
    extra = result.get("extra_sections") or {}
    if isinstance(extra, dict):
        labels = extra.pop("_labels", {}) if isinstance(extra.get("_labels"), dict) else {}
        result["extra_sections"] = extra
        result["extra_section_labels"] = labels

    # 全量清洗：去除控制字符 / 零宽字符，防止 WeasyPrint 在 macOS 崩溃
    result = sanitize_text(result)

    return result


def merge_projects_into_work_experience(resume: dict) -> dict:
    """安全网：把顶层 projects 并入 work_experience（或 internship）的 projects 子字段。

    优先级：
      1. 项目描述/角色中明确出现公司名 → 归入对应段
      2. 项目时间段与某段经历的 period 时间区间重叠 → 归入该段
      3. 仍无法判断 → 按顺序轮询分配，避免全部堆在同一段

    如果 work_experience 与 internship 均为空，则保留顶层 projects 不动。
    该函数应在 optimize 阶段之后调用；如果 LLM 已经正确合并，此函数为 no-op。
    """
    if not isinstance(resume, dict):
        return resume

    top_projects = resume.get("projects") or []
    if not isinstance(top_projects, list) or not top_projects:
        return resume

    work_exp = resume.get("work_experience") or []
    internship = resume.get("internship") or []
    targets = work_exp if work_exp else (internship if internship else None)

    if not targets:
        # 没有任何工作/实习经历：保留顶层 projects 作为兜底
        return resume

    # 确保每个目标 entry 都有 projects 列表
    for entry in targets:
        if not isinstance(entry, dict):
            continue
        if not isinstance(entry.get("projects"), list):
            entry["projects"] = []

    def _period_overlap(p1: str, p2: str) -> bool:
        """粗略判断两个时间段是否有年份重叠。"""
        if not p1 or not p2:
            return False
        years1 = set(re.findall(r"(20\d{2}|19\d{2})", p1))
        years2 = set(re.findall(r"(20\d{2}|19\d{2})", p2))
        return bool(years1 & years2)

    rr_index = 0
    for proj in top_projects:
        if not isinstance(proj, dict):
            continue

        text_blob = " ".join(
            str(proj.get(k, "")) for k in ("name", "role", "description", "achievements")
        )

        # 规则 1：公司名匹配
        assigned = None
        for entry in targets:
            company = (entry.get("company") or "").strip()
            if company and company in text_blob:
                assigned = entry
                break

        # 规则 2：时间区间重叠
        if assigned is None:
            for entry in targets:
                if _period_overlap(proj.get("period", ""), entry.get("period", "")):
                    assigned = entry
                    break

        # 规则 3：轮询兜底
        if assigned is None:
            assigned = targets[rr_index % len(targets)]
            rr_index += 1

        # 避免重复并入：如果嵌套列表中已有同名项目就跳过
        existing_names = {(p.get("name") or "").strip() for p in assigned["projects"] if isinstance(p, dict)}
        if (proj.get("name") or "").strip() in existing_names:
            continue
        assigned["projects"].append(proj)

    # 清空顶层 projects
    resume["projects"] = []
    return resume
