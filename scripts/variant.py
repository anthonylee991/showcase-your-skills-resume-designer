#!/usr/bin/env python3
"""Check a tailored resume against the master it was cut from.

A tailored version (a "variant") may choose, reorder and reword. It may not change a number,
add a number, change a margin figure, or change a role's title, employer or dates.

usage:  python variant.py master.json variant.json

render.py runs the same check by itself when the variant has "master": "master.json"
(a path relative to the variant file) and refuses to render if the check fails.
Standard library only.
"""
import json, pathlib, re, sys

NUM = re.compile(r"\d\S*")   # a number with whatever is attached to it: 1.2M, 9%, 3,000, 4–6×, 300+
EV_KEYS = ("value", "label", "chart", "note")


def numbers(*texts):
    """Every number in the texts, with its unit, as a set: '1.2M products; from 9% to 2%.' -> {'1.2M', '9%', '2%'}.
    Units are kept so that 2M cannot pass for 2%."""
    out = set()
    for t in texts:
        if t is None:
            continue
        if isinstance(t, (dict, list)):
            t = all_text(t)
        out |= {m.rstrip(".,;:)]}'\"!?*").lower() for m in NUM.findall(str(t))}
    return out


def all_text(node):
    if isinstance(node, dict):
        return " ".join(all_text(v) for k, v in node.items() if k not in ("source", "href", "color", "theme", "seed"))
    if isinstance(node, list):
        return " ".join(all_text(v) for v in node)
    return "" if node is None else str(node)


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def ev_core(ev):
    return {k: ev[k] for k in EV_KEYS if ev and ev.get(k) not in (None, "")}


def pub_titles(data):
    return [norm(p.get("title")) for s in data.get("sections", []) if s.get("type") == "publications" for p in s.get("items", [])]


def check(master, variant):
    """Return (errors, summary). errors is empty when the variant is a faithful cut of the master."""
    errs = []
    m_pubs, v_pubs = pub_titles(master), pub_titles(variant)
    everywhere = numbers(all_text(master))
    used = total = 0

    def cited(refs, pubs):
        return {pubs[r - 1] for r in refs or [] if isinstance(r, int) and 1 <= r <= len(pubs)}

    def check_claim(v, m, where):
        allowed = numbers(m.get("lead"), m.get("text"), m.get("name"), m.get("year"), ev_core(m.get("evidence")))
        extra = numbers(v.get("lead"), v.get("text")) - allowed
        if extra:
            errs.append(f'{where}: the text has {", ".join(sorted(extra))}, which the master bullet does not. '
                        "Numbers may be left out but not changed or added.")
        if v.get("evidence") and ev_core(v["evidence"]) != ev_core(m.get("evidence")):
            errs.append(f'{where}: the margin figure differs from the master '
                        f'({ev_core(v["evidence"]).get("value")!r} here, {ev_core(m.get("evidence")).get("value")!r} in the master). '
                        "Copy it unchanged or remove it.")
        gone = cited(v.get("refs"), v_pubs) - cited(m.get("refs"), m_pubs)
        if gone:
            errs.append(f'{where}: cites a publication the master bullet does not cite ("{sorted(gone)[0][:50]}"). '
                        "Check the reference numbers after reordering the publications.")

    # identity
    for key in ("name", "contact"):
        if variant.get(key) != master.get(key):
            errs.append(f'top level: "{key}" differs from the master.')
    for key in ("headline", "summary"):
        extra = numbers(variant.get(key)) - everywhere
        if extra:
            errs.append(f'top level: "{key}" has {", ".join(sorted(extra))}, which appears nowhere in the master.')

    # timeline: the career history is not tailored
    bar = lambda b: (norm(b.get("label")), str(b.get("start")), str(b.get("end") or "present"))
    m_bars = {bar(b) for b in (master.get("timeline") or {}).get("bars", [])}
    v_bars = {bar(b) for b in (variant.get("timeline") or {}).get("bars", [])}
    if variant.get("timeline") is not None and v_bars != m_bars:
        for b in sorted(v_bars - m_bars):
            errs.append(f'timeline: the bar "{b[0]}" ({b[1]} to {b[2]}) is not in the master, or its dates differ.')
        for b in sorted(m_bars - v_bars):
            errs.append(f'timeline: the master bar "{b[0]}" is missing. A variant keeps the whole career timeline.')

    # master lookups
    m_roles, m_projects, m_items, m_graph, m_also = {}, {}, [], {}, set()
    for s in master.get("sections", []):
        t = s.get("type")
        if t == "roles":
            for r in s.get("roles", []):
                m_roles[(norm(r.get("title")), norm(r.get("org")), norm(r.get("dates")))] = r
                total += len(r.get("claims", []))
        elif t == "projects":
            for p in s.get("items", []):
                m_projects[norm(p.get("name"))] = p
            total += len(s.get("items", []))
        elif t in ("entries", "publications"):
            m_items += s.get("items", [])
        elif t == "graph":
            for proj, techs in (s.get("graph") or {}).items():
                m_graph.setdefault(norm(proj), set()).update(norm(x) for x in techs)
            m_also |= {norm(a) for a in s.get("also", [])}
    m_techs = set().union(*m_graph.values()) if m_graph else set()

    for i, s in enumerate(variant.get("sections", [])):
        t = s.get("type")
        w = f'sections[{i}] "{s.get("title", "")}"'
        if s.get("note"):
            extra = numbers(s["note"]) - everywhere
            if extra:
                errs.append(f'{w}: the note has {", ".join(sorted(extra))}, which appears nowhere in the master.')
        if t == "roles":
            for j, r in enumerate(s.get("roles", [])):
                wr = f'{w} > roles[{j}] "{r.get("title", "")}"'
                m = m_roles.get((norm(r.get("title")), norm(r.get("org")), norm(r.get("dates"))))
                if not m:
                    errs.append(f"{wr}: no role in the master has this exact title, organisation and dates.")
                    continue
                by_lead = {norm(c.get("lead")): c for c in m.get("claims", []) if c.get("lead")}
                by_text = {norm(c.get("text")): c for c in m.get("claims", [])}
                for k, c in enumerate(r.get("claims", [])):
                    mc = by_lead.get(norm(c.get("lead"))) if c.get("lead") else None
                    mc = mc or by_text.get(norm(c.get("text")))
                    if not mc:
                        errs.append(f'{wr} > claims[{k}]: no bullet in this master role has the lead "{c.get("lead", "")}" '
                                    "or the same text. Keep the lead unchanged so the bullet can be matched.")
                        continue
                    used += 1
                    check_claim(c, mc, f"{wr} > claims[{k}]")
        elif t == "projects":
            for j, p in enumerate(s.get("items", [])):
                wp = f'{w} > items[{j}] "{p.get("name", "")}"'
                m = m_projects.get(norm(p.get("name")))
                if not m:
                    errs.append(f"{wp}: no project with this name in the master."); continue
                used += 1
                if str(p.get("year") or "") != str(m.get("year") or ""):
                    errs.append(f"{wp}: the year differs from the master.")
                check_claim(p, m, wp)
        elif t in ("entries", "publications"):
            strip = lambda d: {k: v for k, v in d.items() if v not in (None, "")}
            pool = [strip(x) for x in m_items]
            for j, e in enumerate(s.get("items", [])):
                if strip(e) not in pool:
                    errs.append(f'{w} > items[{j}] "{str(e.get("title", ""))[:50]}": not found unchanged in the master.')
        elif t == "graph":
            for proj, techs in (s.get("graph") or {}).items():
                if norm(proj) not in m_graph:
                    errs.append(f'{w} > graph > "{proj}": not a project in the master graph.'); continue
                for x in techs:
                    if norm(x) not in m_graph[norm(proj)]:
                        errs.append(f'{w} > graph > "{proj}": the master does not link this project to "{x}".')
            for a in s.get("also", []):
                if norm(a) not in m_also | m_techs:
                    errs.append(f'{w} > also: "{a}" is not in the master.')
    return errs, f"{used} of {total} master bullets used"


def left_out(master, variant):
    """Leads (or names) of master bullets that the variant does not carry."""
    kept = {norm(c.get("lead") or c.get("text")) for s in variant.get("sections", []) if s.get("type") == "roles"
            for r in s.get("roles", []) for c in r.get("claims", [])}
    kept |= {norm(p.get("name")) for s in variant.get("sections", []) if s.get("type") == "projects" for p in s.get("items", [])}
    out = []
    for s in master.get("sections", []):
        if s.get("type") == "roles":
            for r in s.get("roles", []):
                out += [f'{r.get("title")}: {c.get("lead") or str(c.get("text"))[:50]}' for c in r.get("claims", [])
                        if norm(c.get("lead") or c.get("text")) not in kept]
        elif s.get("type") == "projects":
            out += [f'Project: {p.get("name")}' for p in s.get("items", []) if norm(p.get("name")) not in kept]
    return out


def load_master(variant_path, variant):
    """The master named by the variant's "master" field, or (None, error message)."""
    path = (pathlib.Path(variant_path).parent / str(variant["master"])).resolve()
    if not path.is_file():
        return None, f'"master" points to {path}, which does not exist.'
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except json.JSONDecodeError as e:
        return None, f"the master {path.name} is not valid JSON: {e.msg} at line {e.lineno}."


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    master, variant = (json.loads(pathlib.Path(p).read_text(encoding="utf-8-sig")) for p in sys.argv[1:3])
    errs, summary = check(master, variant)
    if errs:
        print(f"The variant differs from the master in {len(errs)} place{'s' if len(errs) != 1 else ''}:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print(f"master: the variant is a faithful cut ({summary}).")
    for line in left_out(master, variant):
        print(f"  left out  {line}")


if __name__ == "__main__":
    main()
