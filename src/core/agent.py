import json
import os
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from src.common.config import Config
from src.common.logger import logger
from src.tools.pdf_parser import extract_text_from_pdf
from src.tools.json_fixer import (
    robust_parse_json,
    normalize_resume_schema,
    merge_projects_into_work_experience,
)
from src.core.prompts.parse import PARSE_PROMPT
from src.core.prompts.analyze import ANALYZE_PROMPT
from src.core.prompts.optimize import OPTIMIZE_PROMPT
from src.tools.pdf_generator import generate_resume_pdf, generate_analysis_report_pdf


class ResumeOptimizerAgent:
    def __init__(self, config: Config = None):
        self.config = config or Config()

        # 深度思考开关 + 思考强度
        extra_body: dict = {
            "thinking": {
                "type": "enabled" if self.config.ENABLE_THINKING else "disabled"
            }
        }
        # 思考强度仅在思考模式开启时下发；关闭时携带 reasoning_effort 无意义
        if self.config.ENABLE_THINKING and self.config.REASONING_EFFORT:
            extra_body["reasoning_effort"] = self.config.REASONING_EFFORT

        logger.info(
            "Config — model: {}, base_url: {}, temperature: {}, max_tokens: {}, log_level: {}, extra_body: {}",
            self.config.MODEL_NAME,
            self.config.DEEPSEEK_BASE_URL,
            self.config.TEMPERATURE,
            self.config.MAX_TOKENS,
            self.config.LOG_LEVEL,
            extra_body
        )

        self.llm = ChatOpenAI(
            model=self.config.MODEL_NAME,
            api_key=self.config.DEEPSEEK_API_KEY,
            base_url=self.config.DEEPSEEK_BASE_URL,
            temperature=self.config.TEMPERATURE,
            max_tokens=self.config.MAX_TOKENS,
            extra_body=extra_body,
        )
        # JSON模式的LLM实例，保证输出合法JSON
        self.llm_json = ChatOpenAI(
            model=self.config.MODEL_NAME,
            api_key=self.config.DEEPSEEK_API_KEY,
            base_url=self.config.DEEPSEEK_BASE_URL,
            temperature=self.config.TEMPERATURE,
            max_tokens=self.config.MAX_TOKENS,
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body=extra_body
        )

    def run(self, pdf_path: str, job_title: str, job_description: str = "") -> dict:
        """执行简历优化全流程，返回包含两份产物路径的字典。"""
        import time

        total_start = time.perf_counter()

        # Stage 1
        logger.info("Stage 1/6 — 解析 PDF 简历: {}", pdf_path)
        t0 = time.perf_counter()
        resume_text = extract_text_from_pdf(pdf_path)
        if not resume_text.strip():
            raise ValueError(f"PDF解析结果为空，请检查文件: {pdf_path}")
        logger.info("Stage 1/6 耗时: {:.2f}s", time.perf_counter() - t0)

        logger.debug("resume_text =\n{}", resume_text)

        # Stage 2
        logger.info("Stage 2/6 — 结构化提取简历内容...")
        t0 = time.perf_counter()
        structured_resume = self._parse_resume(resume_text)
        logger.info("Stage 2/6 耗时: {:.2f}s", time.perf_counter() - t0)

        logger.debug("structured_resume =\n{}",
                       json.dumps(structured_resume, ensure_ascii=False, indent=2))

        # Stage 3
        logger.info("Stage 3/6 — 分析岗位匹配度...")
        t0 = time.perf_counter()
        analysis = self._analyze_match(structured_resume, job_title, job_description)
        logger.info("Stage 3/6 耗时: {:.2f}s", time.perf_counter() - t0)

        logger.debug("analysis =\n{}",
                       json.dumps(analysis, ensure_ascii=False, indent=2))

        # Stage 4
        logger.info("Stage 4/6 — 优化简历内容...")
        t0 = time.perf_counter()
        optimized = self._optimize_resume(
            structured_resume, job_title, job_description, analysis
        )
        logger.info("Stage 4/6 耗时: {:.2f}s", time.perf_counter() - t0)

        logger.debug("optimized =\n{}",
                       json.dumps(optimized, ensure_ascii=False, indent=2))

        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)

        # Stage 5
        logger.info("Stage 5/6 — 生成优化后的简历 PDF...")
        t0 = time.perf_counter()
        resume_output_path = os.path.join(self.config.OUTPUT_DIR, "optimized_resume.pdf")
        resume_template_path = os.path.join(self.config.TEMPLATE_DIR, "resume.html")
        generate_resume_pdf(optimized, resume_template_path, resume_output_path)
        logger.info("Stage 5/6 耗时: {:.2f}s", time.perf_counter() - t0)

        # Stage 6
        logger.info("Stage 6/6 — 生成岗位匹配分析报告 PDF...")
        t0 = time.perf_counter()
        report_output_path = os.path.join(self.config.OUTPUT_DIR, "analysis_report.pdf")
        report_template_path = os.path.join(self.config.TEMPLATE_DIR, "analysis_report.html")
        report_payload = self._build_report_payload(
            analysis=analysis,
            structured_resume=structured_resume,
            optimized=optimized,
            job_title=job_title,
        )
        try:
            generate_analysis_report_pdf(report_payload, report_template_path, report_output_path)
            logger.info("Stage 6/6 耗时: {:.2f}s", time.perf_counter() - t0)
        except Exception as e:
            # 报告 PDF 失败不应阻塞主流程：简历已生成
            logger.warning("分析报告 PDF 生成失败（不影响简历输出）：{}", e)
            report_output_path = ""

        total_elapsed = time.perf_counter() - total_start
        logger.success("完成！优化后的简历已保存至: {}", resume_output_path)
        if report_output_path:
            logger.success("岗位匹配分析报告已保存至: {}", report_output_path)
        logger.success("全流程总耗时: {:.2f}s", total_elapsed)
        return {"resume_pdf": resume_output_path, "report_pdf": report_output_path}

    def _parse_resume(self, resume_text: str) -> dict:
        """Stage 2: 结构化提取"""
        prompt = PARSE_PROMPT.format(resume_text=resume_text)
        response = self.llm_json.invoke([HumanMessage(content=prompt)])
        parsed = robust_parse_json(response.content, llm=self.llm)
        return normalize_resume_schema(parsed)

    def _analyze_match(
        self, structured_resume: dict, job_title: str, job_description: str
    ) -> dict:
        """Stage 3: 匹配度分析"""
        if not job_description:
            job_description = f"目标岗位为{job_title}，请根据该岗位的通用要求进行分析。"

        prompt = ANALYZE_PROMPT.format(
            job_title=job_title,
            job_description=job_description,
            structured_resume=json.dumps(structured_resume, ensure_ascii=False, indent=2),
        )
        response = self.llm_json.invoke([HumanMessage(content=prompt)])
        return robust_parse_json(response.content, llm=self.llm)

    def _optimize_resume(
        self,
        structured_resume: dict,
        job_title: str,
        job_description: str,
        analysis: dict,
    ) -> dict:
        """Stage 4: 简历内容优化"""
        if not job_description:
            job_description = f"目标岗位为{job_title}"

        prompt = OPTIMIZE_PROMPT.format(
            job_title=job_title,
            job_description=job_description,
            structured_resume=json.dumps(structured_resume, ensure_ascii=False, indent=2),
            analysis_result=json.dumps(analysis, ensure_ascii=False, indent=2),
        )
        response = self.llm_json.invoke([HumanMessage(content=prompt)])
        optimized = robust_parse_json(response.content, llm=self.llm)
        optimized = normalize_resume_schema(optimized)
        # 安全网：若 LLM 未把 projects 全部并入 work_experience，则在此处兜底合并
        optimized = merge_projects_into_work_experience(optimized)
        return optimized

    def _build_report_payload(
        self,
        analysis: dict,
        structured_resume: dict,
        optimized: dict,
        job_title: str,
    ) -> dict:
        """组装 analysis_report.html 渲染所需的上下文。"""
        # 优先从优化结果取候选人姓名，回退到原简历
        candidate_name = (
            (optimized.get("basic_info") or {}).get("name")
            or (structured_resume.get("basic_info") or {}).get("name")
            or ""
        )
        return {
            "candidate_name": candidate_name,
            "job_title": job_title,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "overall_strategy": analysis.get("overall_strategy") or "",
            "gap_report": analysis.get("gap_report") or {},
        }
