"""Plain version of the resume: one column, no charts, standard headings.

The designed PDF is for people. This version is for upload forms and applicant-tracking
systems, which often misread two-column pages: here each role's dates sit on the role's
own line and each margin figure is written into the end of its bullet.

Built from the same JSON, so the words and numbers are identical. Writes HTML (printed to
PDF by render.py) and a .docx. Standard library only.
"""
import html, re, zipfile

PAGE = {"letter": (12240, 15840, "Letter"), "a4": (11906, 16838, "A4")}   # twips, CSS name


# ---------------------------------------------------------------- content
def runs(s):
    """'a **b** *c*' -> [(text, bold, italic), ...]"""
    out = []
    for part in re.split(r"(\*\*.+?\*\*|(?<![\w*])\*(?!\*).+?\*(?!\*))", str(s)):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append((part[2:-2], True, False))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append((part[1:-1], False, True))
        else:
            out.append((part, False, False))
    return out


def flat(s):
    return "".join(t for t, _, _ in runs(s))


def result_text(ev):
    """Margin figure as the end of a sentence: 'Result: 71% first suggestion accepted.'"""
    if not ev or not (ev.get("value") or ev.get("label")):
        return ""
    bits = " ".join(str(ev[k]).strip() for k in ("value", "label") if ev.get(k))
    if ev.get("note"):
        bits += f" ({str(ev['note']).strip().lstrip('*')})"
    return f" Result: {bits.rstrip('.')}."


def cite(refs):
    return f" [{', '.join(str(r) for r in refs)}]" if refs else ""


def blocks(data):
    """The resume as a flat list of (kind, runs) in reading order.
    kinds: name, headline, contact, h (section heading), role, li, ol, p"""
    out = [("name", [(data["name"], True, False)])]
    if data.get("headline"):
        out.append(("headline", runs(data["headline"])))
    for line in data.get("contact", []):
        parts = [(i["text"] if isinstance(i, dict) else str(i)) for i in (line if isinstance(line, list) else [line])]
        out.append(("contact", [(" | ".join(parts), False, False)]))
    if data.get("summary"):
        out += [("h", [("Summary", True, False)]), ("p", runs(data["summary"]))]
    in_experience = False
    for s in data.get("sections", []):
        kind = s["type"]
        if kind == "roles":
            if not in_experience:   # every roles section goes under one standard heading
                out.append(("h", [("Experience", True, False)])); in_experience = True
            for r in s["roles"]:
                head = [(flat(r["title"]), True, False)]
                for extra in (r.get("org"), r.get("dates")):
                    if extra:
                        head.append((" | " + flat(extra), False, False))
                out.append(("role", head))
                for c in r.get("claims", []):
                    lead = [(flat(c["lead"]) + " ", True, False)] if c.get("lead") else []
                    out.append(("li", lead + runs(c["text"]) + [(cite(c.get("refs")) + result_text(c.get("evidence")), False, False)]))
            if s.get("note"):
                out.append(("p", runs(s["note"])))
            continue
        in_experience = False
        if kind == "projects":
            out.append(("h", [(s["title"], True, False)]))
            for p in s["items"]:
                year = f" ({p['year']})" if p.get("year") else ""
                out.append(("li", [(flat(p["name"]), True, False), (year + ". ", False, False)] + runs(p["text"])
                            + [(cite(p.get("refs")) + result_text(p.get("evidence")), False, False)]))
        elif kind == "graph":
            g = s["graph"]
            techs = sorted({t for v in g.values() for t in v}, key=lambda t: (-sum(t in v for v in g.values()), t.lower()))
            out.append(("h", [("Skills", True, False)]))
            out.append(("p", [(", ".join(techs + [str(a) for a in s.get("also", [])]) + ".", False, False)]))
            out.append(("p", [("Projects: " + "; ".join(f"{p} ({', '.join(v)})" for p, v in g.items()) + ".", False, False)]))
        elif kind == "entries":
            out.append(("h", [(s["title"], True, False)]))
            for e in s["items"]:
                line = [(flat(e["title"]), True, False)]
                if e.get("org"):
                    line.append((", " + flat(e["org"]), False, False))
                if e.get("detail"):
                    line.append((" " + flat(e["detail"]), False, False))
                if e.get("dates"):
                    line.append((" | " + str(e["dates"]), False, False))
                out.append(("p", line))
        elif kind == "publications":
            out.append(("h", [(s["title"], True, False)]))
            for p in s["items"]:
                title = str(p["title"]).rstrip()
                text = title + ("" if title.endswith(("?", "!", ".")) else ".")
                if p.get("venue"):
                    text += f" {flat(p['venue'])}."
                if p.get("date"):
                    text += f" {p['date']}."
                url = p.get("url") or (f"https://doi.org/{p['doi']}" if p.get("doi") else None)
                if url:
                    text += f" {url}"
                out.append(("ol", [(text, False, False)]))
    return out


# ---------------------------------------------------------------- html
CSS = """
@page { size: %s; margin: 0.8in; }
body { font: 10.5pt/1.4 Arial, Helvetica, sans-serif; color: #000; max-width: 6.9in; margin: 0 auto; }
h1 { font-size: 18pt; margin: 0; }
h2 { font-size: 12pt; margin: 14pt 0 4pt; text-transform: uppercase; letter-spacing: .03em; border-bottom: 1px solid #000; }
p { margin: 0 0 3pt; }
p.headline { font-size: 11.5pt; margin-bottom: 4pt; }
p.role { margin: 9pt 0 2pt; break-after: avoid; }
ul, ol { margin: 0 0 4pt; padding-left: 18pt; }
li { margin-bottom: 2pt; }
@media screen { body { padding: 0.8in; } }
"""


def _inline(rs):
    out = ""
    for text, bold, italic in rs:
        t = html.escape(text)
        if bold:
            t = f"<strong>{t}</strong>"
        if italic:
            t = f"<em>{t}</em>"
        out += t
    return out


def to_html(data, paper="letter"):
    body, open_list = [], None

    def close():
        nonlocal open_list
        if open_list:
            body.append(f"</{open_list}>"); open_list = None

    for kind, rs in blocks(data):
        want = {"li": "ul", "ol": "ol"}.get(kind)
        if want != open_list:
            close()
            if want:
                body.append(f"<{want}>"); open_list = want
        inner = _inline(rs)
        if kind == "name":
            body.append(f"<h1>{inner}</h1>")
        elif kind == "h":
            body.append(f"<h2>{html.escape(rs[0][0])}</h2>")
        elif kind in ("li", "ol"):
            body.append(f"<li>{inner}</li>")
        else:
            cls = f' class="{kind}"' if kind in ("headline", "contact", "role") else ""
            body.append(f"<p{cls}>{inner}</p>")
    close()
    title = html.escape(f'{data["name"]} – Resume')
    return ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f"<title>{title}</title>\n<style>{CSS % PAGE[paper][2]}</style>\n</head>\n<body>\n" + "\n".join(body) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- docx
def _x(s):
    return html.escape(s, quote=False)


def _run(text, bold=False, italic=False, size=None):
    props = ("<w:b/>" if bold else "") + ("<w:i/>" if italic else "") + (f'<w:sz w:val="{size}"/>' if size else "")
    return f'<w:r>{"<w:rPr>" + props + "</w:rPr>" if props else ""}<w:t xml:space="preserve">{_x(text)}</w:t></w:r>'


def _para(rs, style=None, num=None, size=None, before=0, after=60, keep=False):
    ppr = (f'<w:pStyle w:val="{style}"/>' if style else "") + ("<w:keepNext/>" if keep else "")
    if num:
        ppr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
    ppr += f'<w:spacing w:before="{before}" w:after="{after}"/>'
    return f"<w:p><w:pPr>{ppr}</w:pPr>{''.join(_run(t, b, i, size) for t, b, i in rs if t)}</w:p>"


W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def to_docx(data, path, paper="letter"):
    w, h, _ = PAGE[paper]
    body = []
    for kind, rs in blocks(data):
        if kind == "name":
            body.append(_para(rs, size=36, after=0))
        elif kind == "headline":
            body.append(_para(rs, size=23, after=40))
        elif kind == "contact":
            body.append(_para(rs, after=0))
        elif kind == "h":
            body.append(_para([(rs[0][0].upper(), True, False)], style="Heading1", before=240, after=80, keep=True))
        elif kind == "role":
            body.append(_para(rs, before=160, after=40, keep=True))
        elif kind == "li":
            body.append(_para(rs, style="ListParagraph", num=1, after=40))
        elif kind == "ol":
            body.append(_para(rs, style="ListParagraph", num=2, after=40))
        else:
            body.append(_para(rs))
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W}><w:body>{"".join(body)}'
                f'<w:sectPr><w:pgSz w:w="{w}" w:h="{h}"/><w:pgMar w:top="1152" w:right="1152" w:bottom="1152" w:left="1152" '
                'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W}>'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>'
              '<w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="en-US"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="60" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
              '<w:next w:val="Normal"/><w:pPr><w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>'
              '<w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>'
              '<w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr></w:style></w:styles>')

    def level(fmt, text, font=""):
        return (f'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr>{font}</w:lvl>')

    numbering = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {W}>'
                 f'<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/>'
                 + level("bullet", "•", '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/></w:rPr>') + '</w:abstractNum>'
                 '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/>' + level("decimal", "%1.") + '</w:abstractNum>'
                 '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num><w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num></w:numbering>')
    pkg = "http://schemas.openxmlformats.org/package/2006"
    office = "http://schemas.openxmlformats.org/officeDocument/2006"
    wml = "application/vnd.openxmlformats-officedocument.wordprocessingml"
    parts = {
        "[Content_Types].xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="{pkg}/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                               '<Default Extension="xml" ContentType="application/xml"/>'
                               f'<Override PartName="/word/document.xml" ContentType="{wml}.document.main+xml"/>'
                               f'<Override PartName="/word/styles.xml" ContentType="{wml}.styles+xml"/>'
                               f'<Override PartName="/word/numbering.xml" ContentType="{wml}.numbering+xml"/>'
                               '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>',
        "_rels/.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}/relationships">'
                       f'<Relationship Id="rId1" Type="{office}/relationships/officeDocument" Target="word/document.xml"/>'
                       f'<Relationship Id="rId2" Type="{pkg}/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>',
        "word/_rels/document.xml.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{pkg}/relationships">'
                                        f'<Relationship Id="rId1" Type="{office}/relationships/styles" Target="styles.xml"/>'
                                        f'<Relationship Id="rId2" Type="{office}/relationships/numbering" Target="numbering.xml"/></Relationships>',
        "docProps/core.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                             f'<cp:coreProperties xmlns:cp="{pkg}/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                             f'<dc:title>{_x(data["name"])} - Resume</dc:title><dc:creator>{_x(data["name"])}</dc:creator></cp:coreProperties>',
        "word/document.xml": document, "word/styles.xml": styles, "word/numbering.xml": numbering,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():
            z.writestr(name, content)
