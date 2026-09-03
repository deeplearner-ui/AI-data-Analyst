from __future__ import annotations

import base64
import html
import json
import os
import re
from copy import copy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

from .datasets import load_version
from .models import new_id, now_iso
from .store import ProjectStore


def _generated_label() -> str:
    local = datetime.now().astimezone()
    offset = local.strftime("%z")
    zone = f"UTC{offset[:3]}:{offset[3:]}" if offset else "local time"
    return f"{local:%Y-%m-%d %H:%M} {zone}"


def markdownish(value: str) -> str:
    lines: list[str] = []
    in_list = False
    for raw in value.splitlines():
        escaped = html.escape(raw)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        if escaped.startswith("- "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{escaped[2:]}</li>")
            continue
        if in_list:
            lines.append("</ul>")
            in_list = False
        if escaped.startswith("### "): lines.append(f"<h3>{escaped[4:]}</h3>")
        elif escaped.startswith("## "): lines.append(f"<h2>{escaped[3:]}</h2>")
        elif escaped.startswith("# "): lines.append(f"<h1>{escaped[2:]}</h1>")
        elif escaped.startswith("&gt; "): lines.append(f"<blockquote>{escaped[5:]}</blockquote>")
        elif escaped.strip(): lines.append(f"<p>{escaped}</p>")
    if in_list: lines.append("</ul>")
    return "\n".join(lines)


def _traceability(sections: list[dict[str, Any]], version_id: str | None, plan_id: str | None) -> dict[str, Any]:
    return {
        "datasetVersionId": version_id,
        "planId": plan_id,
        "resultIds": sorted({str(item) for section in sections for item in section.get("resultIds", [])}),
        "chartIds": sorted({str(item) for section in sections for item in section.get("chartIds", [])}),
    }


def _chart_data(visualization: dict[str, Any]) -> tuple[list[str], list[tuple[str, list[int]]]] | None:
    traces = visualization.get("plotly", {}).get("data", [])
    if not traces: return None
    raw_series: list[tuple[str, list[Any]]] = []
    all_values: list[Any] = []
    for index, trace in enumerate(traces[:6]):
        encoded_values = trace.get("x") or []
        if isinstance(encoded_values, dict) and encoded_values.get("bdata"):
            try:
                dtype = np.dtype(encoded_values.get("dtype", "f8"))
                values = np.frombuffer(base64.b64decode(encoded_values["bdata"]), dtype=dtype).tolist()
            except (TypeError, ValueError):
                values = []
        else:
            values = list(encoded_values)
        values = [value for value in values if value is not None and not (isinstance(value, (float, np.floating)) and not np.isfinite(value))]
        if not values: continue
        label = str(trace.get("name") or f"Series {index + 1}")
        raw_series.append((label, values)); all_values.extend(values)
    if not raw_series: return None
    numeric_values: list[float] = []
    numeric = True
    for value in all_values:
        try: numeric_values.append(float(value))
        except (TypeError, ValueError): numeric = False; break
    if numeric and len(set(numeric_values)) > 12:
        low, high = min(numeric_values), max(numeric_values)
        if low == high: labels = [_format_axis(low)]; return labels, [(name, [len(values)]) for name, values in raw_series]
        bins = 8; width = (high - low) / bins
        labels = [f"{_format_axis(low + index * width)}-{_format_axis(low + (index + 1) * width)}" for index in range(bins)]
        series = []
        for name, values in raw_series:
            counts = [0] * bins
            for value in values:
                position = min(bins - 1, int((float(value) - low) / width)); counts[max(0, position)] += 1
            series.append((name, counts))
        return labels, series
    ordered = []
    for value in all_values:
        label = str(value)
        if label not in ordered: ordered.append(label)
    labels = ordered[:10]
    return labels, [(name, [sum(1 for value in values if str(value) == label) for label in labels]) for name, values in raw_series]


def _format_axis(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _chart_svg(visualization: dict[str, Any]) -> str:
    prepared = _chart_data(visualization)
    if not prepared: return ""
    labels, series = prepared
    width, height = 760, 320; left, top, plot_width, plot_height = 54, 28, 672, 220
    maximum = max([count for _, counts in series for count in counts] or [1])
    group_width = plot_width / max(1, len(labels)); bar_width = max(3, group_width * 0.72 / max(1, len(series)))
    palette = ["#2f7560", "#d9a44d", "#4f789b", "#a45c59", "#6d6596", "#7a8b63"]
    parts = [f'<svg class="report-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(str(visualization.get("title", "Chart")))}">', f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#9aaba4"/>']
    for index, label in enumerate(labels):
        center = left + index * group_width + group_width / 2
        for series_index, (_, counts) in enumerate(series):
            bar_height = plot_height * counts[index] / maximum if maximum else 0
            x = center - (len(series) * bar_width) / 2 + series_index * bar_width
            parts.append(f'<rect x="{x:.1f}" y="{top + plot_height - bar_height:.1f}" width="{max(1, bar_width - 2):.1f}" height="{bar_height:.1f}" rx="2" fill="{palette[series_index % len(palette)]}"/>')
        display = label if len(label) <= 14 else label[:12] + "…"
        parts.append(f'<text x="{center:.1f}" y="{top + plot_height + 20}" text-anchor="middle">{html.escape(display)}</text>')
    for index, (name, _) in enumerate(series):
        x = left + index * 150
        parts.append(f'<rect x="{x}" y="{height - 28}" width="12" height="12" rx="2" fill="{palette[index % len(palette)]}"/><text x="{x + 18}" y="{height - 17}">{html.escape(name[:20])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _visualizations_html(section: dict[str, Any]) -> str:
    figures = []
    for visualization in section.get("visualizations", []):
        svg = _chart_svg(visualization)
        if svg: figures.append(f'<figure><figcaption>{html.escape(str(visualization.get("title", "Chart")))}</figcaption>{svg}</figure>')
    return "".join(figures)


def _metrics_html(section: dict[str, Any]) -> str:
    metrics = section.get("metrics") or {}
    if not metrics: return ""
    score = html.escape(str(metrics.get("score", "—")))
    grade = html.escape(str(metrics.get("grade", "—")))
    level = html.escape(str(metrics.get("level", "—")))
    return f'<div class="quality-score"><div><span>QUALITY SCORE</span><strong>{score}<small>/100</small></strong></div><div><span>GRADE</span><strong>{grade}</strong></div><div><span>STATUS</span><strong>{level}</strong></div></div>'


def _section_html(section: dict[str, Any]) -> str:
    title = f"<h2>{html.escape(str(section.get('title', '')))}</h2>" if section.get("title") else ""
    section_id = html.escape(str(section.get("id", "section")), quote=True)
    return f'<section id="{section_id}" class="report-section {section_id}">{title}{_metrics_html(section)}{markdownish(str(section.get("markdown", "")))}{_visualizations_html(section)}</section>'


def build_report(title: str, sections: list[dict[str, Any]], language: str, version_id: str | None = None, plan_id: str | None = None, template: str = "full") -> dict[str, Any]:
    trace = _traceability(sections, version_id, plan_id)
    body = "\n".join(_section_html(section) for section in sections)
    labels = {"zh-CN": ("追溯信息", "数据版本", "分析计划", "统计结果", "图表"), "en": ("Traceability", "Dataset version", "Analysis plan", "Statistical results", "Charts")}[language]
    template_labels = {"zh-CN": {"management": "管理层摘要", "full": "完整分析报告", "technical": "技术审计报告"}, "en": {"management": "Executive brief", "full": "Full analysis report", "technical": "Technical audit report"}}
    contents_title = "目录" if language == "zh-CN" else "Contents"
    contents = "".join(f'<a href="#{html.escape(str(section.get("id", "section")), quote=True)}"><span>{index}</span>{html.escape(str(section.get("title", "")))}</a>' for index, section in enumerate(sections, 1))
    quality_section = next((section for section in sections if section.get("metrics")), None)
    quality_badge = ""
    if quality_section:
        metrics = quality_section["metrics"]
        quality_badge = f'<div class="cover-score"><span>{"数据质量" if language == "zh-CN" else "Data quality"}</span><strong>{metrics.get("score", "—")}/100</strong><small>{metrics.get("grade", "—")} · {html.escape(str(metrics.get("level", "—")))}</small></div>'
    trace_html = f"""<section class="trace"><h2>{labels[0]}</h2><dl><dt>{labels[1]}</dt><dd>{html.escape(trace['datasetVersionId'] or '—')}</dd><dt>{labels[2]}</dt><dd>{html.escape(trace['planId'] or '—')}</dd><dt>{labels[3]}</dt><dd>{html.escape(', '.join(trace['resultIds']) or '—')}</dd><dt>{labels[4]}</dt><dd>{html.escape(', '.join(trace['chartIds']) or '—')}</dd></dl></section>"""
    document = f"""<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(title)}</title><style>:root{{--ink:#17372f;--muted:#687a72;--line:#d9e0db;--paper:#f3f5f2;--forest:#17483d;--gold:#d9a44d}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{font-family:Segoe UI,'Microsoft YaHei',sans-serif;max-width:1040px;margin:42px auto;padding:0 30px;color:var(--ink);line-height:1.7;background:var(--paper)}}.cover{{min-height:430px;padding:58px 54px;margin-bottom:24px;color:#fff;background:linear-gradient(135deg,#123f36,#286b58);border-radius:22px;position:relative;overflow:hidden}}.cover:after{{content:'';position:absolute;width:340px;height:340px;border:1px solid #ffffff22;border-radius:50%;right:-90px;top:-120px}}.cover .badge{{display:inline-block;padding:6px 11px;border:1px solid #ffffff55;border-radius:999px;font-size:12px;letter-spacing:.12em}}.cover h1{{font-size:46px;line-height:1.2;max-width:700px;margin:54px 0 14px}}.cover .meta{{color:#d8e9e2}}.cover-score{{position:absolute;left:54px;bottom:48px;display:flex;gap:16px;align-items:baseline}}.cover-score span,.cover-score small{{color:#d8e9e2}}.cover-score strong{{font-size:30px}}.contents{{padding:24px 30px;background:#fff;border:1px solid var(--line);border-radius:14px}}.contents h2{{margin-top:0}}.contents a{{display:flex;gap:12px;padding:9px 0;color:var(--forest);text-decoration:none;border-bottom:1px solid #edf0ed}}.contents a span{{color:var(--gold);font-weight:700}}h1{{font-size:34px;margin:0}}h2,h3{{color:var(--forest)}}section{{margin:18px 0;padding:26px 32px;border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:0 8px 24px rgba(24,51,45,.04)}}section>h2:first-child{{margin-top:0}}.executive-summary{{border-top:5px solid var(--forest)}}.key-findings h3{{margin:22px 0 5px}}blockquote{{border-left:4px solid var(--gold);background:#fff7e9;margin:10px 0 18px;padding:10px 14px;color:#5f523a}}.quality-score{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin:12px 0 22px}}.quality-score>div{{background:#eef4f0;border-radius:10px;padding:14px}}.quality-score span{{display:block;font-size:10px;letter-spacing:.1em;color:var(--muted)}}.quality-score strong{{display:block;font-size:24px;margin-top:4px}}.quality-score small{{font-size:12px;color:var(--muted)}}figure{{margin:24px 0 8px}}figcaption{{font-weight:700;margin-bottom:8px}}.report-chart{{width:100%;height:auto;background:#fbfcfb;border:1px solid var(--line);border-radius:10px}}.report-chart text{{font:12px 'Microsoft YaHei',Segoe UI,sans-serif;fill:#53665f}}dl{{display:grid;grid-template-columns:150px 1fr;gap:8px}}dt{{font-weight:700}}dd{{margin:0;overflow-wrap:anywhere}}footer{{margin:28px 0;color:var(--muted);font-size:12px}}@media(max-width:700px){{body{{padding:0 14px}}.cover{{padding:38px 28px}}.cover h1{{font-size:34px}}.cover-score{{left:28px}}.quality-score{{grid-template-columns:1fr}}}}@media print{{body{{margin:0;background:#fff}}.cover{{min-height:240mm;break-after:page}}.contents{{break-after:page}}section{{box-shadow:none;break-inside:avoid}}}}</style></head><body><header class="cover"><span class="badge">AI DATA ANALYST · REPORT V2</span><h1>{html.escape(title)}</h1><p class="meta">{html.escape(template_labels[language].get(template, template))} · {_generated_label()}</p>{quality_badge}</header><nav class="contents"><h2>{contents_title}</h2>{contents}</nav>{body}{trace_html}<footer>Generated locally by AI Data Analyst · {html.escape(template_labels[language].get(template, template))}</footer></body></html>"""
    document = document.replace("REPORT V2", "REPORT V3")
    findings = [item for section in sections for item in section.get("findings", [])]
    quality = quality_section.get("metrics") if quality_section else None
    return {"id": new_id("report"), "title": title, "language": language, "template": template, "sections": sections, "findings": findings, "quality": quality, "traceability": trace, "updatedAt": now_iso(), "html": document}


def _pdf_font() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    regular = next((item for item in [fonts / "msyh.ttc", fonts / "simhei.ttf", fonts / "arial.ttf"] if item.exists()), None)
    bold = next((item for item in [fonts / "msyhbd.ttc", fonts / "simhei.ttf", regular] if item and item.exists()), regular)
    if regular:
        pdfmetrics.registerFont(TTFont("AidaSans", str(regular)))
        pdfmetrics.registerFont(TTFont("AidaSansBold", str(bold)))
        return "AidaSans", "AidaSansBold"
    return "Helvetica", "Helvetica-Bold"


def build_pdf_report(title: str, sections: list[dict[str, Any]], language: str, version_id: str | None = None, plan_id: str | None = None, template: str = "full") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font, bold = _pdf_font()
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=19 * mm, leftMargin=19 * mm, topMargin=20 * mm, bottomMargin=18 * mm, title=title, author="AI Data Analyst")
    base = getSampleStyleSheet()
    body = ParagraphStyle("AidaBody", parent=base["BodyText"], fontName=font, fontSize=10, leading=16, textColor=colors.HexColor("#263a34"), spaceAfter=6)
    heading = ParagraphStyle("AidaHeading", parent=body, fontName=bold, fontSize=16, leading=21, textColor=colors.HexColor("#17483d"), spaceBefore=12, spaceAfter=8)
    subheading = ParagraphStyle("AidaSubheading", parent=heading, fontSize=12, leading=17)
    bullet = ParagraphStyle("AidaBullet", parent=body, leftIndent=12, firstLineIndent=-8)
    title_style = ParagraphStyle("AidaTitle", parent=heading, fontSize=27, leading=34, alignment=TA_CENTER, spaceAfter=8)
    meta = ParagraphStyle("AidaMeta", parent=body, fontSize=8, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#73827c"), spaceAfter=18)
    cover_label = {"zh-CN": {"management": "管理层摘要", "full": "完整分析报告", "technical": "技术审计报告"}, "en": {"management": "Executive brief", "full": "Full analysis report", "technical": "Technical audit report"}}[language].get(template, template)
    quality_section = next((section for section in sections if section.get("metrics")), None)
    story: list[Any] = [Spacer(1, 32 * mm), Paragraph("AI DATA ANALYST · REPORT V3", meta), Paragraph(html.escape(title), title_style), Paragraph(f"{html.escape(cover_label)} · {_generated_label()}", meta)]
    if quality_section:
        metrics = quality_section["metrics"]
        cards = [[Paragraph("QUALITY SCORE", meta), Paragraph("GRADE", meta), Paragraph("STATUS", meta)], [Paragraph(f"<b>{metrics.get('score', '—')}/100</b>", subheading), Paragraph(f"<b>{metrics.get('grade', '—')}</b>", subheading), Paragraph(f"<b>{html.escape(str(metrics.get('level', '—')))}</b>", subheading)]]
        score_table = Table(cards, colWidths=[55 * mm, 45 * mm, 55 * mm], rowHeights=[10 * mm, 16 * mm])
        score_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4f0")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9e0db")), ("INNERGRID", (0, 0), (-1, -1), .5, colors.HexColor("#d9e0db")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story += [Spacer(1, 14 * mm), score_table]
    story += [PageBreak(), Paragraph("目录" if language == "zh-CN" else "Contents", heading)]
    for index, section in enumerate(sections, 1):
        story.append(Paragraph(f"<b>{index:02d}</b>　{html.escape(str(section.get('title', '')))}", body))
    story.append(Spacer(1, 8 * mm))

    class ReportChart(Flowable):
        def __init__(self, visualization: dict[str, Any]):
            super().__init__(); self.visualization = visualization; self.width = 168 * mm; self.height = 68 * mm

        def draw(self) -> None:
            prepared = _chart_data(self.visualization)
            if not prepared: return
            labels, series = prepared; canvas = self.canv
            left, bottom, plot_width, plot_height = 11 * mm, 17 * mm, self.width - 14 * mm, self.height - 25 * mm
            maximum = max([count for _, counts in series for count in counts] or [1]); palette = ["#2f7560", "#d9a44d", "#4f789b", "#a45c59", "#6d6596", "#7a8b63"]
            canvas.setStrokeColor(colors.HexColor("#9aaba4")); canvas.line(left, bottom, left + plot_width, bottom)
            group_width = plot_width / max(1, len(labels)); bar_width = max(2, group_width * 0.72 / max(1, len(series)))
            canvas.setFont(font, 6.5); canvas.setFillColor(colors.HexColor("#53665f"))
            for index, label in enumerate(labels):
                center = left + index * group_width + group_width / 2
                for series_index, (_, counts) in enumerate(series):
                    height = plot_height * counts[index] / maximum if maximum else 0
                    x = center - len(series) * bar_width / 2 + series_index * bar_width
                    canvas.setFillColor(colors.HexColor(palette[series_index % len(palette)])); canvas.roundRect(x, bottom, max(1, bar_width - 1), height, 1, stroke=0, fill=1)
                canvas.setFillColor(colors.HexColor("#53665f")); display = label if len(label) <= 10 else label[:9] + "…"; canvas.drawCentredString(center, bottom - 8, display)
            canvas.setFont(font, 7)
            for index, (name, _) in enumerate(series):
                x = left + index * 43 * mm; canvas.setFillColor(colors.HexColor(palette[index % len(palette)])); canvas.rect(x, 2 * mm, 3 * mm, 3 * mm, stroke=0, fill=1)
                canvas.setFillColor(colors.HexColor("#53665f")); canvas.drawString(x + 4 * mm, 2 * mm, name[:18])

    def inline(value: str) -> str:
        escaped = html.escape(value)
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)

    def markdown_flows(value: str) -> list[Any]:
        result: list[Any] = []
        for raw in value.splitlines():
            line = raw.strip()
            if not line: result.append(Spacer(1, 3)); continue
            if line.startswith("### "): result.append(Paragraph(inline(line[4:]), subheading))
            elif line.startswith("## "): result.append(Paragraph(inline(line[3:]), heading))
            elif line.startswith("# "): result.append(Paragraph(inline(line[2:]), heading))
            elif line.startswith("- "): result.append(Paragraph("• " + inline(line[2:]), bullet))
            elif line.startswith("> "): result.append(Paragraph(inline(line[2:]), ParagraphStyle("AidaQuote", parent=body, leftIndent=10, borderColor=colors.HexColor("#d9a44d"), borderWidth=2, borderPadding=7, backColor=colors.HexColor("#fff7e9"))))
            else: result.append(Paragraph(inline(line), body))
        return result

    for section in sections:
        section_heading = Paragraph(html.escape(str(section.get("title", ""))), heading)
        if section.get("id") == "key-findings":
            story.append(section_heading)
            for block in re.split(r"(?=^### )", str(section.get("markdown", "")), flags=re.MULTILINE):
                if block.strip(): story.append(KeepTogether(markdown_flows(block)))
            story.append(Spacer(1, 8))
            continue
        flows: list[Any] = [section_heading]
        metrics = section.get("metrics") or {}
        if metrics:
            metric_table = Table([[Paragraph(f"<b>{metrics.get('score', '—')}/100</b><br/><font size='7'>QUALITY SCORE</font>", body), Paragraph(f"<b>{metrics.get('grade', '—')}</b><br/><font size='7'>GRADE</font>", body), Paragraph(f"<b>{html.escape(str(metrics.get('level', '—')))}</b><br/><font size='7'>STATUS</font>", body)]], colWidths=[52 * mm] * 3)
            metric_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4f0")), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#d9e0db")), ("INNERGRID", (0, 0), (-1, -1), .5, colors.HexColor("#d9e0db")), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
            flows.append(metric_table)
        flows.extend(markdown_flows(str(section.get("markdown", ""))))
        if section.get("id") == "statistics":
            story.append(KeepTogether(flows))
        else:
            story.append(KeepTogether(flows[:3])); story.extend(flows[3:])
        for visualization in section.get("visualizations", []):
            if _chart_data(visualization):
                story.append(KeepTogether([Paragraph(html.escape(str(visualization.get("title", "Chart"))), subheading), ReportChart(visualization)]))
        story.append(Spacer(1, 8))

    trace = _traceability(sections, version_id, plan_id)
    trace_title = "追溯信息" if language == "zh-CN" else "Traceability"
    trace_lines = [
        ("数据版本" if language == "zh-CN" else "Dataset version", trace["datasetVersionId"]),
        ("分析计划" if language == "zh-CN" else "Analysis plan", trace["planId"]),
        ("统计结果" if language == "zh-CN" else "Statistical results", ", ".join(trace["resultIds"])),
        ("图表" if language == "zh-CN" else "Charts", ", ".join(trace["chartIds"])),
    ]
    trace_flows: list[Any] = [Paragraph(trace_title, heading)]
    trace_flows.extend(Paragraph(f"<b>{html.escape(label)}</b>: {html.escape(value or '—')}", body) for label, value in trace_lines)
    story.append(KeepTogether(trace_flows))

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState(); canvas.setFont(font, 8); canvas.setFillColor(colors.HexColor("#73827c"))
        canvas.drawString(19 * mm, 10 * mm, "AI Data Analyst")
        canvas.drawRightString(A4[0] - 19 * mm, 10 * mm, str(doc.page)); canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def encoded_export(filename: str, mime_type: str, content: bytes) -> dict[str, Any]:
    return {"filename": filename, "mimeType": mime_type, "bytes": len(content), "contentBase64": base64.b64encode(content).decode("ascii")}


def _safe_filename(value: str, fallback: str = "analysis") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return (cleaned or fallback)[:120]


def _safe_cell(value: Any) -> Any:
    if value is None: return None
    if isinstance(value, (list, tuple, dict, set)): return json.dumps(value, ensure_ascii=False, default=str)
    missing = pd.isna(value)
    if isinstance(missing, (bool, np.bool_)) and missing: return None
    if isinstance(value, pd.Timestamp): return value.isoformat()
    if isinstance(value, np.generic): value = value.item()
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")): return "'" + value
    return value


def dataset_export(store: ProjectStore, version_id: str, export_format: str) -> dict[str, Any]:
    frame, version = load_version(store, version_id)
    safe = frame.map(_safe_cell)
    if export_format == "csv":
        content = safe.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
        result = encoded_export(f"dataset-{version_id}.csv", "text/csv; charset=utf-8", content)
    elif export_format == "xlsx":
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            safe.to_excel(writer, sheet_name="Data", index=False)
            pd.DataFrame({"Property": ["Version ID", "Fingerprint", "Rows", "Operation", "Created at"], "Value": [version["id"], version["fingerprint"], version["rowCount"], version["operation"], version["createdAt"]]}).to_excel(writer, sheet_name="AIDA Metadata", index=False)
            worksheet = writer.book["Data"]; worksheet.freeze_panes = "A2"; worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                font = copy(cell.font); font.bold = True; cell.font = font
        result = encoded_export(f"dataset-{version_id}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", output.getvalue())
    else:
        raise ValueError("Unsupported dataset export format")
    result["versionId"] = version_id; result["rowCount"] = len(frame); result["columnCount"] = len(frame.columns)
    return result


def report_export(title: str, sections: list[dict[str, Any]], language: str, export_format: str, version_id: str | None, plan_id: str | None, template: str = "full") -> dict[str, Any]:
    report = build_report(title, sections, language, version_id, plan_id, template)
    filename = _safe_filename(title)
    if export_format == "html": return encoded_export(f"{filename}.html", "text/html; charset=utf-8", report["html"].encode("utf-8")) | {"reportId": report["id"]}
    if export_format == "pdf": return encoded_export(f"{filename}.pdf", "application/pdf", build_pdf_report(title, sections, language, version_id, plan_id, template)) | {"reportId": report["id"]}
    raise ValueError("Unsupported report export format")


def reproducibility_bundle(project_directory: str, version_id: str, plan_id: str | None, title: str, sections: list[dict[str, Any]], language: str, include_data: bool = False, data_format: str = "csv", template: str = "full") -> dict[str, Any]:
    store = ProjectStore(project_directory); manifest = store.open()
    plan = store.get_plan(plan_id) if plan_id else store.latest_plan()
    artifacts = store.artifacts_for_plan(plan["id"]) if plan else []
    report = build_report(title, sections, language, version_id, plan["id"] if plan else None, template)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as bundle:
        bundle.writestr("README.txt", ("AI Data Analyst 可复现分析包\n默认不包含原始数据。请查看 manifest、versions、plan 和 artifacts 以复核分析过程。\n" if language == "zh-CN" else "AI Data Analyst reproducibility bundle\nRaw data is excluded by default. Review manifest, versions, plan, and artifacts to reproduce the workflow.\n"))
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        bundle.writestr("versions.json", json.dumps(store.all_versions(), ensure_ascii=False, indent=2))
        bundle.writestr("analysis/plan.json", json.dumps(plan, ensure_ascii=False, indent=2) if plan else "null")
        bundle.writestr("analysis/artifacts.json", json.dumps(artifacts, ensure_ascii=False, indent=2))
        bundle.writestr("environment.json", json.dumps({"schemaVersion": manifest["schemaVersion"], "generatedAt": now_iso(), "dataIncluded": include_data, "dataFormat": data_format if include_data else None}, ensure_ascii=False, indent=2))
        bundle.writestr("report/report.html", report["html"])
        bundle.writestr("report/report.pdf", build_pdf_report(title, sections, language, version_id, plan["id"] if plan else None, template))
        if include_data:
            data = dataset_export(store, version_id, data_format)
            bundle.writestr(f"data/current-version.{data_format}", base64.b64decode(data["contentBase64"]))
    return encoded_export(f"{_safe_filename(title)}-reproducibility.zip", "application/zip", output.getvalue()) | {"includedData": include_data, "versionId": version_id, "planId": plan["id"] if plan else None}
