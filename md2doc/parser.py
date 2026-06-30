"""Markdown -> token stream parsing, shared by the HTML and DOCX writers."""

from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

MERMAID_LANGS = {"mermaid"}


def build_md() -> MarkdownIt:
    """Configure a markdown-it-py parser with GFM tables, strikethrough and
    autolinking enabled. The "gfm-like" preset already turns these on."""
    md = MarkdownIt(
        "gfm-like",
        {
            "html": False,  # raw HTML in markdown is not trusted/rendered
            "linkify": True,
            "typographer": True,
        },
    )
    return md


def parse(text: str) -> list[Token]:
    return build_md().parse(text)


def is_mermaid_fence(token: Token) -> bool:
    return token.type == "fence" and token.info.strip().split()[0:1] == ["mermaid"]


def find_block_end(tokens: list[Token], open_idx: int) -> int:
    """Given the index of a *_open token, return the index of its matching
    *_close token. Relies on markdown-it's `level` field: every token
    strictly between an open/close pair at level L has level > L, so the
    matching close is the next token back down at level L."""
    level = tokens[open_idx].level
    idx = open_idx + 1
    while idx < len(tokens):
        if tokens[idx].level == level:
            return idx
        idx += 1
    raise ValueError(f"Unbalanced token stream starting at {open_idx}")
