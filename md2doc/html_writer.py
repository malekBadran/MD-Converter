"""Render a parsed Markdown token stream to a standalone HTML document.

RTL/Arabic handling: every text-bearing block (paragraph, heading, table
cell, list item) gets an explicit `dir="rtl"` when its text is
majority-Arabic/Hebrew/Syriac, or `dir="auto"` otherwise so the browser's own
bidi algorithm aligns genuinely mixed-script content correctly. `text-align:
start` in the stylesheet makes alignment follow that resolved direction.

Mermaid diagrams are emitted as `<pre class="mermaid">` blocks rendered
client-side into interactive/zoomable SVG by mermaid.js (loaded from CDN),
unless `static_mermaid=True`, in which case they are pre-rendered to images
(useful for fully offline viewing) via md2doc.mermaid.
"""

from __future__ import annotations

import base64
import html as html_mod
from pathlib import Path

from markdown_it.token import Token

from .lang import rtl_ratio
from .mermaid import MermaidRenderer
from .parser import build_md, find_block_end

RTL_THRESHOLD = 0.3

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.js"

CSS = """
:root {
  color-scheme: light;
}
body {
  font-family: -apple-system, "Segoe UI", Roboto, "Noto Sans Arabic",
    "Noto Naskh Arabic", "Amiri", Tahoma, Arial, sans-serif;
  line-height: 1.65;
  max-width: 860px;
  margin: 2.5rem auto;
  padding: 0 1.5rem;
  color: #1d1f23;
  font-size: 16px;
}
[dir="rtl"] { text-align: right; }
[dir="auto"] { text-align: start; unicode-bidi: plaintext; }
h1, h2, h3, h4, h5, h6 { line-height: 1.3; margin-top: 1.8em; }
h1 { font-size: 2rem; border-bottom: 2px solid #e3e5e8; padding-bottom: .3em; }
h2 { font-size: 1.5rem; border-bottom: 1px solid #e3e5e8; padding-bottom: .25em; }
code, pre {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}
code { background: #f1f2f4; padding: .15em .4em; border-radius: 4px; font-size: .9em; }
pre {
  background: #f6f8fa; padding: 1em; border-radius: 6px; overflow-x: auto;
}
pre code { background: none; padding: 0; }
blockquote {
  border-inline-start: 4px solid #d8dbe0; margin-inline-start: 0;
  padding-inline-start: 1em; color: #555; font-style: italic;
}
table { border-collapse: collapse; width: 100%; margin: 1.2em 0; }
table[dir="rtl"] { direction: rtl; }
.table-wrap { overflow-x: auto; }
th, td { border: 1px solid #d8dbe0; padding: .5em .8em; }
th { background: #f1f2f4; }
tr:nth-child(even) { background: #fafbfc; }
img { max-width: 100%; }
.mermaid { text-align: center; margin: 1.5em 0; }
.mermaid-fallback {
  background: #fff8e1; border: 1px solid #f0d878; border-radius: 6px;
  padding: 1em; font-size: .85em;
}
a { color: #0969da; }
hr { border: none; border-top: 1px solid #d8dbe0; margin: 2em 0; }
"""


def _block_dir(text: str) -> str:
    return "rtl" if rtl_ratio(text) >= RTL_THRESHOLD else "auto"


def _inline_text(tokens: list[Token], idx: int) -> str:
    if idx < len(tokens) and tokens[idx].type == "inline":
        return tokens[idx].content
    return ""


def _aggregate_inline_text(tokens: list[Token], start: int, end: int) -> str:
    return " ".join(t.content for t in tokens[start:end] if t.type == "inline")


def render_html(
    tokens: list[Token],
    title: str = "Document",
    mermaid_renderer: MermaidRenderer | None = None,
    static_mermaid: bool = False,
    warn=None,
) -> str:
    md = build_md()
    renderer = md.renderer
    warn = warn or (lambda msg: None)

    def dir_rule(tag_lookahead_idx_offset=1):
        def rule(tokens_, idx, options, env):
            token = tokens_[idx]
            text = _inline_text(tokens_, idx + tag_lookahead_idx_offset)
            token.attrSet("dir", _block_dir(text))
            return renderer.renderToken(tokens_, idx, options, env)

        return rule

    for tag in ("paragraph_open", "heading_open", "th_open", "td_open"):
        renderer.rules[tag] = dir_rule()

    def table_open_rule(tokens_, idx, options, env):
        token = tokens_[idx]
        end = find_block_end(tokens_, idx)
        text = _aggregate_inline_text(tokens_, idx, end)
        direction = _block_dir(text)
        token.attrSet("dir", direction)
        opening = renderer.renderToken(tokens_, idx, options, env)
        return f'<div class="table-wrap">\n{opening}'

    def table_close_rule(tokens_, idx, options, env):
        return renderer.renderToken(tokens_, idx, options, env) + "</div>\n"

    renderer.rules["table_open"] = table_open_rule
    renderer.rules["table_close"] = table_close_rule

    default_fence = renderer.rules.get("fence")

    def fence_rule(tokens_, idx, options, env):
        token = tokens_[idx]
        lang = token.info.strip().split()[0] if token.info.strip() else ""
        if lang.lower() != "mermaid":
            return default_fence(tokens_, idx, options, env)

        src = token.content
        if static_mermaid and mermaid_renderer is not None:
            diagram = mermaid_renderer.render(src, fmt="svg")
            if diagram is not None:
                if diagram.format == "svg":
                    b64 = base64.b64encode(diagram.data).decode()
                    return (
                        f'<div class="mermaid-static">'
                        f'<img alt="diagram" src="data:image/svg+xml;base64,{b64}"></div>\n'
                    )
                b64 = base64.b64encode(diagram.data).decode()
                return (
                    f'<div class="mermaid-static">'
                    f'<img alt="diagram" src="data:image/png;base64,{b64}"></div>\n'
                )
            warn("Falling back to raw source for one Mermaid diagram (static render failed).")
            escaped = html_mod.escape(src)
            return f'<pre class="mermaid-fallback">{escaped}</pre>\n'

        escaped = html_mod.escape(src)
        return f'<pre class="mermaid">{escaped}</pre>\n'

    renderer.rules["fence"] = fence_rule

    body = renderer.render(tokens, md.options, {})

    mermaid_script = ""
    if not static_mermaid:
        mermaid_script = f"""
<script type="module">
  import mermaid from "{MERMAID_CDN}";
  mermaid.initialize({{ startOnLoad: true, securityLevel: "strict" }});
</script>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}{mermaid_script}</body>
</html>
"""


def extract_title(tokens: list[Token], fallback: str) -> str:
    for i, t in enumerate(tokens):
        if t.type == "heading_open" and t.tag == "h1":
            return _inline_text(tokens, i + 1) or fallback
    return fallback
