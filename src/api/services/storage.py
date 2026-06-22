import os
import re
import uuid

from src.common.config import Config

config = Config()

_FILE_ID_RE = re.compile(r"^f_[0-9a-f]{16}$")
_TASK_ID_RE = re.compile(r"^t_[0-9a-f]{16}$")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def new_file_id() -> str:
    return "f_" + uuid.uuid4().hex[:16]


def new_task_id() -> str:
    return "t_" + uuid.uuid4().hex[:16]


def save_upload(data: bytes, original_name: str = "resume.pdf") -> tuple[str, str]:
    """保存上传的简历，返回 (file_id, path)。文件名用随机 id，避免路径穿越。"""
    _ensure_dir(config.UPLOAD_DIR)
    file_id = new_file_id()
    path = os.path.join(config.UPLOAD_DIR, file_id + ".pdf")
    with open(path, "wb") as f:
        f.write(data)
    return file_id, path


def get_upload_path(file_id: str) -> str:
    """根据 file_id 返回简历路径；非法 id 或文件不存在返回空串。"""
    if not file_id or not _FILE_ID_RE.match(file_id):
        return ""
    path = os.path.join(config.UPLOAD_DIR, file_id + ".pdf")
    return path if os.path.exists(path) else ""


def task_output_dir(task_id: str) -> str:
    """返回按 task_id 隔离的产物目录（防止并发任务互相覆盖）。"""
    if not _TASK_ID_RE.match(task_id):
        raise ValueError(f"非法 task_id: {task_id}")
    path = os.path.join(config.TASK_DATA_DIR, task_id)
    _ensure_dir(path)
    return path
