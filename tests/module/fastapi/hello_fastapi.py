"""极简 FastAPI + Uvicorn 体验示例。

运行方式（任选其一）：
    1) 直接运行脚本：     python hello_fastapi.py
    2) 用 uvicorn 命令：  uvicorn hello_fastapi:app --reload --prot 8888

启动后访问：
    http://127.0.0.1:8888/            -> 首页
    http://127.0.0.1:8888/hello/世界  -> 路径参数
    http://127.0.0.1:8888/add?a=1&b=2 -> 查询参数
    http://127.0.0.1:8888/docs        -> 自动生成的交互式 API 文档
"""

from fastapi import FastAPI

app = FastAPI(title="Hello FastAPI Demo")


@app.get("/")
def index():
    return {"message": "Hello FastAPI 🚀"}


@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"你好，{name}！"}


@app.get("/add")
def add(a: int, b: int):
    return {"a": a, "b": b, "sum": a + b}


if __name__ == "__main__":
    import uvicorn

    # 直接传入 app 对象，避免 reload 子进程按导入路径再次 import（test 与标准库同名会冲突）
    uvicorn.run(app, host="127.0.0.1", port=8888)
