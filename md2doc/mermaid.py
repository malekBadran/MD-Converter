"""Render Mermaid.js diagram source to images.

Two rendering backends are tried, in order:

1. A local `mmdc` (mermaid-cli, https://github.com/mermaid-js/mermaid-cli)
   binary, if present on PATH. Fully offline, highest fidelity.
2. The public mermaid.ink rendering service (https://mermaid.ink), used as
   a fallback when mmdc isn't installed. Requires network access; can be
   disabled with `allow_network=False`.

If neither backend is available the caller gets `None` back and is expected
to degrade gracefully (e.g. keep the diagram as a labelled code block).
"""

from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MERMAID_INK_BASE = "https://mermaid.ink"
_USER_AGENT = "md2doc/1.0 (+https://github.com)"


@dataclass
class RenderedDiagram:
    data: bytes
    format: str  # "png" or "svg"
    source: str  # how it was produced, for diagnostics


class MermaidRenderer:
    def __init__(
        self,
        mmdc_path: str | None = None,
        allow_network: bool = True,
        cache_dir: Path | None = None,
        on_warning=None,
    ):
        self._mmdc = mmdc_path or shutil.which("mmdc")
        self._allow_network = allow_network
        self._cache: dict[tuple[str, str], RenderedDiagram | None] = {}
        self._cache_dir = cache_dir
        self._warn = on_warning or (lambda msg: None)

    def available(self) -> bool:
        return bool(self._mmdc) or self._allow_network

    def render(self, mermaid_src: str, fmt: str = "png") -> RenderedDiagram | None:
        """Render mermaid_src to the requested format ('png' or 'svg').
        Results are memoized per (source, format) for the lifetime of this
        renderer instance, since the same diagram often repeats across a
        directory conversion run."""
        key = (mermaid_src, fmt)
        if key in self._cache:
            return self._cache[key]

        result = None
        if self._mmdc:
            result = self._render_mmdc(mermaid_src, fmt)
        if result is None and self._allow_network:
            result = self._render_mermaid_ink(mermaid_src, fmt)
        if result is None:
            self._warn(
                "Could not render a Mermaid diagram (no local mermaid-cli "
                "and network rendering unavailable/disabled); leaving it as "
                "source text."
            )
        self._cache[key] = result
        return result

    def _render_mmdc(self, mermaid_src: str, fmt: str) -> RenderedDiagram | None:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                in_path = Path(tmp) / "diagram.mmd"
                out_path = Path(tmp) / f"diagram.{fmt}"
                in_path.write_text(mermaid_src, encoding="utf-8")
                proc = subprocess.run(
                    [
                        self._mmdc,
                        "-i", str(in_path),
                        "-o", str(out_path),
                        "-b", "transparent",
                    ],
                    capture_output=True,
                    timeout=60,
                )
                if proc.returncode != 0 or not out_path.exists():
                    self._warn(
                        f"mermaid-cli failed (exit {proc.returncode}): "
                        f"{proc.stderr.decode(errors='replace')[:300]}"
                    )
                    return None
                return RenderedDiagram(out_path.read_bytes(), fmt, "mmdc")
        except (OSError, subprocess.SubprocessError) as exc:
            self._warn(f"mermaid-cli invocation failed: {exc}")
            return None

    def _render_mermaid_ink(self, mermaid_src: str, fmt: str) -> RenderedDiagram | None:
        encoded = base64.urlsafe_b64encode(mermaid_src.encode("utf-8")).decode().rstrip("=")
        path = "svg" if fmt == "svg" else "img"
        url = f"{MERMAID_INK_BASE}/{path}/{encoded}"
        if fmt != "svg":
            url += "?type=png"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            return RenderedDiagram(data, fmt, "mermaid.ink")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._warn(f"mermaid.ink rendering failed: {exc}")
            return None


def diagram_cache_key(mermaid_src: str) -> str:
    return hashlib.sha1(mermaid_src.encode("utf-8")).hexdigest()[:16]
