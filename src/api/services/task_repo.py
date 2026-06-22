import os
import sqlite3
from datetime import datetime
from typing import Optional


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskRepo:
    """任务记录读写（SQLite）。每次操作新建连接，进程/线程安全。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def init_db(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id      TEXT PRIMARY KEY,
                    file_id      TEXT NOT NULL,
                    job_title    TEXT NOT NULL,
                    job_desc     TEXT,
                    email        TEXT,
                    status       TEXT NOT NULL,
                    progress     TEXT,
                    resume_path  TEXT,
                    report_path  TEXT,
                    email_sent   INTEGER DEFAULT 0,
                    error        TEXT,
                    created_at   TEXT,
                    finished_at  TEXT
                )
                """
            )

    def create(self, task_id: str, file_id: str, job_title: str, job_desc: str, email: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO tasks (task_id, file_id, job_title, job_desc, email, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (task_id, file_id, job_title, job_desc, email, "PENDING", _now()),
            )

    def get(self, task_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    def update_status(self, task_id: str, status: str, progress: Optional[str] = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE tasks SET status = ?, progress = COALESCE(?, progress) WHERE task_id = ?",
                (status, progress, task_id),
            )

    def update_success(self, task_id: str, resume_path: str, report_path: str, email_sent: bool) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE tasks SET status = 'SUCCESS', progress = '处理完成', "
                "resume_path = ?, report_path = ?, "
                "email_sent = ?, finished_at = ? WHERE task_id = ?",
                (resume_path, report_path, 1 if email_sent else 0, _now(), task_id),
            )

    def update_failed(self, task_id: str, error: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE tasks SET status = 'FAILED', progress = '处理失败', "
                "error = ?, finished_at = ? WHERE task_id = ?",
                ((error or "")[:1000], _now(), task_id),
            )
