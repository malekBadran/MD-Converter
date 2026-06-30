"""Unicode-range based Arabic / RTL script detection.

No external dependency (no ICU/fribidi binding) is required: Arabic, Hebrew,
Syriac and other RTL blocks are detected directly from Unicode code points,
which is sufficient to decide paragraph direction and to split a string into
script-homogeneous runs for per-run font/direction styling.
"""

from __future__ import annotations

# Arabic + Arabic Supplement + Arabic Extended-A/B + Arabic Presentation Forms,
# plus Hebrew and Syriac (other common RTL scripts).
_RTL_RANGES = (
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0700, 0x074F),  # Syriac
    (0x0750, 0x077F),  # Arabic Supplement
    (0x0780, 0x07BF),  # Thaana
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB1D, 0xFB4F),  # Hebrew presentation forms
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)


def is_rtl_char(ch: str) -> bool:
    cp = ord(ch)
    for lo, hi in _RTL_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def rtl_ratio(text: str) -> float:
    """Fraction of *alphabetic* characters in text that belong to an RTL script."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    rtl = sum(1 for c in letters if is_rtl_char(c))
    return rtl / len(letters)


def is_rtl_text(text: str, threshold: float = 0.3) -> bool:
    """Whether text should be treated as RTL overall (paragraph/cell direction)."""
    return rtl_ratio(text) >= threshold


def split_bidi_runs(text: str) -> list[tuple[str, bool]]:
    """Split text into contiguous (substring, is_rtl) runs by script.

    Non-alphabetic characters (digits, spaces, punctuation) inherit the
    direction of the run they appear in, so "Hello سلام 123" splits into
    ("Hello ", False), ("سلام 123", True) rather than fragmenting on every
    space/digit.
    """
    if not text:
        return []
    runs: list[tuple[str, bool]] = []
    cur = text[0]
    cur_rtl = is_rtl_char(text[0])
    for ch in text[1:]:
        ch_rtl = is_rtl_char(ch) if ch.isalpha() else cur_rtl
        if ch_rtl == cur_rtl:
            cur += ch
        else:
            runs.append((cur, cur_rtl))
            cur = ch
            cur_rtl = ch_rtl
    runs.append((cur, cur_rtl))
    return runs
