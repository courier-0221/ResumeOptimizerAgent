import os


def write_minimal_pdf(path: str, title: str) -> str:
    """生成一个最小但合法的 PDF 文件，用于 mock 模式与测试。

    自包含、无外部依赖（不依赖 weasyprint/reportlab），方便在没有系统库
    或 LLM 密钥的情况下验证整条 web 链路。
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # 转义 PDF 文本中的特殊字符
    safe = title.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    text = f"BT /F1 20 Tf 72 760 Td ({safe}) Tj ET".encode("latin-1", "replace")

    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\n" % len(text) + text + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]

    buf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf += b"%d 0 obj\n" % i + obj + b"\nendobj\n"

    xref_pos = len(buf)
    count = len(objs) + 1
    buf += b"xref\n0 %d\n" % count
    buf += b"0000000000 65535 f \n"
    for off in offsets:
        buf += b"%010d 00000 n \n" % off
    buf += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF" % (count, xref_pos)

    with open(path, "wb") as f:
        f.write(buf)
    return path
