import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable, Union

from src.common.config import Config
from src.common.logger import logger


def _split_recipients(to_email: Union[str, Iterable[str]]) -> list[str]:
    if isinstance(to_email, str):
        recipients = to_email.replace(";", ",").split(",")
    else:
        recipients = list(to_email)
    return [recipient.strip() for recipient in recipients if recipient and recipient.strip()]


def validate_smtp_config(config: Config) -> None:
    """校验 SMTP 必填配置，发送前或启动前预检查都可复用。"""
    missing = []
    if not config.SMTP_HOST:
        missing.append("SMTP_HOST")
    if not config.SMTP_PORT:
        missing.append("SMTP_PORT")
    if not config.SMTP_FROM:
        missing.append("SMTP_FROM")
    if not config.SMTP_USERNAME:
        missing.append("SMTP_USERNAME")
    if not config.SMTP_PASSWORD:
        missing.append("SMTP_PASSWORD")

    if missing:
        raise ValueError(
            "邮件配置缺失: "
            f"{', '.join(missing)}。请在 .env 中配置 SMTP_HOST、SMTP_USERNAME、"
            "SMTP_PASSWORD、SMTP_FROM 等邮件参数；如果暂时不需要发邮件，请去掉 --email-to。"
        )


def _attach_file(message: EmailMessage, file_path: str) -> None:
    if not file_path:
        return
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"邮件附件不存在: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"邮件附件不是文件: {file_path}")

    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"
    maintype, subtype = content_type.split("/", 1)

    with open(file_path, "rb") as f:
        message.add_attachment(
            f.read(),
            maintype=maintype,
            subtype=subtype,
            filename=os.path.basename(file_path),
        )


def send_resume_email(
    to_email: Union[str, Iterable[str]],
    subject: str,
    body: str,
    attachment_paths: list[str],
    config: Config,
) -> None:
    """发送优化后的简历邮件，可附带分析报告。"""
    validate_smtp_config(config)

    recipients = _split_recipients(to_email)
    if not recipients:
        raise ValueError("收件人邮箱不能为空")
    if not attachment_paths:
        raise ValueError("邮件附件不能为空")

    message = EmailMessage()
    message["From"] = config.SMTP_FROM
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    for file_path in attachment_paths:
        _attach_file(message, file_path)

    context = ssl.create_default_context()
    logger.info("正在发送邮件至: {}", ", ".join(recipients))

    if config.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=30,
            context=context,
        ) as smtp:
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
            if config.SMTP_USE_TLS:
                smtp.starttls(context=context)
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            smtp.send_message(message)

    logger.success("邮件发送成功: {}", ", ".join(recipients))


def send_optimized_resume(
    to_email: Union[str, Iterable[str]],
    job_title: str,
    resume_pdf: str,
    report_pdf: str,
    config: Config,
) -> bool:
    """拼装并发送「优化后的简历」邮件，CLI 与 worker 共用。

    会自动挑选存在的 PDF 作为附件（简历必带、分析报告可选），并生成统一的
    标题与正文。若没有任何可用附件则跳过发送并返回 False。

    返回:
        True 表示已发送，False 表示无可用附件而跳过。
    """
    attachments = [p for p in (resume_pdf, report_pdf) if p and os.path.exists(p)]
    if not attachments:
        logger.warning("无可用附件，跳过邮件发送")
        return False
    if not (resume_pdf and os.path.exists(resume_pdf)):
        logger.warning("简历文件不存在，邮件将只附带分析报告")

    send_resume_email(
        to_email=to_email,
        subject=f"{job_title} - 优化后的简历",
        body="您好，附件是优化后的简历 PDF，请查收。",
        attachment_paths=attachments,
        config=config,
    )
    return True
