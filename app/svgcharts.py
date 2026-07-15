"""Tiny dependency-free SVG chart builders for the PDF report.

Replaces matplotlib: generating an SVG string is effectively free (no figure
rendering, no font cache, no image encoding), which matters a lot on a small
throttled instance. WeasyPrint rasterizes the inline SVG during layout."""
from __future__ import annotations

import html
import math

GREEN = ["#5f7a4f", "#889d7b", "#b6c7a6", "#3d5430", "#cdd8c1", "#7a8f66", "#a4b58f"]
_DARK = "#3d5430"


def _esc(s: str) -> str:
    return html.escape(str(s))


def _wrap(title: str, width: int, height: int, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Helvetica, Arial, sans-serif">'
        f'<text x="0" y="14" font-size="12" font-weight="bold" fill="{_DARK}">{_esc(title)}</text>'
        f'{body}</svg>'
    )


def donut(pairs: list[tuple[str, float]], title: str) -> str:
    pairs = [(l, v) for l, v in pairs if v and v > 0]
    total = sum(v for _, v in pairs)
    cx, cy, r, sw = 70, 105, 52, 24
    circ = 2 * math.pi * r
    segs, offset = [], 0.0
    for i, (_l, v) in enumerate(pairs):
        seg = circ * (v / total) if total else 0
        segs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GREEN[i % len(GREEN)]}" '
            f'stroke-width="{sw}" stroke-dasharray="{seg:.2f} {circ - seg:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += seg
    legend, ly = [], 46
    for i, (l, v) in enumerate(pairs):
        pct = (v / total * 100) if total else 0
        legend.append(
            f'<rect x="150" y="{ly - 9}" width="10" height="10" fill="{GREEN[i % len(GREEN)]}"/>'
            f'<text x="166" y="{ly}" font-size="10">{_esc(l)} {pct:.0f}%</text>'
        )
        ly += 18
    body = "".join(segs) + "".join(legend)
    if not pairs:
        body = f'<text x="{cx}" y="{cy}" font-size="10" text-anchor="middle">no data</text>'
    return _wrap(title, 300, 210, body)


def hbar(pairs: list[tuple[str, float]], title: str, top: int = 8) -> str:
    pairs = [(l, v) for l, v in pairs if v > 0][:top]
    maxv = max((v for _, v in pairs), default=1) or 1
    bar_x, bar_w = 118, 200
    rows, y = [], 34
    for l, v in pairs:
        w = bar_w * (v / maxv)
        rows.append(
            f'<text x="0" y="{y + 11}" font-size="10">{_esc(l[:18])}</text>'
            f'<rect x="{bar_x}" y="{y}" width="{w:.1f}" height="14" rx="2" fill="{GREEN[0]}"/>'
            f'<text x="{bar_x + w + 5:.1f}" y="{y + 11}" font-size="9" fill="#4a553f">${v:,.0f}</text>'
        )
        y += 22
    height = max(60, y + 6)
    body = "".join(rows) or '<text x="0" y="40" font-size="10">no data</text>'
    return _wrap(title, 360, height, body)


def line(points: list[tuple[str, float]], title: str) -> str:
    width, height, pad = 360, 150, 26
    vals = [v for _, v in points]
    maxv = max(vals, default=1) or 1
    n = len(points)

    def px(i: int) -> float:
        return pad + (width - 2 * pad) * (i / (n - 1) if n > 1 else 0.5)

    def py(v: float) -> float:
        return height - pad - (height - 2 * pad) * (v / maxv)

    dots = "".join(
        f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="2.5" fill="{_DARK}"/>'
        for i, (_l, v) in enumerate(points)
    )
    labels = "".join(
        f'<text x="{px(i):.1f}" y="{height - 6}" font-size="8" text-anchor="middle">{_esc(l[2:])}</text>'
        for i, (l, _v) in enumerate(points)
    )
    poly = ""
    if n > 1:
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, (_l, v) in enumerate(points))
        poly = f'<polyline points="{pts}" fill="none" stroke="{_DARK}" stroke-width="2"/>'
    body = poly + dots + labels or '<text x="0" y="40" font-size="10">no data</text>'
    return _wrap(title, width, height, body)
