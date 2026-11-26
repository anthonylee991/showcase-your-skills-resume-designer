#!/usr/bin/env python3
"""Render a resume JSON file into the designed two-column layout (HTML) and, when a
Chromium-based browser is installed, a print-ready PDF.

usage:  python render.py resume.json [--out DIR] [--paper letter|a4] [--sources] [--plain] [--no-pdf] [--browser PATH]

Checks the JSON first and names every missing or malformed field before rendering.
Reports margin figures that have no "source", and after rendering checks the layout
(orphaned last lines, over-long bullets, clipped timeline labels, overlapping graph labels).

Prints the PDF page count so the caller can tighten copy until it fits.
Standard library only.
"""
import argparse, base64, datetime, html, json, math, os, pathlib, random, re, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
CSS_PATH = HERE.parent / "assets" / "style.css"
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@400;500;600'
         '&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;0,8..60,700;1,8..60,400;1,8..60,600'
         '&display=block" rel="stylesheet">')
FONT_DIR = HERE.parent / "assets" / "fonts"
# scripts the bundled Latin fonts do not cover: Greek, Cyrillic, Vietnamese
OTHER_SCRIPTS = re.compile("[\u0370-\u03ff\u0400-\u052f\u1ea0-\u1ef9\u1f00-\u1fff\u20ab]")
INK, GRAPHITE, RULE = "#1C2430", "#5B6573", "#D9DEE5"
PAPERS = {"letter": "Letter", "a4": "A4"}
CONTENT_IN = {"letter": 7.4, "a4": 7.168}   # width of the text block in print, inches
LAYOUT_NOTES = []   # problems found while drawing the timeline and graph
COND = "IBM Plex Sans Condensed, Arial Narrow, sans-serif"
SERIF = "Source Serif 4, Georgia, serif"


# ---------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=True)


def md(s):
    """Escape, then allow **bold** and *italic*."""
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", s)
    return s


def mix(hex_a, hex_b, t):
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def year_of(v, now):
    """'2024', '2024-07', 'present' -> fractional year."""
    if v in (None, "", "present", "now"):
        return now
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?", str(v).strip())
    if not m:
        sys.exit(f"Bad date {v!r}: use YYYY, YYYY-MM or 'present'.")
    y = int(m.group(1)); mo = int(m.group(2) or 1)
    return y + (mo - 1) / 12


def num(v):
    """Number as short text for a chart description: 0.81, 6, 308."""
    return f"{float(v):g}"


def refs_html(refs):
    if not refs:
        return ""
    return f' <cite class="ref">[{esc(", ".join(str(r) for r in refs))}]</cite>'


# ---------------------------------------------------------------- fonts
def font_faces(text):
    """@font-face rules with the bundled font files inlined, for the subsets this text needs.
    Returns (css, link): link is the Google Fonts tag, used only when the bundled files are
    missing or the text is in a script they do not cover."""
    css_file = FONT_DIR / "fonts.css"
    if not css_file.is_file():
        return "", FONTS
    used = {ord(ch) for ch in text}
    out = []
    for block in re.findall(r"@font-face \{.*?\}", css_file.read_text(encoding="utf8"), re.S):
        spans = [(int(a, 16), int(b or a, 16)) for a, b in
                 re.findall(r"U\+([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?", block.split("unicode-range:")[-1])]
        if not any(lo <= ch <= hi for ch in used for lo, hi in spans):
            continue
        name = re.search(r"url\(([^)]+)\)", block).group(1)
        f = FONT_DIR / name
        if not f.is_file():
            return "", FONTS
        out.append(block.replace(f"url({name})", "url(data:font/woff2;base64," + base64.b64encode(f.read_bytes()).decode("ascii") + ")"))
    return "\n".join(out), (FONTS if OTHER_SCRIPTS.search(text) else "")


# ---------------------------------------------------------------- mini charts (margin)
def mini_chart(c, th):
    if not c:
        return ""
    A, T, S = th["accent"], th["tint"], th["secondary"]
    kind = c.get("type")
    if kind == "fill":
        mx = float(c.get("max", 1)); v = float(c["value"]) / mx * 100
        return (f'<svg class="mini" viewBox="0 0 100 9" role="img" aria-label="Bar filled to {v:.0f}%"><rect x="0" y="1" width="100" height="7" rx="1.5" fill="{T}"/>'
                f'<rect x="0" y="1" width="{v:.1f}" height="7" rx="1.5" fill="{A}"/></svg>')
    if kind == "range":
        mx = float(c.get("max", 100)); a = float(c["from"]) / mx * 100; b = float(c["to"]) / mx * 100
        base = ""
        if c.get("baseline") is not None:
            base = f'<rect x="0" y="1" width="{float(c["baseline"]) / mx * 100:.1f}" height="7" rx="1.5" fill="{S}"/>'
        desc = f'Range from {num(c["from"])} to {num(c["to"])} on a scale of 0 to {num(mx)}'
        if c.get("baseline") is not None:
            desc += f', against a baseline of {num(c["baseline"])}'
        return (f'<svg class="mini" viewBox="0 0 100 9" role="img" aria-label="{esc(desc)}"><rect x="0" y="1" width="100" height="7" rx="1.5" fill="{T}"/>{base}'
                f'<rect x="{a:.1f}" y="1" width="{max(b - a, 1.5):.1f}" height="7" rx="1.5" fill="{A}"/></svg>')
    if kind == "bars":
        items = c["items"]; mx = float(c.get("max", max(float(i["value"]) for i in items)))
        lab_w = min(46, max(len(i["label"]) for i in items) * 3.9 + 4)
        bw = 100 - lab_w; h = 12 * len(items)
        rows = []
        for k, it in enumerate(items):
            y = 2 + 12 * k; hi = it.get("highlight")
            weight = 'font-weight="600" ' if hi else ""
            rows.append(f'<text x="0" y="{y + 6}" font-family="{COND}" font-size="7.3" {weight}fill="{A if hi else GRAPHITE}">{esc(it["label"])}</text>'
                        f'<rect x="{lab_w}" y="{y}" width="{bw}" height="7" rx="1.5" fill="{T}"/>'
                        f'<rect x="{lab_w}" y="{y}" width="{float(it["value"]) / mx * bw:.1f}" height="7" rx="1.5" fill="{A if hi else S}"/>')
        desc = "Comparison: " + ", ".join(f'{i["label"]} {num(i["value"])}' for i in items)
        return f'<svg class="mini" viewBox="0 0 100 {h}" role="img" aria-label="{esc(desc)}">{"".join(rows)}</svg>'
    sys.exit(f"Unknown chart type {kind!r}: use fill, range or bars.")


def evidence(ev, th):
    if not ev:
        return '<div class="ev"></div>'
    out = '<div class="ev">'
    if ev.get("value"):
        out += f'<b>{esc(ev["value"])}</b>'
    out += esc(ev.get("label", ""))
    out += mini_chart(ev.get("chart"), th)
    if ev.get("note"):
        out += esc(ev["note"])
    return out + "</div>"


def claim(c, th):
    lead = f'<strong>{md(c["lead"])}</strong> ' if c.get("lead") else ""
    return (f'<li class="claim"><p>{lead}{md(c["text"])}{refs_html(c.get("refs"))}</p>'
            f'{evidence(c.get("evidence"), th)}</li>')


# ---------------------------------------------------------------- career timeline
def timeline(tl, th, now):
    cats = tl.get("categories", {})
    bars = []
    for b in tl["bars"]:
        cat = cats.get(b.get("category"), {})
        bars.append(dict(label=b["label"], a=year_of(b["start"], now), b=year_of(b.get("end"), now),
                         color=cat.get("color", th["accent"])))
    t0 = math.floor(min(x["a"] for x in bars)) - 0.05
    W = 1000; L, R = 8, 992
    # leave room on the right for labels of bars that run to "now"
    t1 = now + 0.95
    X = lambda t: L + (t - t0) / (t1 - t0) * (R - L)
    # lane assignment: a bar's label sits inside if it fits, else to its right
    bars.sort(key=lambda x: x["a"])
    lanes = []
    for bar in bars:
        x1, x2 = X(bar["a"]), X(bar["b"])
        fits = len(bar["label"]) * 9.5 * 0.5 <= (x2 - x1 - 10)
        bar["inside"] = fits
        end_px = x2 if fits else x2 + 6 + len(bar["label"]) * 6.4
        if not fits and end_px > W:
            LAYOUT_NOTES.append(f'timeline: the label "{bar["label"]}" runs past the right edge and will be clipped; shorten it.')
        for i, last in enumerate(lanes):
            if last + 2 <= x1:
                bar["lane"] = i; lanes[i] = end_px; break
        else:
            bar["lane"] = len(lanes); lanes.append(end_px)
    n = len(lanes); bh = 24; step = 32
    H = 8 + n * step + 28
    out = [f'<svg class="timeline" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(tl.get("aria", "Career timeline"))}">']
    for y in range(int(math.ceil(t0)), int(now) + 2):
        x = X(y)
        if x > R:
            break
        out.append(f'<line x1="{x:.1f}" y1="2" x2="{x:.1f}" y2="{8 + n * step - 2}" stroke="{RULE}" stroke-width="0.8"/>')
        if y <= now:
            out.append(f'<text x="{x + 3:.1f}" y="{H - 8}" font-family="{COND}" font-size="12.5" fill="{GRAPHITE}">{y}</text>')
    for bar in bars:
        x1, x2 = X(bar["a"]), X(bar["b"]); y = 8 + bar["lane"] * step
        out.append(f'<rect x="{x1 + 1:.1f}" y="{y}" width="{max(x2 - x1 - 2, 3):.1f}" height="{bh}" rx="3" fill="{bar["color"]}"/>')
        light = sum(int(bar["color"][i:i + 2], 16) for i in (1, 3, 5)) > 450
        if bar["inside"]:
            fs = 13.0
            while len(bar["label"]) * fs * 0.5 > (x2 - x1 - 10) and fs > 9.5:
                fs -= 0.5
            out.append(f'<text x="{x1 + 5:.1f}" y="{y + 16.5}" font-family="{COND}" font-size="{fs}" font-weight="500" fill="{INK if light else "#FFFFFF"}">{esc(bar["label"])}</text>')
        else:
            out.append(f'<text x="{x2 + 5:.1f}" y="{y + 16.5}" font-family="{COND}" font-size="12.5" font-weight="600" fill="{bar["color"] if not light else INK}">{esc(bar["label"])}</text>')
    nx = X(now)
    out.append(f'<line x1="{nx:.1f}" y1="0" x2="{nx:.1f}" y2="{8 + n * step - 2}" stroke="{th["now"]}" stroke-width="2"/>')
    out.append(f'<text x="{nx - 4:.1f}" y="{H - 8}" text-anchor="end" font-family="{COND}" font-size="12.5" font-weight="600" fill="{th["now"]}">now</text>')
    out.append("</svg>")
    return "\n".join(out)


def legend(tl, th, as_of_label):
    rows = [f'<i style="background:{esc(c.get("color", th["accent"]))}"></i>{esc(c["label"])}'
            for c in tl.get("categories", {}).values()]
    rows.append(f'<i class="line" style="background:{th["now"]}"></i>Now, {esc(as_of_label)}')
    return '<div class="legend">' + "<br>".join(rows) + "</div>"


# ---------------------------------------------------------------- knowledge graph
def graph_layout(projects, seed):
    """Place the nodes. Returns the positions and how many labels still overlap."""
    techs = sorted({t for v in projects.values() for t in v})
    deg = {t: sum(t in v for v in projects.values()) for t in techs}
    nodes = list(projects) + techs
    is_p = {n: n in projects for n in nodes}
    edges = [(p, t) for p, ts in projects.items() for t in ts]
    W = 1000; H = max(180, min(300, 120 + 5 * len(nodes)))
    rnd = random.Random(seed); pos = {}
    for i, p in enumerate(projects):
        a = 2 * math.pi * i / len(projects)
        pos[p] = [W / 2 + 400 * math.cos(a), H / 2 + (H / 2 - 40) * math.sin(a)]
    for t in techs:
        pos[t] = [W / 2 + rnd.uniform(-250, 250), H / 2 + rnd.uniform(-H / 4, H / 4)]
    lw = lambda n: len(n) * (8.2 if is_p[n] else 7.0) + 20
    iters = 900
    for it in range(iters):
        disp = {n: [0.0, 0.0] for n in nodes}; temp = 1.0 - it / iters
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                dx = pos[a][0] - pos[b][0]; dy = (pos[a][1] - pos[b][1]) * 2.2
                d = math.hypot(dx, dy) + 0.01; want = (lw(a) + lw(b)) / 2 + 10
                f = (want * want) / d * 0.9 if d < want * 1.8 else 900 / d
                disp[a][0] += dx / d * f; disp[a][1] += dy / d * f / 2.2
                disp[b][0] -= dx / d * f; disp[b][1] -= dy / d * f / 2.2
        for a, b in edges:
            dx = pos[a][0] - pos[b][0]; dy = pos[a][1] - pos[b][1]
            d = math.hypot(dx, dy) + 0.01; f = d * d / 160
            disp[a][0] -= dx / d * f; disp[a][1] -= dy / d * f
            disp[b][0] += dx / d * f; disp[b][1] += dy / d * f
        for n in nodes:
            dx, dy = disp[n]; d = math.hypot(dx, dy) + 0.01; step = min(d, 30 * temp + 1)
            pos[n][0] += dx / d * step; pos[n][1] += dy / d * step
            m = lw(n) / 2
            pos[n][0] = min(max(pos[n][0], m), W - m); pos[n][1] = min(max(pos[n][1], 22), H - 22)

    def box(n):
        x, y = pos[n]
        if is_p[n]:
            w = lw(n) - 4
            return (x - w / 2 - 6, y - 15, x + w / 2 + 6, y + 15)
        r = 4 + deg[n] * 1.6; w = len(n) * (6.4 + deg[n] * 0.45) + 10
        return (x - max(w / 2, r) - 4, y - r - 20, x + max(w / 2, r) + 4, y + r + 4)

    for _ in range(400):  # push overlapping labels apart
        moved = False
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                P, Q = box(a), box(b)
                ox = min(P[2], Q[2]) - max(P[0], Q[0]); oy = min(P[3], Q[3]) - max(P[1], Q[1])
                if ox > 0 and oy > 0:
                    moved = True
                    if ox < oy * 1.6:
                        d = ox / 2 + 0.5; s = 1 if pos[a][0] >= pos[b][0] else -1
                        pos[a][0] += s * d; pos[b][0] -= s * d
                    else:
                        d = oy / 2 + 0.5; s = 1 if pos[a][1] >= pos[b][1] else -1
                        pos[a][1] += s * d; pos[b][1] -= s * d
        for n in nodes:
            x0, y0, x1, y1 = box(n)
            if x0 < 0: pos[n][0] -= x0
            if x1 > W: pos[n][0] -= x1 - W
            if y0 < 0: pos[n][1] -= y0
            if y1 > H: pos[n][1] -= y1 - H
        if not moved:
            break
    hit = lambda P, Q: min(P[2], Q[2]) - max(P[0], Q[0]) > 1 and min(P[3], Q[3]) - max(P[1], Q[1]) > 1
    overlaps = sum(hit(box(a), box(b)) for i, a in enumerate(nodes) for b in nodes[i + 1:])
    crossed = 0   # links that run through another node's label: not an error, but the fewer the cleaner
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        for n in nodes:
            if n in (a, b):
                continue
            x0, y0, xb, yb = box(n)
            if any(x0 < x1 + (x2 - x1) * k / 24 < xb and y0 < y1 + (y2 - y1) * k / 24 < yb for k in range(1, 24)):
                crossed += 1
    return dict(pos=pos, techs=techs, deg=deg, edges=edges, lw=lw, W=W, H=H, overlaps=overlaps, crossed=crossed)


def graph(projects, th, seed=7):
    A = th["accent"]; edge_col = mix(A, "#FFFFFF", 0.55)
    g = graph_layout(projects, seed)
    if g["overlaps"]:
        note = f'graph: {g["overlaps"]} label{"s" if g["overlaps"] != 1 else ""} overlap with "seed": {seed}.'
        clean = [(c["crossed"], k) for k in range(1, 25) if k != seed
                 for c in [graph_layout(projects, k)] if not c["overlaps"]]
        note += (f' "seed": {min(clean)[1]} has no overlaps; set it on the graph section.' if clean else
                 ' No seed from 1 to 24 fixes it; move some technologies into "also".')
        LAYOUT_NOTES.append(note)
    pos, techs, deg, edges, lw, W, H = (g[k] for k in ("pos", "techs", "deg", "edges", "lw", "W", "H"))
    top = sorted(techs, key=lambda t: -deg[t])[:5]
    out = [f'<svg class="graph" viewBox="0 0 {W} {H}" role="img" aria-label="Knowledge graph linking projects to the technologies they use. Most shared: {esc(", ".join(top))}.">']
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{edge_col}" stroke-width="1.3"/>')
    for t in techs:
        x, y = pos[t]; r = 4 + deg[t] * 1.6; fs = 12 + deg[t] * 0.9; tw = len(t) * fs * 0.47
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#FFFFFF" stroke="{A}" stroke-width="1.6"/>')
        out.append(f'<rect x="{x - tw / 2 - 2:.1f}" y="{y - r - 4 - fs * 0.82:.1f}" width="{tw + 4:.1f}" height="{fs * 1.05:.1f}" fill="#FFFFFF" fill-opacity="0.9"/>')
        out.append(f'<text x="{x:.1f}" y="{y - r - 4:.1f}" text-anchor="middle" font-family="{COND}" font-size="{fs:.1f}" fill="{INK}">{esc(t)}</text>')
    for p in projects:
        x, y = pos[p]; w = lw(p) - 4
        out.append(f'<rect x="{x - w / 2:.1f}" y="{y - 12:.1f}" width="{w:.1f}" height="24" rx="12" fill="{A}"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-family="{SERIF}" font-size="14" font-weight="600" fill="#FFFFFF">{esc(p)}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ---------------------------------------------------------------- sections
def section_roles(s, th):
    out = []
    for r in s["roles"]:
        org = f', <span class="role-org">{md(r["org"])}</span>' if r.get("org") else ""
        out.append('<div class="role-block"><div class="role-head">'
                   f'<div><span class="role-title">{md(r["title"])}</span>{org}</div>'
                   f'<div class="dates">{esc(r.get("dates", ""))}</div></div>'
                   '<ul class="claims">' + "".join(claim(c, th) for c in r.get("claims", [])) + "</ul></div>")
    if s.get("note"):
        out.append(f'<p class="note">{md(s["note"])}</p>')
    return "".join(out)


def section_projects(s, th):
    items = []
    for p in s["items"]:
        year = f' ({esc(p["year"])})' if p.get("year") else ""
        items.append(claim({"lead": None, "text": f'**{p["name"]}**{year}. {p["text"]}',
                            "refs": p.get("refs"), "evidence": p.get("evidence")}, th))
    return '<ul class="claims">' + "".join(items) + "</ul>"


def section_entries(s, th):
    rows = []
    for e in s["items"]:
        org = f', <span class="role-org">{md(e["org"])}</span>' if e.get("org") else ""
        detail = f' <span class="role-org">{md(e["detail"])}</span>' if e.get("detail") else ""
        rows.append(f'<li class="entry"><span><span class="role-title" style="font-size:9.8pt">{md(e["title"])}</span>{org}{detail}</span>'
                    f'<span class="dates">{esc(e.get("dates", ""))}</span></li>')
    return '<ul class="entries">' + "".join(rows) + "</ul>"


def section_graph(s, th):
    out = f'<figure style="margin-top:.02in">{graph(s["graph"], th, s.get("seed", 7))}'
    if s.get("caption", True):
        cap = s["caption"] if isinstance(s.get("caption"), str) else \
            "Projects (filled) linked to the technologies they use. Larger nodes appear in more projects."
        out += f"<figcaption>{esc(cap)}</figcaption>"
    out += "</figure>"
    if s.get("also"):
        out += f'<p class="note"><span>Also:</span> {esc("; ".join(s["also"]))}.</p>'
    return out


def section_publications(s, th):
    rows = []
    for p in s["items"]:
        url = p.get("url") or (f'https://doi.org/{p["doi"]}' if p.get("doi") else None)
        label = p.get("link_label") or ("DOI" if p.get("doi") else "Link")
        link = f' <a class="link" href="{esc(url)}">{esc(label)}</a>' if url else ""
        date = f' <span class="meta">{esc(p["date"])}</span>' if p.get("date") else ""
        venue = f' {md(p["venue"])}.' if p.get("venue") else ""
        stop = "" if str(p["title"]).rstrip().endswith(("?", "!", ".")) else "."
        rows.append(f'<li><em>{esc(p["title"])}{stop}</em>{venue}{date}{link}</li>')
    return '<ol class="refs">' + "".join(rows) + "</ol>"


RENDER = {"roles": section_roles, "projects": section_projects, "entries": section_entries,
          "graph": section_graph, "publications": section_publications}


# ---------------------------------------------------------------- checks before rendering
DATE_RE = re.compile(r"\d{4}(-\d{1,2})?")
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def validate(data):
    """Return (errors, warnings). Each message names the place in the JSON, so the
    file can be fixed without reading a Python traceback."""
    errs, warns = [], []
    figures = []   # every margin figure, with its source if it has one

    def is_num(v):
        if isinstance(v, bool):
            return False
        try:
            float(v); return True
        except (TypeError, ValueError):
            return False

    def text(obj, key, where, required=True):
        v = obj.get(key)
        if v is None or v == "":
            if required:
                errs.append(f'{where}: "{key}" is missing.')
            return False
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            errs.append(f'{where}: "{key}" must be text.'); return False
        return True

    def items(obj, key, where, required=True):
        v = obj.get(key)
        if v is None:
            if required:
                errs.append(f'{where}: "{key}" is missing (it must be a list).')
            return []
        if not isinstance(v, list):
            errs.append(f'{where}: "{key}" must be a list in [ ].'); return []
        if required and not v:
            errs.append(f'{where}: "{key}" is empty.')
        out = []
        for i, x in enumerate(v):
            if isinstance(x, dict):
                out.append((i, x))
            else:
                errs.append(f'{where} > {key}[{i}]: must be an object in {{ }}.')
        return out

    def date(v, where, key, allow_present=True):
        if v is None:
            return None
        s = str(v).strip()
        if allow_present and s in ("", "present", "now"):
            return float("inf")
        m = DATE_RE.fullmatch(s)
        if not m or not 1 <= int(s[5:] or 1) <= 12:
            errs.append(f'{where}: "{key}" is {v!r}; use "YYYY", "YYYY-MM"' + (' or "present".' if allow_present else "."))
            return None
        return int(s[:4]) + (int(s[5:] or 1) - 1) / 12

    def color(v, where, key):
        if v is not None and not (isinstance(v, str) and HEX_RE.fullmatch(v)):
            errs.append(f'{where}: "{key}" is {v!r}; use a six-digit hex color like "#0F6E6E".')

    def check_source(obj, where):
        v = obj.get("source")
        ok = lambda x: isinstance(x, str) and x.strip()
        if v is not None and not (ok(v) or (isinstance(v, list) and v and all(ok(x) for x in v))):
            errs.append(f'{where}: "source" must be text, or a list of texts, saying where the number comes from.')

    def check_evidence(ev, where):
        if ev is None:
            return
        if not isinstance(ev, dict):
            errs.append(f'{where}: "evidence" must be an object in {{ }} or null.'); return
        check_source(ev, f"{where} > evidence")
        if ev.get("value") not in (None, ""):
            figures.append(dict(where=where, figure=" ".join(str(ev[k]) for k in ("value", "label") if ev.get(k)),
                                source=ev.get("source")))
        c = ev.get("chart")
        if c is None:
            return
        w = f"{where} > evidence > chart"
        if not isinstance(c, dict):
            errs.append(f"{w}: must be an object in {{ }}."); return
        kind = c.get("type")

        def number(key, required=True, positive=False):
            v = c.get(key)
            if v is None:
                if required:
                    errs.append(f'{w}: a "{kind}" chart needs "{key}".')
                return None
            if not is_num(v):
                errs.append(f'{w}: "{key}" is {v!r}; it must be a number.'); return None
            if positive and float(v) <= 0:
                errs.append(f'{w}: "{key}" must be greater than 0.'); return None
            return float(v)

        if kind == "fill":
            v, mx = number("value"), number("max", required=False, positive=True)
            top = mx if mx is not None else 1
            if v is not None and v > top:
                warns.append(f'{w}: "value" {v:g} is larger than "max" {top:g}, so the bar overflows. '
                             'For a percentage use 0.71, or set "max": 100.')
        elif kind == "range":
            a, b = number("from"), number("to")
            mx = number("max", required=False, positive=True); number("baseline", required=False)
            top = mx if mx is not None else 100
            if a is not None and b is not None:
                if a > b:
                    errs.append(f'{w}: "from" {a:g} is larger than "to" {b:g}.')
                elif b > top:
                    warns.append(f'{w}: "to" {b:g} is larger than "max" {top:g}, so the bar overflows.')
        elif kind == "bars":
            number("max", required=False, positive=True)
            for i, it in items(c, "items", w):
                if text(it, "label", f"{w} > items[{i}]") and not is_num(it.get("value")):
                    errs.append(f'{w} > items[{i}]: "value" is {it.get("value")!r}; it must be a number.')
        else:
            errs.append(f'{w}: "type" is {kind!r}; use "fill", "range" or "bars".')

    if not isinstance(data, dict):
        return ["The file must be one JSON object in { }."], []
    text(data, "name", "top level")
    if data.get("master") is not None and not (isinstance(data["master"], str) and data["master"].strip()):
        errs.append('top level: "master" must be the path of the master JSON file, relative to this file.')
    if str(data.get("paper", "letter")).lower() not in PAPERS:
        errs.append(f'top level: "paper" is {data["paper"]!r}; use "letter" or "a4".')
    date(data.get("as_of"), "top level", "as_of", allow_present=False)
    theme = data.get("theme") or {}
    if not isinstance(theme, dict):
        errs.append('top level: "theme" must be an object in { }.'); theme = {}
    for k in ("accent", "secondary", "now"):
        color(theme.get(k), "theme", k)
    if not isinstance(data.get("contact", []), list):
        errs.append('top level: "contact" must be a list of lines.')
    else:
        for i, line in enumerate(data.get("contact", [])):
            for j, item in enumerate(line if isinstance(line, list) else [line]):
                if isinstance(item, dict) and not (item.get("text") and item.get("href")):
                    errs.append(f'contact[{i}][{j}]: a link needs both "text" and "href".')

    tl = data.get("timeline")
    if tl is not None:
        if not isinstance(tl, dict):
            errs.append('top level: "timeline" must be an object in { }.')
        else:
            cats = tl.get("categories") or {}
            if not isinstance(cats, dict):
                errs.append('timeline: "categories" must be an object in { }.'); cats = {}
            for k, c in cats.items():
                if not isinstance(c, dict):
                    errs.append(f'timeline > categories > {k}: must be an object in {{ }}.'); continue
                text(c, "label", f"timeline > categories > {k}")
                color(c.get("color"), f"timeline > categories > {k}", "color")
            for i, b in items(tl, "bars", "timeline"):
                w = f"timeline > bars[{i}]" + (f' "{b["label"]}"' if isinstance(b.get("label"), str) else "")
                text(b, "label", w)
                a = None
                if b.get("start") in (None, ""):
                    errs.append(f'{w}: "start" is missing.')
                else:
                    a = date(b["start"], w, "start", allow_present=False)
                z = date(b.get("end"), w, "end")
                if a is not None and z is not None and z < a:
                    errs.append(f'{w}: "end" {b["end"]!r} is before "start" {b["start"]!r}.')
                if b.get("category") is not None and b["category"] not in cats:
                    errs.append(f'{w}: category {b["category"]!r} is not defined in timeline > categories '
                                f'({", ".join(cats) or "none defined"}).')

    cited, n_pubs, highlights = [], 0, 0

    def refs(obj, where):
        r = obj.get("refs")
        if r is None:
            return
        if not isinstance(r, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in r):
            errs.append(f'{where}: "refs" must be a list of whole numbers, like [1, 3].'); return
        cited.extend((x, where) for x in r)

    for i, s in items(data, "sections", "top level"):
        w = f"sections[{i}]" + (f' "{s["title"]}"' if isinstance(s.get("title"), str) else "")
        kind = s.get("type")
        if kind not in RENDER:
            errs.append(f'{w}: "type" is {kind!r}; use {", ".join(RENDER)}.'); continue
        text(s, "title", w)
        highlights += bool(s.get("highlight"))
        if kind == "roles":
            for j, r in items(s, "roles", w):
                wr = f"{w} > roles[{j}]" + (f' "{r["title"]}"' if isinstance(r.get("title"), str) else "")
                text(r, "title", wr)
                for k, c in items(r, "claims", wr, required=False):
                    wc = f"{wr} > claims[{k}]"
                    text(c, "text", wc); refs(c, wc); check_source(c, wc); check_evidence(c.get("evidence"), wc)
        elif kind == "projects":
            for j, p in items(s, "items", w):
                wp = f"{w} > items[{j}]" + (f' "{p["name"]}"' if isinstance(p.get("name"), str) else "")
                text(p, "name", wp); text(p, "text", wp); refs(p, wp); check_source(p, wp); check_evidence(p.get("evidence"), wp)
        elif kind == "entries":
            for j, e in items(s, "items", w):
                text(e, "title", f"{w} > items[{j}]")
        elif kind == "publications":
            pubs = items(s, "items", w); n_pubs += len(pubs)
            for j, p in pubs:
                text(p, "title", f"{w} > items[{j}]")
        elif kind == "graph":
            g = s.get("graph")
            if not isinstance(g, dict) or not g:
                errs.append(f'{w}: "graph" must be an object mapping each project to a list of technologies.')
            else:
                for proj, techs in g.items():
                    if not isinstance(techs, list) or not techs or not all(isinstance(t, str) for t in techs):
                        errs.append(f'{w} > graph > "{proj}": must be a non-empty list of technology names.')
            if s.get("also") is not None and not isinstance(s["also"], list):
                errs.append(f'{w}: "also" must be a list.')
            if s.get("seed") is not None and (not isinstance(s["seed"], int) or isinstance(s["seed"], bool)):
                errs.append(f'{w}: "seed" must be a whole number.')

    for n, where in cited:
        if n_pubs == 0:
            warns.append(f"{where}: cites [{n}] but there is no publications section.")
        elif not 1 <= n <= n_pubs:
            warns.append(f"{where}: cites [{n}] but the publications list has only {n_pubs} item{'s' if n_pubs != 1 else ''}.")
    if highlights > 1:
        warns.append(f'{highlights} sections have "highlight": true; the tinted panel is meant to be used once.')
    return errs, warns, figures


def sources_report(figures, full=False):
    """Lines to print about where the margin figures come from."""
    if not figures:
        return []
    src = lambda f: "; ".join(f["source"]) if isinstance(f["source"], list) else f["source"]
    have = [f for f in figures if f["source"]]
    missing = [f for f in figures if not f["source"]]
    out = [f"sources: {len(have)} of {len(figures)} margin figures have a source."]
    if full and have:
        out += [f"  {f['figure']}  <-  {src(f)}" for f in have]
    if missing:
        out.append('warning: no "source" for these figures. Add one to each "evidence" (a file, a link, '
                   'or who confirmed it and when), or remove the figure:')
        out += [f"  - {f['where']}: {f['figure']}" for f in missing]
    return out


# ---------------------------------------------------------------- layout checks after rendering
CHECK_JS = """
(async () => {
  try { await document.fonts.ready; } catch (e) {}
  const lines = el => {
    const r = document.createRange(); r.selectNodeContents(el);
    const rects = [...r.getClientRects()].filter(q => q.width > 0.5).sort((a, b) => a.top - b.top);
    const out = [];
    for (const q of rects) {
      const mid = (q.top + q.bottom) / 2, last = out[out.length - 1];
      if (last && mid > last.top && mid < last.bottom) {
        last.left = Math.min(last.left, q.left); last.right = Math.max(last.right, q.right);
        last.top = Math.min(last.top, q.top); last.bottom = Math.max(last.bottom, q.bottom);
      } else out.push({ top: q.top, bottom: q.bottom, left: q.left, right: q.right });
    }
    return out;
  };
  const measure = el => {
    if (!el) return null;
    const l = lines(el), w = el.getBoundingClientRect().width, last = l[l.length - 1];
    return { n: l.length, last: last && w ? (last.right - last.left) / w : 1 };
  };
  const res = { headline: measure(document.querySelector('.headline')),
                summary: measure(document.querySelector('.summary')), claims: [] };
  for (const li of document.querySelectorAll('.claim')) {
    const p = li.querySelector('p'), b = li.querySelector('.ev b');
    res.claims.push(Object.assign({ text: p.textContent.trim().slice(0, 44),
      value: b ? b.textContent : '', vlines: b ? lines(b).length : 0 }, measure(p)));
  }
  document.documentElement.setAttribute('data-layout', JSON.stringify(res));
})();
"""


def layout_checks(browser, page_html, paper):
    """Lay the page out at its print width in the browser and measure it.
    Returns a list of problems, or None if the measurement could not be run."""
    width = CONTENT_IN[paper]
    probe = page_html.replace("</style>", f"@media screen {{ body {{ padding: 0; margin: 0; width: {width}in; max-width: none; }} }}\n</style>", 1)
    probe = probe.replace("</body>", f"<script>{CHECK_JS}</script>\n</body>", 1)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "probe.html"; f.write_text(probe, encoding="utf8")
            with tempfile.TemporaryDirectory() as prof:
                r = subprocess.run([browser, "--headless=new", "--disable-gpu", "--window-size=1400,1800",
                                    "--virtual-time-budget=8000", f"--user-data-dir={prof}", "--dump-dom", f.resolve().as_uri()],
                                   capture_output=True, timeout=120)
        m = re.search(r'data-layout="([^"]*)"', r.stdout.decode("utf8", "replace"))
        res = json.loads(html.unescape(m.group(1)))
    except Exception:
        return None
    notes = []
    if res.get("headline") and res["headline"]["n"] > 1:
        notes.append("the headline wraps onto two lines; shorten it.")
    if res.get("summary") and res["summary"]["n"] > 1 and res["summary"]["last"] < 0.15:
        notes.append("the summary ends with a nearly empty last line; trim or add a few words.")
    for c in res.get("claims", []):
        name = f'bullet "{c["text"]}..."'
        if c["n"] > 3:
            notes.append(f'{name} runs to {c["n"]} lines; keep bullets to three at most.')
        elif c["n"] > 1 and c["last"] < 0.15:
            notes.append(f'{name} ends with a nearly empty last line; trim a few words.')
        if c["vlines"] > 1:
            notes.append(f'margin figure "{c["value"]}" wraps onto {c["vlines"]} lines; shorten it.')
    return notes


# ---------------------------------------------------------------- page
def build(data, paper=None):
    theme = data.get("theme", {})
    paper = (paper or data.get("paper") or "letter").lower()
    accent = theme.get("accent", "#0F6E6E")
    th = {"accent": accent, "secondary": theme.get("secondary", "#A9B3C1"), "now": theme.get("now", "#D99A1E"),
          "tint": mix(accent, "#FFFFFF", 0.86)}
    today = datetime.date.today()
    as_of = data.get("as_of") or f"{today.year}-{today.month:02d}"
    now = year_of(as_of, None) + 0.05
    as_of_label = datetime.date(int(as_of[:4]), int(as_of[5:7] or 1) if len(as_of) > 4 else 1, 1).strftime("%b %Y")

    contact_lines = []
    for line in data.get("contact", []):
        parts = []
        for item in line if isinstance(line, list) else [line]:
            if isinstance(item, dict):
                parts.append(f'<a href="{esc(item["href"])}">{esc(item["text"])}</a>')
            else:
                parts.append(esc(item))
        contact_lines.append(" &nbsp;|&nbsp; ".join(parts))

    body = [f'<header class="masthead"><div><h1 class="name">{esc(data["name"])}</h1>'
            f'<p class="headline">{md(data.get("headline", ""))}</p></div>'
            f'<address class="contact">{"<br>".join(contact_lines)}</address></header>']
    tl = data.get("timeline")
    body.append('<div class="intro">' f'<p class="summary">{md(data.get("summary", ""))}</p>'
                + (legend(tl, th, as_of_label) if tl else "<div></div>") + "</div>")
    if tl:
        body.append(f'<figure aria-label="Career timeline">{timeline(tl, th, now)}</figure>')
    for i, s in enumerate(data.get("sections", [])):
        kind = s.get("type")
        if kind not in RENDER:
            sys.exit(f"Unknown section type {kind!r}: use {', '.join(RENDER)}.")
        cls = ' class="panel"' if s.get("highlight") else ""
        body.append(f'<section{cls} aria-labelledby="s{i}"><h2 id="s{i}">{esc(s["title"])}</h2>{RENDER[kind](s, th)}</section>')

    css = CSS_PATH.read_text(encoding="utf8")
    running = f'"{data["name"]}, page " counter(page)'.replace("\\", "")
    vars_ = (f':root {{ --accent: {accent}; --accent-tint: {th["tint"]}; --panel: {mix(accent, "#FFFFFF", 0.94)};'
             f' --panel-rule: {mix(accent, "#FFFFFF", 0.75)}; --now: {th["now"]}; }}'
             f'@page {{ size: {PAPERS[paper]}; @top-right {{ content: {running}; }} }} @page :first {{ @top-right {{ content: none; }} }}')
    faces, link = font_faces("\n".join(body))
    title = data.get("title") or f'{data["name"]} – Resume'
    return ("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{esc(title)}</title>\n{link}\n<style>\n{faces}\n{css}\n{vars_}\n</style>\n</head>\n<body>\n"
            + "\n".join(body) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- pdf
def find_browser(explicit=None):
    cands = [explicit, os.environ.get("RESUME_BROWSER")]
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge"):
        cands.append(shutil.which(name))
    cands += [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for c in cands:
        if c and pathlib.Path(c).exists():
            return c
    return None


def print_pdf(browser, html_path, pdf_path):
    pdf_path = pathlib.Path(pdf_path).resolve()
    if pdf_path.exists():
        pdf_path.unlink()
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=8000", f"--user-data-dir={prof}",
                        f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    if not pdf_path.exists():
        sys.exit(f"The browser did not write {pdf_path}. Open the HTML and print it to PDF by hand, "
                 "or pass --browser with a different Chrome, Edge or Chromium.")
    data = pdf_path.read_bytes()
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json")
    ap.add_argument("--out", default=None, help="output folder (default: next to the JSON)")
    ap.add_argument("--name", default=None, help="output file stem (default: from the person's name)")
    ap.add_argument("--paper", default=None, choices=sorted(PAPERS), type=str.lower,
                    help='page size (default: "paper" in the JSON, else letter)')
    ap.add_argument("--sources", action="store_true", help="list every margin figure with its source")
    ap.add_argument("--plain", action="store_true",
                    help="also write a one-column version without charts (PDF and .docx) for upload forms")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--browser", default=None, help="path to Chrome, Edge or Chromium")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):   # resume text can hold characters a Windows console cannot encode
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    src = pathlib.Path(a.json)
    if not src.is_file():
        sys.exit(f"No such file: {src}")
    try:
        data = json.loads(src.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"{src.name} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}.")
    errs, warns, figures = validate(data)
    master_note = None
    if not errs and data.get("master"):   # a tailored version: it must be a faithful cut of its master
        sys.path.insert(0, str(HERE))
        import variant
        master, problem = variant.load_master(src, data)
        if problem:
            errs.append(problem)
        else:
            drift, summary = variant.check(master, data)
            errs += [f"differs from the master: {d}" for d in drift]
            master_note = f"master: faithful cut of {pathlib.Path(data['master']).name} ({summary})."
    for w in warns:
        print(f"warning: {w}")
    if errs:
        print(f"{src.name} has {len(errs)} problem{'s' if len(errs) != 1 else ''} to fix before it can render:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    out = (pathlib.Path(a.out) if a.out else src.parent).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = a.name or re.sub(r"[^A-Za-z0-9]+", "-", data["name"]).strip("-") + "-Resume"
    html_path = out / f"{stem}.html"
    paper = (a.paper or data.get("paper") or "letter").lower()
    page_html = build(data, paper)
    html_path.write_text(page_html, encoding="utf8")
    if master_note:
        print(master_note)
    for line in sources_report(figures, a.sources):
        print(line)
    print(f"html: {html_path}")
    for n in LAYOUT_NOTES:
        print(f"warning: {n}")
    browser = None if a.no_pdf else find_browser(a.browser)
    if a.plain:
        sys.path.insert(0, str(HERE))
        import plain
        docx_path = out / f"{stem}-plain.docx"
        plain.to_docx(data, docx_path, paper)
        print(f"plain docx: {docx_path}")
        if browser:
            with tempfile.TemporaryDirectory() as tmp:
                plain_html = pathlib.Path(tmp) / "plain.html"
                plain_html.write_text(plain.to_html(data, paper), encoding="utf8")
                plain_pdf = out / f"{stem}-plain.pdf"
                n = print_pdf(browser, plain_html, plain_pdf)
            print(f"plain pdf: {plain_pdf} ({n} page{'s' if n != 1 else ''})")
    if a.no_pdf:
        return
    if not browser:
        print("pdf: skipped, no Chrome, Edge or Chromium found. Open the HTML in a browser and print to PDF "
              "(default margins, background graphics on), or pass --browser PATH.")
        return
    pdf_path = out / f"{stem}.pdf"
    pages = print_pdf(browser, html_path, pdf_path)
    print(f"pdf: {pdf_path}")
    print(f"pages: {pages}")
    if pages > 2:
        print("warning: over two pages. Tighten copy (see SKILL.md, 'Fitting two pages') and render again.")
    notes = layout_checks(browser, page_html, paper)
    if notes is None:
        print("layout: could not be measured; check the PDF by eye.")
    else:
        for n in notes:
            print(f"warning: {n}")
        if not notes and not LAYOUT_NOTES:
            print("layout: no problems found.")


if __name__ == "__main__":
    main()
