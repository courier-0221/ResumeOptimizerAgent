import os

from src.common.config import Config
from src.common.logger import logger
from src.api.services import storage
from src.api.services.mockpdf import write_minimal_pdf
from src.api.services.task_repo import TaskRepo


def run_optimize_job(task_id: str) -> None:
    """队列任务：执行简历优化全流程并（按配置）发送邮件。

    复用现有 ResumeOptimizerAgent，仅把产物输出目录按 task_id 隔离，
    避免并发任务互相覆盖 output/ 下的固定文件名。
    """
    config = Config()
    repo = TaskRepo(config.DB_PATH)

    task = repo.get(task_id)
    if not task:
        logger.error("任务不存在: {}", task_id)
        return

    repo.update_status(task_id, "PROCESSING", "开始处理")
    try:
        out_dir = storage.task_output_dir(task_id)
        config.OUTPUT_DIR = out_dir

        upload_path = storage.get_upload_path(task["file_id"])
        if not upload_path:
            raise FileNotFoundError("简历文件不存在或已被清理")

        if config.AGENT_MODE == "mock":
            logger.info("[mock] 模拟优化任务 {}", task_id)
            resume_pdf = os.path.join(out_dir, "optimized_resume.pdf")
            report_pdf = os.path.join(out_dir, "analysis_report.pdf")
            write_minimal_pdf(resume_pdf, f"Mock Optimized Resume - {task['job_title']}")
            write_minimal_pdf(report_pdf, f"Mock Analysis Report - {task['job_title']}")
        else:
            from src.core import ResumeOptimizerAgent

            agent = ResumeOptimizerAgent(config)
            result = agent.run(upload_path, task["job_title"], task["job_desc"] or "")
            resume_pdf = result.get("resume_pdf") or ""
            report_pdf = result.get("report_pdf") or ""

        email_sent = False
        if task["email"] and config.SEND_EMAIL:
            from src.tools.email_sender import send_optimized_resume

            email_sent = send_optimized_resume(
                to_email=task["email"],
                job_title=task["job_title"],
                resume_pdf=resume_pdf,
                report_pdf=report_pdf,
                config=config,
            )

        repo.update_success(task_id, resume_pdf, report_pdf, email_sent)
        logger.success("任务完成 {} email_sent={}", task_id, email_sent)
    except Exception as e:
        logger.exception("任务失败 {}: {}", task_id, e)
        repo.update_failed(task_id, str(e))
        raise
