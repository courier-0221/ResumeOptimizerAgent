import pdfplumber
import re
import json

def extract_text_from_pdf(pdf_path: str) -> str:
    """从PDF提取全部文本内容"""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text

# ================= 清洗与结构化 =================
def clean_resume(raw):
    result = {}

    # 1. 姓名（第一个非空行，且不是标题）
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    result["name"] = lines[0]

    # 2. 个人信息
    info_match = re.search(r"## 个人信息\n(.+?)\n##", raw, re.DOTALL)
    if info_match:
        info_text = info_match.group(1).replace("\n", "")
        age = re.search(r"年龄：(\d+)", info_text)
        gender = re.search(r"性别：([男女])", info_text)
        residence = re.search(r"居住地：([^目标]+)", info_text)
        target_city = re.search(r"目标城市：([^#\n]+)", info_text)

        result["age"] = age.group(1) if age else ""
        result["gender"] = gender.group(1) if gender else ""
        result["residence"] = residence.group(1) if residence else ""
        result["target_city"] = target_city.group(1) if target_city else ""

    # 3. 联系方式
    phone_match = re.search(r"电话：(\d{11})", raw)
    email_match = re.search(r"电子邮件：([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", raw)
    result["phone"] = phone_match.group(1) if phone_match else ""
    result["email"] = email_match.group(1) if email_match else ""

    # 4. 技能（合并两个技能区块）
    skills_raw = re.findall(r"## 技能\n(.+?)\n##", raw, re.DOTALL)
    skills_set = set()
    for block in skills_raw:
        # 提取普通技能（空格 / 换行分隔）
        words = re.split(r"\s+", block.strip())
        for w in words:
            w = w.strip("·")
            if w and not re.match(r"[语言办公运动能力]|良好|熟练运用", w):
                skills_set.add(w)
        # 提取办公技能
        if "办公技能：" in block:
            office_match = re.search(r"办公技能：(.+?)。", block)
            if office_match:
                for s in re.split(r"[，,]", office_match.group(1)):
                    skills_set.add(s.strip())
    result["skills"] = sorted(skills_set)

    # 5. 爱好
    hobby_match = re.search(r"## 爱好\n(.+?)\n##", raw, re.DOTALL)
    if hobby_match:
        result["hobbies"] = re.split(r"\s+", hobby_match.group(1).strip())

    # 6. 教育背景
    edu_match = re.search(r"## 教育背景\n(.+?)\n##", raw, re.DOTALL)
    if edu_match:
        edu_text = edu_match.group(1).replace("\n", " ")
        school_match = re.search(r"([\u4e00-\u9fa5]+大学)\s*(\d{4}年\s*-\s*\d{4}年)", edu_text)
        major_match = re.search(r"主修：(.+?)(?=\s*##|\s*$)", edu_text)
        result["education"] = {
            "school": school_match.group(1) if school_match else "",
            "period": school_match.group(2) if school_match else "",
            "major": major_match.group(1) if major_match else ""
        }

    # 7. 工作经验
    work_match = re.search(r"## 工作经验\n(.+?)\n## 技能", raw, re.DOTALL)
    if work_match:
        work_text = work_match.group(1).strip()
        # 提取公司 + 职位
        job_title_match = re.search(r"## (.+?)\n", work_text)
        job_title = job_title_match.group(1) if job_title_match else ""
        # 提取时间 + 职责
        duty_match = re.search(r"(\d{4}年.*?-\s*\d{4}年.*?)\n(.+)", work_text, re.DOTALL)
        result["work_experience"] = {
            "title": job_title,
            "period": duty_match.group(1).strip() if duty_match else "",
            "responsibilities": [r.strip("- ") for r in duty_match.group(2).split("- ") if r.strip()] if duty_match else []
        }

    # 8. 自我评价
    self_match = re.search(r"## 自我评价\n(.+)", raw, re.DOTALL)
    result["self_evaluation"] = self_match.group(1).strip() if self_match else ""

    return result

if __name__ == "__main__":
    pdf_path = "./test_1.pdf"  # 替换为你的PDF文件路径
    extracted_text = extract_text_from_pdf(pdf_path)
    resume_json = clean_resume(extracted_text)
    print(json.dumps(resume_json, ensure_ascii=False, indent=2))