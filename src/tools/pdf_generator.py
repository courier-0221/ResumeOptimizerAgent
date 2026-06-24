import os
import subprocess
import sys

from jinja2 import Template


def _weasyprint_env() -> dict:
    """构造 WeasyPrint 子进程环境。

    - G_SLICE/G_DEBUG：规避 macOS 上 GLib slice 分配器与已加载网络/加密栈互扰。
    - macOS 额外注入 DYLD_FALLBACK_LIBRARY_PATH：WeasyPrint 依赖的
      libgobject/pango/cairo 等原生库由 Homebrew 安装在 /opt/homebrew/lib
      （Apple Silicon）或 /usr/local/lib（Intel），但不在 conda Python 子进程的
      默认动态库搜索路径中，否则 cffi dlopen 报
      "cannot load library 'libgobject-2.0-0'"。
    """
    env = os.environ.copy()
    env["G_SLICE"] = "always-malloc"
    env["G_DEBUG"] = "gc-friendly"

    if sys.platform == "darwin":
        brew_libs = [p for p in ("/opt/homebrew/lib", "/usr/local/lib") if os.path.isdir(p)]
        if brew_libs:
            existing = env.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            parts = brew_libs + ([existing] if existing else [])
            env["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)

    return env


# 子进程脚本：在干净的 Python 解释器里调用 WeasyPrint，避免主进程因
# httpx / OpenSSL / CoreFoundation 等先行初始化污染 GLib slice 分配器，
# 进而触发 macOS 上 "GSlice: assertion failed" 崩溃。
_RENDER_SUBPROCESS = r"""
import os, sys
# 双保险：让 GLib 走 malloc，不用 slice 分配器
os.environ.setdefault('G_SLICE', 'always-malloc')
os.environ.setdefault('G_DEBUG', 'gc-friendly')

from weasyprint import HTML

html_path, pdf_path = sys.argv[1], sys.argv[2]
HTML(filename=html_path).write_pdf(pdf_path)
"""


def render_template_to_pdf(
    data: dict,
    template_path: str,
    output_path: str,
    context_key: str = "resume",
) -> str:
    """通用：用 Jinja2 模板 + WeasyPrint 将任意结构化数据渲染为 PDF。

    WeasyPrint 渲染在子进程中执行，规避 macOS 上 GLib slice 分配器与
    主进程中已加载的网络/加密栈的互相干扰。
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板不存在: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        template = Template(f.read())

    html_content = template.render(**{context_key: data})

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 始终把渲染后的 HTML 落盘，便于 WeasyPrint 崩溃时定位问题
    debug_html_path = os.path.splitext(output_path)[0] + ".debug.html"
    with open(debug_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 在子进程中调用 WeasyPrint
    env = _weasyprint_env()

    proc = subprocess.run(
        [sys.executable, "-c", _RENDER_SUBPROCESS, debug_html_path, output_path],
        env=env,
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(
            "WeasyPrint 子进程渲染失败 (returncode="
            f"{proc.returncode}).\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}\n"
            f"渲染用 HTML 已保存至: {debug_html_path}"
        )

    return output_path


def generate_resume_pdf(resume_data: dict, template_path: str, output_path: str) -> str:
    """使用 HTML 模板 + WeasyPrint 生成优化后的简历 PDF。"""
    return render_template_to_pdf(resume_data, template_path, output_path, context_key="resume")


def generate_analysis_report_pdf(report_data: dict, template_path: str, output_path: str) -> str:
    """生成岗位匹配分析报告 PDF。"""
    return render_template_to_pdf(report_data, template_path, output_path, context_key="report")
