"""Render an assembled report document to self-contained HTML and to PDF."""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path

STATUS_COLOR = {"PASS": "#1a7f37", "FAIL": "#cf222e", "WARN": "#9a6700", "REVIEW": "#9a6700",
                "NOT DONE": "#6e7781", "INFO": "#0969da"}
STATUS_LABEL = {"WARN": "REVIEW"}

CSS = """
:root{--bg:#ffffff;--ink:#1c2330;--muted:#5b6678;--line:#d9dee6;--soft:#f4f6f9;--accent:#1f6feb}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#12161d;--ink:#e6ebf2;--muted:#9aa6b8;--line:#2c3542;--soft:#1a202a;--accent:#6ea8ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.page{max-width:920px;margin:0 auto;padding:32px 24px 64px}
header.top{border-bottom:2px solid var(--ink);padding-bottom:14px;margin-bottom:8px}
header.top .eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
h1{font-size:27px;line-height:1.2;margin:6px 0 10px}
.meta{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:13px;color:var(--muted)}
.meta b{color:var(--ink);font-weight:600}
h2{font-size:18px;margin:34px 0 10px;padding-bottom:5px;border-bottom:1px solid var(--line)}
h3{font-size:15px;margin:20px 0 8px}
p{margin:8px 0}
table{border-collapse:collapse;width:100%;margin:10px 0 14px;font-size:13.5px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
th{font-size:12px;letter-spacing:.03em;color:var(--muted);font-weight:600;border-bottom:1.5px solid var(--ink)}
td.num{font-variant-numeric:tabular-nums}
table.kv td:first-child{color:var(--muted);width:38%}
.verdict{display:flex;gap:14px;align-items:center;border:1px solid var(--line);border-left-width:6px;border-radius:8px;padding:12px 16px;margin:10px 0 16px;background:var(--soft)}
.verdict .v{font-size:20px;font-weight:700;letter-spacing:.04em}
.badge{display:inline-block;min-width:74px;text-align:center;font-size:11.5px;font-weight:700;letter-spacing:.04em;padding:2px 8px;border-radius:999px;color:#fff;white-space:nowrap}
.note{border-left:3px solid var(--line);padding:4px 12px;color:var(--muted);font-size:13.5px;margin:8px 0}
figure{margin:14px 0;text-align:center}
figure img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:6px;background:#fff}
figcaption{font-size:12.5px;color:var(--muted);margin-top:4px}
.calc{border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0}
.calc .hd{display:flex;justify-content:space-between;gap:12px;align-items:center;font-weight:600}
.calc .cmp{display:flex;flex-wrap:wrap;gap:6px 26px;margin:6px 0;font-variant-numeric:tabular-nums}
.calc .cmp span b{font-weight:600}
.calc .ln{font-size:13px;color:var(--muted);margin:2px 0}
.fcf{font-family:"DejaVu Sans","Segoe UI Symbol","Arial Unicode MS",sans-serif;font-size:15px;white-space:nowrap}
ul{margin:6px 0 12px;padding-left:22px}
li{margin:3px 0}
.sign{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:14px}
.sign div{border-top:1px solid var(--ink);padding-top:6px;font-size:12.5px;color:var(--muted);min-height:54px}
footer{margin-top:36px;font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:10px}
@media (max-width:640px){.page{padding:20px 16px 48px}.sign{grid-template-columns:1fr}table{font-size:12.5px}}
@media print{.page{max-width:none;padding:0}h2{break-after:avoid}figure,.calc,.verdict,tr{break-inside:avoid}body{font-size:11pt}}
"""


def _badge(status: str) -> str:
    return (f'<span class="badge" style="background:{STATUS_COLOR.get(status, "#6e7781")}">'
            f'{STATUS_LABEL.get(status, status)}</span>')


def _e(s) -> str:
    """Escape text but keep the few inline tags the assembler uses."""
    t = html.escape(str(s), quote=False)
    return re.sub(r"&lt;(/?b)&gt;", r"<\1>", t)


def to_html(doc: dict) -> str:
    out = []
    w = out.append
    w(f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
      f'<meta name="viewport" content="width=device-width, initial-scale=1">'
      f'<title>{html.escape(doc["title"])} - engineering report</title><style>{CSS}</style></head><body>'
      f'<div class="page"><header class="top"><div class="eyebrow">Engineering verification report - {html.escape(doc["kind"])}</div>'
      f'<h1>{html.escape(doc["title"])}</h1><div class="meta">'
      f'<span>Job <b>{html.escape(doc["job"])}</b></span><span>Date <b>{doc["date"]}</b></span>'
      f'<span>Units <b>{doc["system"]}</b></span><span>Tolerancing standard <b>{html.escape(doc["standard"])}</b></span>'
      f'<span>Verdict {_badge(doc["verdict"])}</span></div></header>')
    for b in doc["blocks"]:
        k = b[0]
        if k == "h2":
            w(f"<h2>{_e(b[1])}</h2>")
        elif k == "h3":
            w(f"<h3>{_e(b[1])}</h3>")
        elif k == "p":
            w(f"<p>{_e(b[1])}</p>")
        elif k == "note":
            w(f'<div class="note">{_e(b[1])}</div>')
        elif k == "verdict":
            c = STATUS_COLOR.get(b[1], "#6e7781")
            w(f'<div class="verdict" style="border-left-color:{c}"><span class="v" style="color:{c}">'
              f'{b[1]}</span><span>{_e(b[2])}</span></div>')
        elif k == "kv":
            w('<table class="kv">' + "".join(f"<tr><td>{_e(a)}</td><td>{_e(v)}</td></tr>" for a, v in b[1]) + "</table>")
        elif k == "table":
            sym = b[3].get("symbols") if len(b) > 3 else None
            head = "".join(f"<th>{_e(h)}</th>" for h in b[1])
            rows = "".join("<tr>" + "".join(
                f'<td class="{"fcf" if sym is not None and i == sym else "num" if i else ""}">{_e(c)}</td>'
                for i, c in enumerate(r)) + "</tr>" for r in b[2])
            w(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
        elif k == "list":
            if b[1]:
                w(f"<h3>{_e(b[1])}</h3>")
            w("<ul>" + "".join(f"<li>{_e(i)}</li>" for i in b[2]) + "</ul>")
        elif k == "checks":
            if b[2]:
                w(f"<h3>{_e(b[2])}</h3>")
            w("<table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>"
              + "".join(f"<tr><td>{_e(n)}</td><td>{_badge(s)}</td><td>{_e(d)}</td></tr>" for n, s, d in b[1])
              + "</tbody></table>")
        elif k == "calc":
            _, name, status, lines, exp, fea, diff = b
            cmp_ = "".join(f"<span>{lab} <b>{_e(v)}</b></span>" for lab, v in
                           (("Hand calculation", exp), ("FEA", fea), ("Difference", diff)) if v)
            w(f'<div class="calc"><div class="hd"><span>{_e(name)}</span>{_badge(status)}</div>'
              f'<div class="cmp">{cmp_}</div>' + "".join(f'<div class="ln">{_e(ln)}</div>' for ln in lines) + "</div>")
        elif k == "img":
            p = Path(b[1])
            if p.exists():
                data = base64.b64encode(p.read_bytes()).decode()
                w(f'<figure><img alt="{html.escape(b[2])}" src="data:image/png;base64,{data}">'
                  f"<figcaption>{_e(b[2])}</figcaption></figure>")
        elif k == "signoff":
            w('<h2>Review and approval</h2><div class="sign"><div>Prepared with EngineeringAgent '
              f'v{doc["version"]}<br>{doc["date"]}</div><div>Checked by / date</div>'
              "<div>Approved by / date</div></div>")
    w(f'<footer>Generated by EngineeringAgent v{doc["version"]} (build123d, Gmsh, CalculiX). '
      "Numbers in this report are read from solver output files or computed by the documented "
      "formulas. Engineering assistance only - not a substitute for review by a qualified engineer."
      "</footer></div></body></html>")
    return "".join(out)


# --------------------------------------------------------------------------- PDF
def _fonts() -> tuple[str, str]:
    """Register DejaVu Sans (ships with matplotlib) for full Unicode incl. GD&T symbols."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        import matplotlib
        d = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        if "EA-Sans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("EA-Sans", str(d / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("EA-Sans-Bold", str(d / "DejaVuSans-Bold.ttf")))
            pdfmetrics.registerFontFamily("EA-Sans", normal="EA-Sans", bold="EA-Sans-Bold",
                                          italic="EA-Sans", boldItalic="EA-Sans-Bold")
        return "EA-Sans", "EA-Sans-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def to_pdf(doc: dict, path: str | Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)
    font, bold = _fonts()
    page = A4 if doc["system"] == "metric" else letter
    W = page[0] - 36 * mm
    base = ParagraphStyle("b", fontName=font, fontSize=9.2, leading=12.6, textColor=colors.HexColor("#1c2330"))
    small = ParagraphStyle("s", parent=base, fontSize=8, leading=10.6, textColor=colors.HexColor("#5b6678"))
    cell = ParagraphStyle("c", parent=base, fontSize=8.3, leading=10.8)
    head = ParagraphStyle("th", parent=cell, fontName=bold, textColor=colors.HexColor("#5b6678"))
    h1 = ParagraphStyle("h1", parent=base, fontName=bold, fontSize=18, leading=22, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base, fontName=bold, fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=4)
    h3 = ParagraphStyle("h3", parent=base, fontName=bold, fontSize=10, leading=13, spaceBefore=6, spaceAfter=2)
    line = colors.HexColor("#d9dee6")

    def esc(s):
        t = html.escape(str(s), quote=False)
        return re.sub(r"&lt;(/?b)&gt;", r"<\1>", t)

    def badge(status):
        c = STATUS_COLOR.get(status, "#6e7781")
        return Paragraph(f'<font color="{c}"><b>{STATUS_LABEL.get(status, status)}</b></font>', cell)

    def table(headers, rows, widths=None, kv=False):
        data = ([[Paragraph(esc(h), head) for h in headers]] if headers else []) + \
            [[c if not isinstance(c, str) else Paragraph(esc(c), cell) for c in r] for r in rows]
        n = len(data[0])
        cw = [W * f for f in widths] if widths else [W / n] * n
        t = Table(data, colWidths=cw, repeatRows=1 if headers else 0)
        st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, line),
              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if headers:
            st.append(("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.HexColor("#1c2330")))
        t.setStyle(TableStyle(st))
        return t

    S = []
    S.append(Paragraph(f"ENGINEERING VERIFICATION REPORT - {esc(doc['kind']).upper()}", small))
    S.append(Paragraph(esc(doc["title"]), h1))
    vc = STATUS_COLOR.get(doc["verdict"], "#6e7781")
    S.append(Paragraph(f"Job <b>{esc(doc['job'])}</b> &nbsp;&nbsp; Date <b>{doc['date']}</b> &nbsp;&nbsp; "
                       f"Units <b>{doc['system']}</b> &nbsp;&nbsp; Tolerancing standard <b>{esc(doc['standard'])}</b> "
                       f"&nbsp;&nbsp; Verdict <font color='{vc}'><b>{doc['verdict']}</b></font>", small))
    S.append(Spacer(1, 2 * mm))
    S.append(Table([[""]], colWidths=[W], rowHeights=[1], style=TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.HexColor("#1c2330"))])))
    for b in doc["blocks"]:
        k = b[0]
        if k == "h2":
            S.append(Paragraph(esc(b[1]), h2))
        elif k == "h3":
            S.append(Paragraph(esc(b[1]), h3))
        elif k == "p":
            S.append(Paragraph(esc(b[1]), base)); S.append(Spacer(1, 1.5 * mm))
        elif k == "note":
            S.append(Paragraph(esc(b[1]), small)); S.append(Spacer(1, 1.5 * mm))
        elif k == "verdict":
            c = STATUS_COLOR.get(b[1], "#6e7781")
            t = Table([[Paragraph(f'<font color="{c}" size="13"><b>{b[1]}</b></font>', base),
                        Paragraph(esc(b[2]), base)]], colWidths=[W * 0.18, W * 0.82])
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f6f9")),
                                   ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor(c)),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
            S.append(t); S.append(Spacer(1, 2 * mm))
        elif k == "kv":
            S.append(table(None, [(a, v) for a, v in b[1]], [0.38, 0.62])); S.append(Spacer(1, 2 * mm))
        elif k == "table":
            opts = b[3] if len(b) > 3 else {}
            hdr, rws = list(b[1]), [list(r) for r in b[2]]
            if opts.get("symbols") is not None:          # PDF fonts lack GD&T symbols: drop that column
                i = opts["symbols"]
                hdr.pop(i)
                for r in rws:
                    r.pop(i)
            S.append(table(hdr, rws, opts.get("widths"))); S.append(Spacer(1, 2 * mm))
        elif k == "list":
            if b[1]:
                S.append(Paragraph(esc(b[1]), h3))
            for i in b[2]:
                S.append(Paragraph("•&nbsp; " + esc(i), ParagraphStyle("li", parent=base, leftIndent=10, firstLineIndent=-8)))
            S.append(Spacer(1, 1.5 * mm))
        elif k == "checks":
            if b[2]:
                S.append(Paragraph(esc(b[2]), h3))
            S.append(table(["Check", "Status", "Detail"], [(n, badge(s), d) for n, s, d in b[1]], [0.3, 0.13, 0.57]))
            S.append(Spacer(1, 2 * mm))
        elif k == "calc":
            _, name, status, lines, exp, fea, diff = b
            cmp_ = " &nbsp;&nbsp; ".join(f"{lab} <b>{esc(v)}</b>" for lab, v in
                                         (("Hand calculation", exp), ("FEA", fea), ("Difference", diff)) if v)
            inner = [Paragraph(f"<b>{esc(name)}</b>", base)]
            if cmp_:
                inner.append(Paragraph(cmp_, base))
            inner += [Paragraph(esc(ln), small) for ln in lines]
            t = Table([[inner, badge(status)]], colWidths=[W * 0.86, W * 0.14])
            t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, line), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            S.append(KeepTogether([t, Spacer(1, 2 * mm)]))
        elif k == "img":
            p = Path(b[1])
            if p.exists():
                from reportlab.lib.utils import ImageReader
                iw, ih = ImageReader(str(p)).getSize()
                w_ = min(W * 0.8, 135 * mm)
                S.append(KeepTogether([Image(str(p), width=w_, height=w_ * ih / iw),
                                       Paragraph(esc(b[2]), ParagraphStyle("cap", parent=small, alignment=1)),
                                       Spacer(1, 2 * mm)]))
        elif k == "signoff":
            S.append(Paragraph("Review and approval", h2))
            t = Table([[Paragraph(f"Prepared with EngineeringAgent v{doc['version']}<br/>{doc['date']}", small),
                        Paragraph("Checked by / date", small), Paragraph("Approved by / date", small)]],
                      colWidths=[W / 3] * 3, rowHeights=[18 * mm])
            t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.HexColor("#1c2330")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
            S.append(Spacer(1, 6 * mm)); S.append(t)

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#5b6678"))
        canvas.drawString(18 * mm, 10 * mm, f"{doc['title'][:70]} - EngineeringAgent v{doc['version']} - "
                          "engineering assistance, not a sign-off")
        canvas.drawRightString(page[0] - 18 * mm, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=page, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=18 * mm, title=doc["title"],
                      author="EngineeringAgent").build(S, onFirstPage=footer, onLaterPages=footer)
    return Path(path)
