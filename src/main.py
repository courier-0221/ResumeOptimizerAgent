import argparse
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import ResumeOptimizerAgent
from src.config import Config
from src.logger import logger, setup_logger


def main():
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python src/main.py -r test/pdf/test_1.pdf -t "Python后端开发工程师"
  python src/main.py -r test/pdf/test_1.pdf -t "算法工程师" -d "要求3年以上机器学习经验，熟悉PyTorch..."
  python src/main.py -r test/pdf/test_1.pdf -t "前端开发" -o output/frontend_resume.pdf
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

    args = parser.parse_args()

    # 先加载配置，再初始化日志（确保日志格式生效）
    config = Config()
    setup_logger(level=config.LOG_LEVEL, log_file=config.LOG_FILE)

    # 校验输入文件
    if not os.path.exists(args.resume):
        logger.error("简历文件不存在: {}", args.resume)
        sys.exit(1)

    if not config.DEEPSEEK_API_KEY or config.DEEPSEEK_API_KEY == "your_api_key_here":
        logger.error("请在 .env 文件中填入 DEEPSEEK_API_KEY")
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
    except Exception as e:
        logger.exception("执行失败: {}", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
