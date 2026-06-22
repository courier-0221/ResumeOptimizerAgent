import argparse
import sys
import os

# 确保项目根目录在 path 中（本文件位于 test/core/ 下，需上溯两级到工程根）
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

from src.core import ResumeOptimizerAgent
from src.common.config import Config
from src.common.logger import logger, setup_logger
from src.tools.email_sender import send_optimized_resume, validate_smtp_config


def main():
    parser = argparse.ArgumentParser(
        description="测试 core 中 ResumeOptimizerAgent.run 的完整流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python test/core/test_agent.py -r test/pdf/test_1.pdf -t "Python后端开发工程师"
  python test/core/test_agent.py -r test/pdf/test_1.pdf -t "算法工程师" -d "要求3年以上机器学习经验，熟悉PyTorch..."
  python test/core/test_agent.py -r test/pdf/test_1.pdf -t "前端开发" -o output/frontend_resume.pdf
  python test/core/test_agent.py -r test/pdf/test_1.pdf -t "前端开发" --email-to hr@example.com
        """,
    )
    parser.add_argument(
        "--resume", "-r", required=True, help="简历PDF文件路径"
    )
    parser.add_argument(
        "--job-title", "-t", required=True, help="目标岗位名称"
    )
    parser.add_argument(
        "--job-desc", "-d", default="", help="岗位描述/要求文本（选填）"
    )
    parser.add_argument(
        "--output", "-o", default="", help="输出简历PDF路径（默认output/optimized_resume.pdf；分析报告与其同目录）"
    )
    parser.add_argument(
        "--email-to",
        default="",
        help="收件人邮箱；多个收件人可用英文逗号或分号分隔。不填则不发送邮件",
    )

    args = parser.parse_args()

    # 先加载配置，再初始化日志（确保日志格式生效）
    config = Config()
    setup_logger(level=config.LOG_LEVEL, log_file=config.LOG_FILE)

    # 默认产物输出到顶层 output/（绝对路径，不依赖运行时 cwd）
    config.OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

    # 校验输入文件
    if not os.path.exists(args.resume):
        logger.error("简历文件不存在: {}", args.resume)
        sys.exit(1)

    if not config.DEEPSEEK_API_KEY or config.DEEPSEEK_API_KEY == "your_api_key_here":
        logger.error("请在 .env 文件中填入 DEEPSEEK_API_KEY")
        sys.exit(1)

    email_enabled = bool(args.email_to)
    if args.email_to:
        try:
            validate_smtp_config(config)
        except ValueError as e:
            logger.error("{}", e)
            sys.exit(1)

    # 如果指定了输出路径则覆盖配置
    if args.output:
        config.OUTPUT_DIR = os.path.dirname(args.output) or "output"

    agent = ResumeOptimizerAgent(config)

    try:
        result = agent.run(
            pdf_path=args.resume,
            job_title=args.job_title,
            job_description=args.job_desc,
        )
        resume_path = result.get("resume_pdf", "")
        report_path = result.get("report_pdf", "")

        if args.output:
            # 如果用户指定了不同的输出路径，移动简历文件
            import shutil
            if resume_path and resume_path != args.output:
                os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
                shutil.move(resume_path, args.output)
                resume_path = args.output

        logger.success("简历输出: {}", resume_path)
        if report_path:
            logger.success("分析报告: {}", report_path)

        if email_enabled:
            send_optimized_resume(
                to_email=args.email_to,
                job_title=args.job_title,
                resume_pdf=resume_path,
                report_pdf=report_path,
                config=config,
            )
    except Exception as e:
        logger.exception("执行失败: {}", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
