---
name: showcase-your-skills-resume-designer
description: Generate a designed two-page resume (HTML and print-ready PDF) where every claim sits beside its measured result in a margin column, with a career timeline chart, small charts in the margin, a tinted panel for current work, and a knowledge graph of the person's stack. Also writes a plain one-column version (PDF and Word) for upload forms, and checks a version tailored to one job against the master resume so that no number or date changes. Use when someone asks to make, redesign, refresh, update or tailor a resume or CV and wants it to look designed rather than like a Word template, or asks for this skill by name.
---

# Showcase Your Skills: resume designer

A resume generator with one idea: **every claim has its proof beside it.** The left column says what the person did; a narrow right margin shows the measured result (a big number, a short label, sometimes a small chart). A reader can skim the margin alone and get the person's impact in seconds.

The page also carries:
- a **career timeline** chart under the summary (every role as a bar, colored by kind of work, with a "now" line);
- a tinted **current work** panel that separates present roles from past ones;
- a **knowledge graph** linking projects to the technologies they use, which replaces a comma-separated skills list;
- a numbered **publications** list that bullets can cite, like "[3]".

You write a JSON file; `scripts/render.py` turns it into HTML and a PDF. Read `references/schema.md` for every field, and start from `examples/example.json` (fictional).

Two more things come from the same JSON:
- a **plain version** for upload forms and applicant-tracking systems (see "The plain version");
- **tailored versions** for one job each, checked against the master (see "Tailoring to a job").

## Workflow

1. **Gather the source material.** Ask for the existing resume, LinkedIn text, portfolio, repos, papers, or a description of their work. Read every file you are given in full. If you have access to their project folders or repos, look there for real numbers (READMEs, eval results, handoff docs, git history).
2. **Confirm before you invent nothing.** Every number on the page must come from a source or from the person. Never estimate, round up or fill a gap with a plausible figure. Make a short list of claims you could not verify and ask the person to confirm or correct them. Watch for stale facts: roles that ended, products that were shut down, projects that were replaced by newer ones.
3. **Pick the evidence for each claim.** For each bullet, choose the one result that best proves it: outcomes (conversion, revenue, accuracy, time saved, users served) beat volume (lines of code, tickets closed). If a claim has no real number, leave its margin empty: an empty margin is fine, an invented one is not.

   **Record where each margin figure comes from** in a `"source"` field on its `evidence`. The source is never printed on the resume; it lives in the JSON so that the person, or you in a later session, can trace every figure. Write something a person could follow back to the number:
   - a file and where in it: `"eval/results.md in the search repo, top-1 table"`;
   - a link and the date you read it: `"github.com/acme/tool, read Nov 2026"`;
   - the person's own word, with the date: `"confirmed by Maya in chat, 26 Nov 2026"`.

   "Their old resume" is a source only for the fact that they claimed it before; if that is all you have, write `"previous resume, not re-checked"` and put the figure on the list to confirm. Never write a source you did not actually use. Numbers inside the bullet text need the same care; add a `"source"` on the claim itself when the bullet carries a number that the margin does not.
4. **Choose charts only where they add information:**
   - `fill` for a share of a whole (60% completion, 308 of 509 files);
   - `range` for a span, optionally against a baseline (86–96%, 2.5–3.1× vs. 1×);
   - `bars` for a comparison on the *same* metric under the *same* conditions (yours vs. a competitor vs. a baseline). Put any caveat in `note` (for example, "*on 500 shared questions").
   Do not chart a single number that has nothing to compare against.
5. **Write the JSON** (see `references/schema.md`). Copy `examples/example.json` as a starting point. Writing rules:
   - Each bullet opens with a 2–5 word `lead` naming the thing ("Two-stage product search.").
   - Keep bullets to two lines, three at most. Active voice, plain words, no "responsible for", no filler adjectives.
   - Put present roles in a section with `"highlight": true` titled "Current work"; past roles in "Previous roles". Older or unrelated roles go in that section's `note` line and on the timeline only.
   - The timeline needs only `label`, `start`, `end` and `category` per bar. Use two or three categories at most (for example "Analytics" and "ML engineering").
   - In the stack graph, list each project with the technologies it actually uses. Put infrastructure and minor tools in `also`. Keep the graph to roughly 6–9 projects and 12–20 technologies.
   - Set `"paper"` to `"letter"` for the United States and Canada and `"a4"` everywhere else, going by where the person is applying, not where they live.
6. **Render:**
   ```
   python scripts/render.py path/to/resume.json --out path/to/output
   ```
   It checks the JSON first. If a field is missing or malformed it renders nothing and lists every problem with its place in the file (for example `sections[1] "Previous roles" > roles[0] > claims[2]: "text" is missing`); fix them all and run it again. Lines that start with `warning:` do not stop the render, but resolve each one: a bullet citing a publication number that does not exist, or a chart value larger than its `max`, is a mistake on the page.

   It then writes `<Name>-Resume.html` and `<Name>-Resume.pdf` and prints, in this order:
   - `sources:` how many margin figures have a source, and a list of those that do not. Give each one a source or remove the figure;
   - `pages:` the page count, with a warning above two;
   - layout warnings, measured in the browser at the print width: a bullet over three lines, a bullet or summary whose last line is nearly empty, a margin figure that wraps, a headline that wraps, a timeline label that runs off the edge, graph labels that overlap (with a `seed` that fixes it, when one exists). `layout: no problems found.` means all of these passed.

   Fix what it reports and render again until the output is clean. The PDF needs Chrome, Edge or Chromium (found automatically, or pass `--browser PATH`). The two typefaces are bundled in `assets/fonts` and written into the HTML, so rendering needs no internet. The one exception is text in Greek, Cyrillic or Vietnamese: the bundled files cover Latin scripts only, so for those the page loads the fonts from Google Fonts and needs a connection.
7. **Look at the PDF before you hand it over.** The renderer's checks cover the list above, not everything. Open the PDF and check what it cannot measure:
   - the margin figures line up with the bullets they prove;
   - links in the graph do not run through a label so that it is hard to read (try another `"seed"`);
   - the page break falls between sections or roles, not just under a heading;
   - the last page is not mostly empty.

   If the renderer printed `layout: could not be measured`, also check its list by eye.
8. **Deliver** the PDF (the version to send to people), the plain PDF and Word file (the versions to upload to application forms; add `--plain` to the render command), the HTML and the JSON (to edit later). Run the renderer once more with `--sources` and give the person the list it prints: every margin figure next to where it came from. Tell them what you cut, and point out each figure whose source is only their own word or an old resume, so they can check it before the resume goes out.

## The plain version

```
python scripts/render.py path/to/resume.json --out path/to/output --plain
```

This also writes `<Name>-Resume-plain.pdf` and `<Name>-Resume-plain.docx`: one column, no charts, standard headings ("Summary", "Experience", "Skills"). Each role's dates sit on the role's own line, each margin figure is written into the end of its bullet ("Result: 71% first suggestion accepted."), and the graph becomes a skills list. The words and numbers are the same as the designed version, because both come from one JSON file.

Tell the person which file is for what:
- the designed PDF goes to people: a recruiter's inbox, a hiring manager, a link on their site;
- the plain PDF or Word file goes into application forms that parse the resume into fields.

Why both: in the designed PDF the dates and figures sit in a margin column. Software that reads the PDF's stored text order gets everything in order. Software that rebuilds the reading order from positions on the page reads the main column first and the margin column afterwards, so dates and figures arrive detached from their roles. The plain version reads the same either way. See "What was measured" under Notes.

## Tailoring to a job

Keep one **master** JSON with everything: every role, every bullet, every figure, with sources. For a specific job, write a **variant**: a copy of the master with `"master": "master.json"` added at the top level (the path is relative to the variant file).

In a variant you may:
- choose which bullets, projects, publications and graph entries to keep, and put them in a different order;
- reword a bullet to use the job description's own terms, as long as its `lead` stays the same;
- rewrite the `headline` and `summary`.

In a variant you may not change a number or add one, change a margin figure, change a role's title, organisation or dates, or change the timeline. If you reorder or drop publications, renumber the `refs` that point to them.

The renderer enforces this. When the JSON has `"master"`, it compares every bullet with its master bullet before rendering, refuses to render if anything differs, and names each place. To see what a variant leaves out, run:

```
python scripts/variant.py path/to/master.json path/to/variant.json
```

Give that list to the person with the variant, so they know what this version omits.

How to tailor: read the job description, pick the master bullets that answer what it asks for, lead each role with the most relevant one, and cut bullets that do not help this application. Do not write a bullet for a requirement the person has no evidence for; tell them about the gap instead.

Limits of the check: numbers are compared with their units, so "2M" cannot replace "1.2M" and "300+" cannot become "300". The check on the headline and summary is looser: it only requires that each number appears somewhere in the master, so read those two fields against the master yourself. The check cannot tell whether reworded text still describes the same work; that is your responsibility.

## Fitting two pages

Cut words, not type size or margins. In this order:
1. Shorten bullets that run to a third line by a few words.
2. Move details that a margin chart already shows out of the bullet text.
3. Merge two weak bullets in an older role into one.
4. Move older roles into the `note` line (they stay on the timeline).
5. Move minor tools from the graph into `also`.
6. Drop the weakest bullet of the oldest role.

Tell the person every fact you removed.

## Notes

- **What was measured** (26 Nov 2026, on the example resume, 60 pieces of content checked for order: section, role, bullet, figure, label). Six text extractors were run on each file.
  - Designed PDF, extractors that follow the stored text order (pdftotext, pypdf, PyMuPDF) and pdfplumber: 59 or 60 of 60 in order on both paper sizes. Before the reading-order fix in this skill, the three stored-order extractors scored 13 of 60.
  - Designed PDF, extractors that rebuild order from page positions (pdfminer.six, pdftotext in layout mode): 41 to 48 of 60. The main column is read in order, but the margin column, including each role's dates, comes out as a separate block.
  - Plain PDF: 61 of 61 on all six extractors, with each role's dates on the role's line.
  - Not tested: any commercial applicant-tracking system, and any dedicated resume parser. Do not promise the person that a given system will parse either file; say what was measured.
- The PDF contains real text (not an image). Timeline and graph labels are also real text, and they come out as loose words wherever the chart sits.
- Every chart is SVG with a description for screen readers, written from the data (for example "Comparison: New 0.81, Old 0.62").
- If you edit `assets/style.css`, do not give bullets or their paragraphs a CSS `position`. Chrome writes positioned elements to the PDF last, which separates every bullet from its role when the text is extracted.
- The HTML is also responsive: on a phone the margin column folds under each bullet.
- Colors: one accent (`theme.accent`, default deep teal `#0F6E6E`) used for figures, current-work panel and graph; grey for secondary timeline bars; gold for the "now" line. Change the accent if the person has a brand color, but keep it dark enough for white text on the graph labels.
- Use only characters the typefaces have in margin figures and labels. An arrow (→), for example, is not in the condensed face and is drawn in a substitute font that differs from one computer to the next; write "9 days to 1".
- The fonts are Source Serif 4 and IBM Plex Sans Condensed, both under the SIL Open Font License (`assets/fonts/LICENSE.txt`).
- Requires Python 3.8+ (standard library only).
