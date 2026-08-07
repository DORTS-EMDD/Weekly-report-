"""Shared PDF exporter; importing this module never creates a report."""

import re
from html import escape
from io import BytesIO


def markdown_to_pdf_bytes(md: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    for style_name in ("Title", "Heading1", "Heading2", "Heading3", "BodyText"):
        styles[style_name].fontName = "MSung-Light"
        styles[style_name].leading = max(styles[style_name].leading, 16)
    styles["BodyText"].fontSize = 10.5

    story = []
    for raw_line in md.splitlines():
        line = raw_line.strip()
        if not line or line == "---":
            story.append(Spacer(1, 8))
            continue
        if line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(escape(line[3:]), styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(escape(line[4:]), styles["Heading3"]))
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            line = re.sub(r"\[(.+?)\]\((https?://[^\)]+)\)", r"\1：\2", line)
            story.append(Paragraph(escape(line), styles["BodyText"]))
    doc.build(story)
    return buffer.getvalue()


def try_markdown_to_pdf_bytes(md: str) -> bytes | None:
    try:
        return markdown_to_pdf_bytes(md)
    except ModuleNotFoundError:
        print("[WARN] reportlab 未安裝，略過 PDF 附件")
        return None


def pdf_rich_text(text: str, cjk_font: str, latin_font: str) -> str:
    prepared = (
        (text or "")
        .replace("🔹", "◆")
        .replace("📊", "【統計】")
        .replace("⏰", "【時間】")
        .replace("🔍", "【搜尋】")
        .replace("🚇", "")
        .replace("📧", "")
    )
    links: list[tuple[str, str]] = []

    def _protect_link(match: re.Match) -> str:
        links.append((match.group(1), match.group(2)))
        return f"__PDF_LINK_{len(links) - 1}__"

    prepared = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", _protect_link, prepared)
    safe = escape(prepared, quote=False)
    for idx, (label, url) in enumerate(links):
        link_markup = (
            f'<link href="{escape(url, quote=True)}" color="#1f5f8b">'
            f'{escape(label, quote=False)}</link>'
        )
        safe = safe.replace(f"__PDF_LINK_{idx}__", link_markup)
    return f'<font name="{cjk_font}">{safe}</font>'


def _soft_wrap_long_tokens(text: str, chunk: int = 45) -> str:
    """在超長無空白字串（如 Google News 長網址）中每隔 chunk 字元插入零寬空白，
    讓 reportlab 能夠換行、不會爆出版面；零寬空白不影響複製貼上後的文字內容。"""
    words = text.split(" ")
    out = []
    for w in words:
        has_cjk = re.search(r"[\u3400-\u9fff]", w) is not None
        looks_like_url_or_ascii_token = re.search(r"https?://|[A-Za-z0-9]{24,}", w) is not None
        if len(w) > chunk and looks_like_url_or_ascii_token and not has_cjk:
            w = "\u200b".join(w[i:i + chunk] for i in range(0, len(w), chunk))
        out.append(w)
    return " ".join(out)


def streamlit_markdown_to_pdf_bytes(
    md: str, *, marker_cleaner, font_registrar, line_compactor, rich_text_renderer,
    token_wrapper, candidate_id_pattern,
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    md = marker_cleaner(md)
    cjk_font, latin_font = font_registrar()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    for style_name in ("Title", "Heading1", "Heading2", "Heading3", "BodyText"):
        styles[style_name].fontName = cjk_font
        styles[style_name].leading = max(styles[style_name].leading, 14)
        styles[style_name].wordWrap = "CJK"
        styles[style_name].splitLongWords = 1
    styles["BodyText"].fontSize = 10.2
    styles["BodyText"].leading = 15
    styles["Title"].fontSize = 15
    styles["Title"].leading = 20
    styles["Heading2"].fontSize = 12.5
    styles["Heading2"].leading = 17
    styles["Heading3"].fontSize = 11.2
    styles["Heading3"].leading = 16
    styles.add(ParagraphStyle(
        name="ReportBullet",
        parent=styles["BodyText"],
        leftIndent=14,
        firstLineIndent=-8,
        spaceBefore=1,
        spaceAfter=1,
        wordWrap="CJK",
        splitLongWords=1,
    ))
    styles.add(ParagraphStyle(
        name="CompactReportTitle",
        parent=styles["Title"],
        fontName=cjk_font,
        fontSize=13.5,
        leading=18,
        wordWrap="CJK",
        splitLongWords=1,
    ))

    story = []
    raw_lines = md.splitlines()
    idx = 0
    previous_blank = False
    while idx < len(raw_lines):
        raw_line = raw_lines[idx]
        line = raw_line.strip()
        if candidate_id_pattern.fullmatch(line):
            idx += 1
            continue
        if not line or line == "---":
            if not previous_blank:
                story.append(Spacer(1, 3))
            previous_blank = True
            idx += 1
            continue
        previous_blank = False
        if line.startswith("📊") and idx + 1 < len(raw_lines):
            next_idx = idx + 1
            while next_idx < len(raw_lines) and not raw_lines[next_idx].strip():
                next_idx += 1
            next_line = raw_lines[next_idx].strip() if next_idx < len(raw_lines) else ""
            if next_line.startswith("⏰"):
                story.append(Paragraph(rich_text_renderer(line_compactor(line), cjk_font, latin_font), styles["BodyText"]))
                story.append(Spacer(1, 3))
                story.append(Paragraph(rich_text_renderer(line_compactor(next_line), cjk_font, latin_font), styles["BodyText"]))
                idx = next_idx + 1
                continue
        if line.startswith("# "):
            title_text = line[2:]
            title_style = styles["CompactReportTitle"] if len(title_text) >= 28 else styles["Title"]
            story.append(Paragraph(rich_text_renderer(title_text, cjk_font, latin_font), title_style))
        elif line.startswith("## "):
            story.append(Paragraph(rich_text_renderer(line[3:], cjk_font, latin_font), styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(rich_text_renderer(line[4:], cjk_font, latin_font), styles["Heading3"]))
        elif line.startswith(("- ", "• ")):
            line = line_compactor(line)
            story.append(Paragraph(rich_text_renderer(token_wrapper(line, 48), cjk_font, latin_font), styles["ReportBullet"]))
        else:
            line = line_compactor(line)
            story.append(Paragraph(rich_text_renderer(token_wrapper(line, 56), cjk_font, latin_font), styles["BodyText"]))
        idx += 1
    doc.build(story)
    return buffer.getvalue()
