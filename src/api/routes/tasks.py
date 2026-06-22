import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.common.config import Config
from src.api.schemas import ok
from src.api.services.task_repo import TaskRepo

config = Config()
router = APIRouter(tags=["tasks"])
repo = TaskRepo(config.DB_PATH)


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    """查询任务状态（供前端轮询）。"""
    t = repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return ok(
        {
            "task_id": t["task_id"],
            "status": t["status"],
            "progress": t["progress"],
            "error": t["error"],
            "email_sent": bool(t["email_sent"]),
            "created_at": t["created_at"],
            "finished_at": t["finished_at"],
        }
    )


@router.get("/tasks/{task_id}/result")
def get_result(task_id: str):
    """获取任务结果（成功后）。v1 主要靠邮件交付，这里附带下载链接便于验证。"""
    t = repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t["status"] != "SUCCESS":
        raise HTTPException(status_code=409, detail=f"任务尚未完成，当前状态 {t['status']}")

    resume_ok = bool(t["resume_path"] and os.path.exists(t["resume_path"]))
    report_ok = bool(t["report_path"] and os.path.exists(t["report_path"]))
    return ok(
        {
            "email_sent": bool(t["email_sent"]),
            "resume_available": resume_ok,
            "report_available": report_ok,
            # v1版本，先不提供下载oss地址，主要靠邮件交付
            # "resume_download": f"/api/v1/tasks/{task_id}/files/resume" if resume_ok else None,
            # "report_download": f"/api/v1/tasks/{task_id}/files/report" if report_ok else None,
        }
    )


@router.get("/tasks/{task_id}/files/{kind}")
def download_file(task_id: str, kind: str):
    """下载产物 PDF。kind = resume | report。"""
    if kind not in ("resume", "report"):
        raise HTTPException(status_code=400, detail="kind 只能是 resume 或 report")

    t = repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")

    path = t["resume_path"] if kind == "resume" else t["report_path"]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = "optimized_resume.pdf" if kind == "resume" else "analysis_report.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)
