OPTIMIZE_PROMPT = """你是一位顶级简历改写专家。根据【匹配分析结果】对【原始简历】进行**有据可依**的重写，输出一份能直接渲染成 PDF 的结构化 JSON。

## 目标岗位
{job_title}

## 岗位描述
{job_description}

## 原始简历（结构化 JSON，唯一事实来源）
{structured_resume}

## 匹配分析结果（改写指令，必须遵循）
{analysis_result}

---

## 改写原则（按优先级排序）

### A. 真实性铁律（违反任意一条即视为失败）
1. **禁止虚构经历**：不得新增原简历中不存在的公司、项目、岗位、证书、学历。
2. **禁止虚增技能**：`skill_categories` 与 `skills` 中的每一条技能名，必须能在以下任一来源中找到对应记录：原简历 `skills` 字段、`projects[].tech_stack`、`work_experience[].description`、`internship[].description`（同义词可合并，但不能添加上述来源均未出现过的技术）。若原简历 `skills` 为空或过于简略，**主动从上述经历中提炼**候选人实际使用过的工具/框架/语言，按类别填充 `skill_categories`。
3. **禁止伪造数据**：原简历里没有的具体数字（百分比、人数、金额）不得编造。原简历里**已有**的数据可以保留并润色措辞。
4. **禁止编造正在进行的事**：不得添加"正在自学 XX"、"正在搭建 XX 项目"等原简历未声明的内容。

### B. 改写动作（在 A 的前提下尽量发挥）
1. 重写各板块 `description`，规则如下：
   - **`work_experience.description`（工作经历级别）**：用 **3 句话左右**高度概括这段工作的主要职责与贡献，来源优先取自原简历该段工作经历的"主要工作"等描述字段，再结合该段下属项目的共同技术/业务主题提炼；**不要**逐条展开 STAR 故事，保持精简。
   - **`projects.intro`（项目描述）**：用 1-2 句话介绍该项目"是做什么的"（业务背景 / 目标 / 候选人负责的模块）。原简历若无类似描述，需从项目名称、技术栈、贡献内容中主动提炼，**不得虚构**。
   - **`projects.description`（主要贡献）与 `internship.description`**：列举该项目中**几条最重要**的个人贡献（建议 2-4 条），每条以动词开头、控制在 20-45 字以内做内容精简，能量化则量化。
2. 将岗位关键词（来自 `analysis_result.keyword_injection`）**只在候选人真实经历能合理承接的位置**自然融入。
3. 重写 `self_evaluation` 使其符合 `analysis_result.section_rewrite_plan.self_evaluation.tone`，长度 **60-100 字，3 句话左右**。
   - 若原简历的"兴趣爱好"中有**对目标岗位有正向价值**的项（如：写作 → 文档/沟通能力；运动 → 抗压；摄影/绘画 → 审美/细节），可用**最多一句话**融入自我评价；与岗位无关的爱好一律舍弃，**不要单独成段**。
4. 根据 `analysis_result.skills_categorization` 把扁平 skills 重组为分类结构（详见下方 schema）。
5. 教育板块按 `analysis_result.education.highlight_courses / highlight_honors` 筛选并排序。
6. 对 `analysis_result.sections_to_drop` 中的板块进行精简或删除。
7. **求职意向**只保留在 `basic_info.job_intention` 字段中（PDF 头部不再单独大字展示），**不要**再做成独立段落。

### B-2. 项目经历并入工作经历（强制规则）
最终简历**只保留"工作经历"一栏**，不再单独出现"项目经验"板块。原简历中的所有 `projects` 必须按以下规则全部并入 `work_experience` 的子字段 `projects` 中：

1. **归属判定**：依次检查每个项目，按下列优先级判断它属于哪段工作经历：
   - (a) 项目描述/角色中明确出现某段工作经历的公司名、部门名 → 直接归入该段；
   - (b) 项目的 `period` 与某段 `work_experience.period` 时间区间重叠（或落在其中）→ 归入该段；
   - (c) 仍无法判断且 `work_experience` 非空 → **随机但稳定地**分配到某一段（建议按项目顺序依次分配，避免全部堆到同一段）。
2. **没有 work_experience 时**：若 `work_experience` 为空但 `internship` 非空，则按同样规则把 projects 并入 `internship[].projects`；若两者都为空，才允许保留顶层 `projects` 数组。
3. **每段 work_experience 必须给出 `description`**：写 **3 句话左右**的整合段落（约 2 行）——首句源自原简历该段"主要工作"或职责概述（若有），其余句从该段下属项目提炼核心技术/贡献并加以精简；各句自然衔接，读起来像一段完整叙述，**不加 bullet 前缀，不要出现空洞的"负责 XX 工作"套话**。`summary` 字段输出空字符串即可。
4. **顶层 `projects` 字段输出为 `[]`**（除非第 2 条的最后兜底情况成立）。
5. 合并后，每个 work_experience 内部嵌套的项目仍要遵守"真实性铁律"，项目名、技术栈、数据不得虚构。

### C. 格式要求（影响 PDF 排版，必须严格遵守）
1. **`description` 字段格式**：
   - **`work_experience.description`**：纯文本，3 句左右的整合段落（约 2 行），**不加 `• ` 前缀**，句与句之间用中文句号衔接，内容涵盖职责定位与核心技术贡献。
   - **`projects.description`（主要贡献）/ `internship.description`**：bullet 列表，每条以 `• ` 开头（U+2022 + 空格），多条之间用单个 `\\n` 分隔，列 2-4 条最重要的贡献，每条 20-45 字、以动词开头、内容精简。
2. `self_evaluation` 不要用 bullet，写成连贯的段落。
3. 所有字符串不要包含多余的前后空格或制表符。

---

## 输出 JSON Schema（顶层 key 必须齐全，缺一不可）

{{
    "basic_info": {{
        "name": "", "gender": "", "age": "",
        "phone": "", "email": "", "location": "",
        "job_intention": "", "expected_salary": "", "availability": "",
        "linkedin": "", "personal_site": "", "github": "", "portfolio": ""
    }},
    "self_evaluation": "60-100字的连贯段落（3句话左右），紧扣目标岗位定位",
    "education": [
        {{
            "school": "", "degree": "", "major": "", "period": "",
            "gpa": "",
            "courses": ["按岗位相关度排序后保留 3-6 门"],
            "honors": ["保留最有说服力的 1-3 项"]
        }}
    ],
    "work_experience": [
        {{
            "company": "（必须与原简历一致）",
            "position": "",
            "period": "",
            "summary": "",
            "description": "3 句左右整合段落（约 2 行）：首句来自原简历"主要工作"或职责概述，其余句精简提炼项目核心技术/贡献，自然衔接，无 bullet 前缀",
            "projects": [
                {{
                    "name": "（必须与原简历 projects 中的项目名一致）",
                    "role": "",
                    "period": "",
                    "intro": "1-2句话介绍该项目是做什么的（业务背景/目标），原简历无则从项目内容提炼，不得虚构",
                    "description": "主要贡献，2-4条精简要点：• ...\\n• ...",
                    "tech_stack": ["仅用于专业技能板块的技能溯源，PDF 项目条目中不再展示，仍只能列真实技术"],
                    "achievements": "可选：有可量化/亮点成果时用1句话展示，无则输出空字符串"
                }}
            ]
        }}
    ],
    "internship": [
        {{
            "company": "", "position": "", "period": "",
            "summary": "若有项目并入，同样给一句 25-50 字总结，否则可留空",
            "description": "• ...\\n• ...",
            "projects": []
        }}
    ],
    "projects": [],
    "skill_categories": [
        {{"category": "编程语言", "items": ["Python（来自 skills / 项目描述）"]}},
        {{"category": "推理框架与工具", "items": ["TensorRT、ONNXRuntime（来自 tech_stack）"]}},
        {{"category": "系统与底层", "items": ["Linux多线程/进程开发（来自 skills / 描述）"]}},
        {{"category": "性能调优", "items": ["perf、gdb、mmap（来自 tech_stack / 描述）"]}}
    ],
    /* skill_categories 填写规则：
       - 分类名与数量按岗位需求灵活调整（建议 3-6 个分类）；
       - items 来源：原简历 skills 字段 + 所有 projects[].tech_stack + work_experience 描述中出现的技术名词；
       - 同一技术在多个来源出现时只列一次；
       - 禁止添加任何上述来源均未出现过的技术。
    */
    "skills": ["与 skill_categories 所有 items 合并去重后的扁平列表，用作兜底"],
    "language_ability": {{"mandarin": "", "english": "", "other": ""}},
    "certifications": ["原简历中真实存在的证书"],
    "awards": ["原简历中真实存在的奖项"],
    "extra_sections": {{}}
}}

### extra_sections 规则
- **必须输出为空对象 `{{}}`**。`hobbies` / `target_city` / `self_directed_learning` / `training_experience` 等板块一律不要输出。
- 兴趣爱好中真正能为目标岗位加分的（如：写作、运动）请精简后融入 `self_evaluation`，不要单独成段。
- 不得借此字段塞入原简历不存在的内容。

---

## 输出前自检
- [ ] 顶层 13 个 key 全部存在？
- [ ] `extra_sections` 是 `{{}}`（空对象）？
- [ ] `work_experience.description` 是 3 句左右整合段落（无 bullet 前缀），自然衔接？
- [ ] 每个 `projects` 都填了 `intro`（项目描述），且 `description`（主要贡献）是 `• ` 开头、2-4 条精简要点？`internship.description` 同为 `• ` 开头的多行格式？
- [ ] 没有虚构公司、项目、技能、数据？
- [ ] `skill_categories` 的 items 全部来自原简历 skills 字段或项目/工作经历的 tech_stack/描述，没有凭空添加？
- [ ] 求职意向只出现在 `basic_info.job_intention`？
- [ ] 原简历 `projects` 中的**每一个项目**都已并入某段 `work_experience.projects`（或在没有工作经历时并入 internship），顶层 `projects` 为 `[]`？
- [ ] 每段 `work_experience` 都有 25-50 字的 `summary`？

严格输出合法 JSON，禁止 markdown 代码块或任何解释文字。
"""
