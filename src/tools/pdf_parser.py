import pdfplumber


def _detect_columns(words, page_width, gap_threshold_ratio=0.05):
    """检测页面是否为多栏布局，返回分栏的x坐标分界点列表。
    
    通过分析所有词的x坐标分布，寻找明显的空白间隙来判断分栏。
    """
    if not words:
        return []

    gap_threshold = page_width * gap_threshold_ratio

    # 收集所有词的左右边界
    intervals = sorted([(w["x0"], w["x1"]) for w in words], key=lambda x: x[0])

    # 合并重叠区间，找出文本覆盖的x轴范围
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + gap_threshold:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # 如果只有一个连续区域，说明是单栏
    if len(merged) <= 1:
        return []

    # 找到栏间的分界点（取间隙中点）
    split_points = []
    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        # 只有间隙足够大才视为分栏（至少页面宽度的3%）
        if (gap_end - gap_start) > page_width * 0.03:
            split_points.append((gap_start + gap_end) / 2)

    return split_points


def _extract_column_text(words, x_start, x_end):
    """提取某一栏范围内的文字，按y坐标从上到下、同行x从左到右排列。"""
    col_words = [w for w in words if w["x0"] >= x_start and w["x1"] <= x_end]
    if not col_words:
        return ""

    # 按y坐标分行（y坐标差距小于字体高度的一半视为同一行）
    col_words.sort(key=lambda w: (w["top"], w["x0"]))

    lines = []
    current_line = [col_words[0]]
    for w in col_words[1:]:
        # 判断是否同一行：top坐标差距小于行高的一半
        line_height = current_line[0].get("height", 12)
        if abs(w["top"] - current_line[0]["top"]) < line_height * 0.6:
            current_line.append(w)
        else:
            current_line.sort(key=lambda x: x["x0"])
            lines.append(" ".join(item["text"] for item in current_line))
            current_line = [w]

    if current_line:
        current_line.sort(key=lambda x: x["x0"])
        lines.append(" ".join(item["text"] for item in current_line))

    return "\n".join(lines)


def _extract_page_with_columns(page):
    """智能提取页面文本：自动检测多栏布局并按栏分别提取。"""
    words = page.extract_words(keep_blank_chars=True, x_tolerance=2, y_tolerance=2)
    if not words:
        return page.extract_text() or ""

    page_width = page.width
    split_points = _detect_columns(words, page_width)

    # 单栏布局：直接用默认提取
    if not split_points:
        return page.extract_text() or ""

    # 多栏布局：按栏分别提取，然后依次拼接
    boundaries = [0] + split_points + [page_width]
    column_texts = []
    for i in range(len(boundaries) - 1):
        col_text = _extract_column_text(words, boundaries[i], boundaries[i + 1])
        if col_text.strip():
            column_texts.append(col_text.strip())

    return "\n\n".join(column_texts)


def extract_text_from_pdf(pdf_path: str) -> str:
    """从PDF提取全部文本内容，自动处理多栏布局"""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = _extract_page_with_columns(page)
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)
