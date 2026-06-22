"""模拟微信小程序前端，对后端接口做端到端交互测试。

流程：生成测试简历 PDF -> 上传 -> 创建优化任务 -> 轮询状态 -> 取结果 -> 下载产物。

用法：
    # === 模式 A：mock 自测（无 Redis / 无 LLM 密钥，仅验证链路）===
    # 1) 先启动后端：
    #    ./start.sh start all
    # 2) 再运行本脚本：
    #    python tests/api/test_flow.py
    #
    # === 模式 B：真实简历触发流程（用真实 PDF + 真实 Agent）===
    # 1) 启动后端（需配好 DEEPSEEK_API_KEY；如需邮件则配好 SMTP）：
    #    ./start.sh start all
    # 2) 指定真实简历 PDF 运行：
    #    RESUME_PDF=/path/to/my_resume.pdf \
    #        JOB_TITLE="高级Python工程师" JOB_DESC="..." \
    #        python tests/api/test_flow.py
    #
    # 可选环境变量：
    #    BASE_URL    后端地址（默认 http://127.0.0.1:8000）
    #    RESUME_PDF  真实简历 PDF 路径；留空则生成最小 mock PDF
    #    JOB_TITLE   目标岗位名称（默认 Python后端开发工程师）
    #    JOB_DESC    目标岗位 JD（默认内置一段示例）
    #    TEST_EMAIL  填写后将真实触发邮件发送（需后端 SEND_EMAIL=true 且配好 SMTP）
"""

import os
import sys
import tempfile
import time

# 项目根目录入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests

from src.api.services.mockpdf import write_minimal_pdf

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TEST_EMAIL = os.getenv("TEST_EMAIL", "")
RESUME_PDF = os.getenv("RESUME_PDF", "").strip()
JOB_TITLE = os.getenv("JOB_TITLE", "Python后端开发工程师")
JOB_DESC = os.getenv(
    "JOB_DESC",
    "要求3年以上后端经验，熟悉 FastAPI、Redis、消息队列。",
)


def _check(resp, label):
    print(f"[{label}] HTTP {resp.status_code}")
    try:
        body = resp.json()
    except Exception:
        print("  非 JSON 响应:", resp.text[:200])
        raise SystemExit(1)
    print("  body:", body)
    return body


def main():
    # 0. 健康检查
    r = requests.get(f"{BASE}/health", timeout=10)
    _check(r, "health")

    # 1. 准备简历 PDF：
    #    - 指定 RESUME_PDF -> 使用真实简历（真实触发流程）
    #    - 未指定       -> 生成最小 mock PDF（仅验证链路）
    if RESUME_PDF:
        if not os.path.isfile(RESUME_PDF):
            print(f"RESUME_PDF 不存在: {RESUME_PDF}")
            raise SystemExit(1)
        pdf_path = RESUME_PDF
        upload_name = os.path.basename(RESUME_PDF)
        print(f"\n使用真实简历: {pdf_path}")
    else:
        pdf_path = tempfile.mktemp(suffix=".pdf")
        write_minimal_pdf(pdf_path, "Test Resume - Zhang San")
        upload_name = "resume.pdf"
        print(f"\n生成 mock 测试简历: {pdf_path}")

    # 2. 上传
    with open(pdf_path, "rb") as f:
        r = requests.post(
            f"{BASE}/api/v1/resume/upload",
            files={"file": (upload_name, f, "application/pdf")},
            timeout=30,
        )
    body = _check(r, "upload")
    file_id = body["data"]["file_id"]

    # 3. 创建优化任务
    payload = {
        "file_id": file_id,
        "job_title": JOB_TITLE,
        "job_desc": JOB_DESC,
        "email": TEST_EMAIL,
    }
    r = requests.post(f"{BASE}/api/v1/resume/optimize", json=payload, timeout=60)
    body = _check(r, "optimize")
    task_id = body["data"]["task_id"]

    # 4. 轮询状态
    print("\n开始轮询任务状态...")
    final = None
    for i in range(150):
        r = requests.get(f"{BASE}/api/v1/tasks/{task_id}", timeout=10)
        data = r.json()["data"]
        print(f"  poll #{i}: status={data['status']} progress={data.get('progress')}")
        if data["status"] in ("SUCCESS", "FAILED"):
            final = data
            break
        time.sleep(2)

    if not final:
        print("轮询超时")
        raise SystemExit(1)
    if final["status"] == "FAILED":
        print("任务失败:", final.get("error"))
        raise SystemExit(1)

    # 5. 取结果
    r = requests.get(f"{BASE}/api/v1/tasks/{task_id}/result", timeout=10)
    body = _check(r, "result")

    # 6. 下载产物并校验是 PDF
    os.makedirs(f"output/{task_id}", exist_ok=True)
    for kind in ("resume", "report"):
        rr = requests.get(f"{BASE}/api/v1/tasks/{task_id}/files/{kind}", timeout=30)
        if rr.status_code == 200:
            out = os.path.join(f"output/{task_id}", f"{task_id}_{kind}.pdf")
            with open(out, "wb") as f:
                f.write(rr.content)
            is_pdf = rr.content[:4] == b"%PDF"
            print(f"  下载 {kind}: {out} ({len(rr.content)} bytes, pdf={is_pdf})")
        else:
            print(f"  下载 {kind} 失败: HTTP {rr.status_code}")

    print("\n✅ 端到端链路验证通过")


if __name__ == "__main__":
    main()
