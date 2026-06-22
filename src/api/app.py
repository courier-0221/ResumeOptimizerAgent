import os
import sys

# 确保项目根目录在 path 中（支持 `uvicorn src.api.app:app` 启动）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.common.config import Config
from src.common.logger import logger, setup_logger
from src.api.routes import resume, tasks
from src.api.services.task_repo import TaskRepo

config = Config()
setup_logger(level=config.LOG_LEVEL, log_file=config.LOG_FILE)

# 启动时初始化数据库与本地目录
TaskRepo(config.DB_PATH)
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.makedirs(config.TASK_DATA_DIR, exist_ok=True)

app = FastAPI(title="Resume Optimizer API", version="1.0.0")

# 小程序前端跨域（v1 放开，上线时按需收紧到具体来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "参数校验失败", "data": {"errors": str(exc.errors())}},
    )


app.include_router(resume.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"code": 0, "message": "ok", "data": {"status": "up", "agent_mode": config.AGENT_MODE}}


logger.info(
    "API 就绪 — queue_backend={}, queue_async={}, agent_mode={}, send_email={}",
    config.QUEUE_BACKEND,
    config.QUEUE_ASYNC,
    config.AGENT_MODE,
    config.SEND_EMAIL,
)
