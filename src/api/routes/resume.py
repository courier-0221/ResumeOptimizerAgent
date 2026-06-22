import re

from fastapi import APIRouter, File, HTTPException, UploadFile

from src.common.config import Config
from src.common.logger import logger
from src.api.schemas import OptimizeRequest, ok
from src.api.services import storage
from src.api.services.task_repo import TaskRepo
from src.api.worker.jobs import run_optimize_job
from src.api.worker.task_queue import get_queue

config = Config()
router = APIRouter(tags=["resume"])
repo = TaskRepo(config.DB_PATH)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PDF_MAGIC = b"%PDF"


@router.post("/resume/upload")
async def upload_resume(file: UploadFile = File(...)):
    """上传 PDF 简历，返回 file_id。"""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大，最大 {config.MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )
    if not data.startswith(_PDF_MAGIC):
        raise HTTPException(status_code=400, detail="文件不是有效的 PDF")

    file_id, _ = storage.save_upload(data, file.filename or "resume.pdf")
    logger.info("上传成功 file_id={} size={}", file_id, len(data))
    return ok({"file_id": file_id, "filename": file.filename, "size": len(data)})


@router.post("/resume/optimize")
async def create_optimize_task(req: OptimizeRequest):
    """创建简历优化任务，入队后返回 task_id（异步处理）。"""
    if not storage.get_upload_path(req.file_id):
        raise HTTPException(status_code=404, detail="file_id 不存在，请先上传简历")
    if req.email and not _EMAIL_RE.match(req.email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    task_id = storage.new_task_id()
    repo.create(task_id, req.file_id, req.job_title, req.job_desc or "", req.email or "")

    queue = get_queue()
    queue.enqueue(run_optimize_job, task_id, job_id=task_id, job_timeout=config.TASK_TIMEOUT)

    logger.info("创建任务 task_id={} job_title={}", task_id, req.job_title)
    return ok({"task_id": task_id, "status": "PENDING"})
