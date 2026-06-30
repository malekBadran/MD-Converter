# md2doc

A CLI that converts Markdown (`.md`) files into Word (`.docx`) or HTML, with
clean table rendering, Mermaid.js diagram support, and full Arabic / RTL
text handling in both output formats.

## Why this stack

| Concern | Choice | Reason |
|---|---|---|
| Language | Python | Best-supported ecosystem for both OOXML (`python-docx`) and Markdown ASTs; one language for both writers. |
| Markdown parsing | `markdown-it-py` (+ `mdit-py-plugins`) | Mature CommonMark/GFM implementation with a token stream (not just an HTML string), which both writers need — the DOCX writer doesn't go through HTML at all. GFM tables and strikethrough come from the bundled `gfm-like` preset. |
| DOCX generation | `python-docx` | Direct OOXML control. Word's bidi/complex-script text model (`w:bidi`, `w:rtl`, `w:cs`) isn't exposed by python-docx's high-level API, so `docx_writer.py` talks to the underlying XML directly — this is what makes correct Arabic shaping/alignment possible. |
| Diagrams | Mermaid.js via `mermaid-cli` (local) or `mermaid.ink` (hosted fallback) for DOCX; `mermaid.js` loaded client-side for HTML | DOCX needs a static raster image; HTML can render live, interactive/zoomable SVG instead of a flat image, which is strictly better when the output is viewed in a browser. |
| RTL detection | Unicode code-point ranges (no ICU dependency) | Arabic/Hebrew/Syriac blocks are static and well-known; a regex-free range check is enough to choose direction per paragraph, table cell, and even per inline run within mixed-language text — and it needs zero system dependencies. |

A `pandoc`-based approach was considered, but pandoc has no native Mermaid
support and only partial control over per-run bidi styling in its DOCX
writer — both would still need this same custom pre/post-processing, so a
direct Python implementation ended up simpler than wrapping pandoc.

## Install

```bash
pip install -r requirements.txt
# or, for the `md2doc` console command:
pip install -e .
```

Optional, for the highest-fidelity offline diagram rendering:

```bash
npm install -g @mermaid-js/mermaid-cli   # provides `mmdc`
```

Without `mmdc`, Mermaid diagrams used in **DOCX** output are rendered via the
public [mermaid.ink](https://mermaid.ink) API instead (requires network; use
`--no-network` to disable and keep diagrams as labelled source blocks
instead). **HTML** output never needs either backend by default — diagrams
render live in the browser via mermaid.js — unless you pass
`--html-mermaid-render` to bake them into static images instead.

## Usage

```bash
# single file, explicit format
md2doc report.md --format docx
md2doc report.md --format html

# or run as a module if not installed as a script
python -m md2doc report.md --format docx

# no --format: interactive prompt (TTY only)
md2doc report.md

# a whole directory, recursively, mirroring structure into ./docs_html
md2doc ./docs --format html -o ./docs_html

# choose a specific output file
md2doc report.md -f docx -o build/report.docx

# pick the Arabic complex-script font baked into the .docx
md2doc report.md -f docx --arabic-font "Noto Naskh Arabic"

# fully offline (no mermaid.ink fallback, no remote image fetches)
md2doc report.md -f docx --no-network
```

Try it on the bundled example:

```bash
md2doc examples/sample.md -f html -o /tmp/sample.html
md2doc examples/sample.md -f docx -o /tmp/sample.docx
```

## Feature notes

- **Tables**: standard and GFM-aligned (`:--`, `:-:`, `--:`) tables render
  with borders, header shading, and per-cell RTL detection in both formats.
  Plain Markdown has no colspan/rowspan syntax, so merged cells aren't
  supported — none of `pandoc`, `marked`, or any other Markdown-based tool
  support this either, since it isn't representable in the source format.
- **Mermaid diagrams**: any fenced block tagged `mermaid` is detected
  automatically. HTML gets interactive client-rendered SVG; DOCX gets a
  centered embedded PNG sized to fit the page width.
- **Arabic / RTL**: paragraph, heading, list item, and table-cell direction
  is set automatically from the dominant script of their text (`dir="rtl"`
  in HTML, `w:bidi`/`w:rtl` in DOCX). Mixed Arabic/Latin text is split into
  per-script runs so each part gets correct direction, alignment, and font
  — including inside a single sentence. HTML ships a font stack with
  Arabic-capable fallbacks (Noto Naskh/Sans Arabic, Amiri) pulled from
  Google Fonts; DOCX embeds a complex-script font reference (`--arabic-font`,
  default `Arial`) that must be installed on the machine opening the
  document to render correctly — point it at whatever Arabic font you use
  (e.g. `Noto Naskh Arabic`, `Amiri`, `Traditional Arabic`).

## Project layout

```
md2doc/
  parser.py        Markdown -> token stream (markdown-it-py)
  lang.py           Unicode-range RTL/Arabic detection + bidi run splitting
  mermaid.py        Mermaid -> PNG/SVG (mmdc local, mermaid.ink fallback)
  html_writer.py     tokens -> standalone HTML document
  docx_writer.py     tokens -> python-docx Document (direct OOXML for bidi)
  cli.py             argument parsing, file/directory walking
```

## Tests

```bash
python -m tests.test_basic
```
