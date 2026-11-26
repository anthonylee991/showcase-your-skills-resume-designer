# Resume JSON reference

All text fields accept `**bold**` and `*italic*`. Dates are `"YYYY"`, `"YYYY-MM"` or `"present"`.

`render.py` checks the file against this reference before it renders and lists every problem with its place in the file. Unknown extra keys (such as `_comment`) are ignored.

## Top level

| Field | Required | Meaning |
| :--- | :--- | :--- |
| `name` | yes | Shown large at the top and in the page-2 running head. |
| `headline` | | One line under the name, in italics. Keep it under about 55 characters so it stays on one line. |
| `contact` | | List of lines. Each line is a list of items; an item is plain text or `{ "text": ..., "href": ... }`. Items on a line are joined with a vertical bar. Three or four lines fit. |
| `summary` | | Three to five sentences. Shown beside the timeline legend. |
| `paper` | | `"letter"` (default) or `"a4"`. Use A4 outside the United States and Canada. `--paper` on the command line overrides it. |
| `master` | | Only in a version tailored to one job: the path of the master JSON, relative to this file. The renderer then refuses to render if a number, margin figure, role title, organisation, date or timeline bar differs from the master. See "Tailoring to a job" in SKILL.md. |
| `as_of` | | `"YYYY-MM"` for the "now" line. Defaults to the current month. |
| `theme` | | `{ "accent": "#0F6E6E", "secondary": "#A9B3C1", "now": "#D99A1E" }`, all optional. |
| `title` | | Browser tab title. Defaults to "<name> – Resume". |
| `timeline` | | See below. Omit it to skip the chart and legend. |
| `sections` | yes | Ordered list of sections, rendered top to bottom. |

## `timeline`

```json
"timeline": {
  "categories": {
    "analytics": { "label": "Analytics",      "color": "#A9B3C1" },
    "ml":        { "label": "ML engineering", "color": "#0F6E6E" }
  },
  "bars": [
    { "label": "Northwind Retail: data analyst", "start": "2016-09", "end": "2020-08", "category": "analytics" },
    { "label": "Basket", "start": "2023-04", "end": "present", "category": "ml" }
  ],
  "aria": "Optional description of the chart for screen readers."
}
```

Bars are packed into as few lanes as possible. A label goes inside its bar when it fits and to the right of the bar otherwise, so short recent roles still get readable labels.

## Sections

Every section has `type` and `title`. Add `"highlight": true` to draw it as the tinted panel (use it once, for current work).

### `roles`

```json
{ "type": "roles", "title": "Current work", "highlight": true,
  "roles": [
    { "title": "AI Engineer (contract)", "org": "Acme, remote", "dates": "Aug 2026 – present",
      "claims": [ { "lead": "Search platform.", "text": "...", "refs": [3], "evidence": { ... } } ] }
  ],
  "note": "Earlier: one line listing older roles." }
```

### `projects`

```json
{ "type": "projects", "title": "Open-source projects",
  "items": [ { "name": "tiny-bm25", "year": "2021", "text": "...", "refs": [1], "evidence": { ... } } ] }
```

### `graph`

```json
{ "type": "graph", "title": "Stack",
  "graph": { "Project A": ["Python", "PostgreSQL"], "Project B": ["Python", "MCP"] },
  "also": ["Docker", "Terraform"],
  "caption": "Optional caption. Set false to hide it.",
  "seed": 7 }
```

The skills graph is a standard part of the page: the renderer warns when no section of this type is present. Project names become filled labels; technologies become circles sized by how many projects use them. Change `seed` if the layout comes out tangled.

### `entries`

Compact one-line items with the date in the margin, for education, certifications or awards.

```json
{ "type": "entries", "title": "Education",
  "items": [ { "title": "MSc Computer Science", "org": "University of Porto", "detail": "optional", "dates": "2016" } ] }
```

### `publications`

Numbered list; bullets cite items by number with `"refs": [n]`. Numbers follow the order of `items`, so if you reorder or remove an item, update every `refs` that points past it; the renderer warns when a number has no matching item.

```json
{ "type": "publications", "title": "Research pre-prints",
  "items": [ { "title": "...", "venue": "optional", "date": "Apr 2026", "doi": "10.5281/zenodo.123", "url": "optional instead of doi", "link_label": "optional, default DOI or Link" } ] }
```

## `evidence` (margin column)

```json
"evidence": {
  "value": "85%",
  "label": "right answer ranked first",
  "chart": { ... },
  "note": "optional small caveat under the chart",
  "source": "eval/results.md, top-1 table, read Nov 2026"
}
```

Use `null` (or omit it) when the claim has no measured result.

`source` says where the figure comes from: a file, a link, or who confirmed it and when. It is text or a list of texts, and it is never printed on the resume. The renderer reports every figure that has a `value` and no `source`, and `--sources` lists them all. A claim or project item can carry its own `"source"` for numbers that appear only in its text.

### Chart types

| Type | Fields | Use it for |
| :--- | :--- | :--- |
| `fill` | `value`, optional `max` (default 1) | A share of a whole: `{ "type": "fill", "value": 308, "max": 509 }` |
| `range` | `from`, `to`, optional `max` (default 100), optional `baseline` | A span, optionally against a baseline: `{ "type": "range", "from": 2.5, "to": 3.1, "max": 3.5, "baseline": 1 }` |
| `bars` | `items` of `{ "label", "value", "highlight" }`, optional `max` | The same metric compared across systems: highlight the person's own result. |
