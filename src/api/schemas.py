from typing import Optional

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    """创建优化任务的请求体。"""

    file_id: str = Field(min_length=1, description="上传简历返回的 file_id")
    job_title: str = Field(min_length=1, description="目标岗位名称")
    job_desc: str = Field(default="", description="岗位描述/要求（选填）")
    email: Optional[str] = Field(default="", description="收件邮箱（v1 通过邮件交付结果）")


def ok(data=None, message: str = "ok") -> dict:
    """统一成功响应。"""
    return {"code": 0, "message": message, "data": data}
