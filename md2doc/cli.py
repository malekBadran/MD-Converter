"""md2doc command-line interface.

Usage:
    md2doc SOURCE [--format {docx,html}] [-o OUTPUT] [options]

SOURCE may be a single .md file or a directory (converted recursively,
mirroring the directory structure into the output location).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .docx_writer import convert_to_docx
from .html_writer import extract_title, render_html
from .mermaid import MermaidRenderer
from .parser import parse


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="md2doc",
        description="Convert Markdown (.md) files to Word (.docx) or HTML, "
        "with table, Mermaid diagram and Arabic/RTL support.",
    )
    p.add_argument("source", type=Path, help="Markdown file or directory to convert")
    p.add_argument(
        "-f", "--format", choices=["docx", "html"], default=None,
        help="Output format. If omitted, you'll be prompted (interactive terminals only).",
    )
    p.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output file (single-file mode) or output directory (directory mode). "
        "Defaults to alongside the source.",
    )
    p.add_argument(
        "--arabic-font", default="Arial",
        help="Complex-script (Arabic) font name to embed in DOCX output (default: Arial). "
        "Must be installed wherever the document is opened to render correctly, "
        "e.g. 'Noto Naskh Arabic', 'Amiri', 'Traditional Arabic'.",
    )
    p.add_argument(
        "--mermaid-cli", default=None,
        help="Path to a local mermaid-cli (mmdc) binary. Auto-detected from PATH if omitted.",
    )
    p.add_argument(
        "--no-network", action="store_true",
        help="Disable network fallback for Mermaid rendering (mermaid.ink) and remote images. "
        "Diagrams are kept as labelled source blocks if mermaid-cli isn't available locally.",
    )
    p.add_argument(
        "--html-mermaid-render", action="store_true",
        help="Pre-render Mermaid diagrams to static images in HTML output instead of the "
        "default client-side interactive rendering via mermaid.js.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Print warnings during conversion.")
    return p


def _prompt_format() -> str:
    if not sys.stdin.isatty():
        print(
            "error: no --format given and input is not interactive; "
            "pass --format {docx,html} explicitly.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    while True:
        choice = input("Output format - 'docx' or 'html'? [docx]: ").strip().lower() or "docx"
        if choice in ("docx", "html"):
            return choice
        print("Please enter 'docx' or 'html'.")


def _find_markdown_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def _output_path_for(src_file: Path, source_root: Path, output_root: Path | None, fmt: str, single_file: bool) -> Path:
    ext = ".docx" if fmt == "docx" else ".html"
    if single_file:
        if output_root is not None:
            if output_root.suffix:
                return output_root
            return output_root / src_file.with_suffix(ext).name
        return src_file.with_suffix(ext)
    rel = src_file.relative_to(source_root)
    base = output_root if output_root is not None else source_root.parent / f"{source_root.name}_{fmt}"
    return (base / rel).with_suffix(ext)


def convert_one(src_file: Path, dst_file: Path, fmt: str, args: argparse.Namespace) -> None:
    text = src_file.read_text(encoding="utf-8")
    tokens = parse(text)

    def warn(msg: str) -> None:
        if args.verbose:
            print(f"  [warn] {src_file}: {msg}", file=sys.stderr)

    mermaid_renderer = MermaidRenderer(
        mmdc_path=args.mermaid_cli,
        allow_network=not args.no_network,
        on_warning=warn,
    )

    if fmt == "docx":
        convert_to_docx(
            tokens,
            dst_file,
            base_dir=src_file.parent,
            mermaid_renderer=mermaid_renderer,
            arabic_font=args.arabic_font,
            allow_network=not args.no_network,
            warn=warn,
        )
    else:
        title = extract_title(tokens, fallback=src_file.stem)
        html = render_html(
            tokens,
            title=title,
            mermaid_renderer=mermaid_renderer,
            static_mermaid=args.html_mermaid_render,
            warn=warn,
        )
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        dst_file.write_text(html, encoding="utf-8")

    print(f"  {src_file} -> {dst_file}")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    source: Path = args.source

    if not source.exists():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 1

    fmt = args.format or _prompt_format()

    if source.is_file():
        if source.suffix.lower() != ".md":
            print(f"error: not a Markdown file: {source}", file=sys.stderr)
            return 1
        dst = _output_path_for(source, source.parent, args.output, fmt, single_file=True)
        try:
            convert_one(source, dst, fmt, args)
        except Exception as exc:
            print(f"error converting {source}: {exc}", file=sys.stderr)
            return 1
        return 0

    # Directory mode
    files = _find_markdown_files(source)
    if not files:
        print(f"No .md files found under {source}", file=sys.stderr)
        return 1

    failures = 0
    for f in files:
        dst = _output_path_for(f, source, args.output, fmt, single_file=False)
        try:
            convert_one(f, dst, fmt, args)
        except Exception as exc:
            print(f"error converting {f}: {exc}", file=sys.stderr)
            failures += 1

    total = len(files)
    print(f"Converted {total - failures}/{total} file(s).")
    return 1 if failures else 0
