#!/usr/bin/env python3
"""WCAG 2.x contrast check for one foreground/background pair, with an optional lightness repair.

Usage:
    python3 contrast.py FG BG [--target RATIO] [--fix fg|bg] [--json]

Colors are hex (#rgb, #rrggbb, or #rrggbbaa). A translucent foreground is composited over the
background before measuring. --fix moves only the OKLCH lightness of the chosen color (hue and
chroma kept, chroma reduced only when needed to stay in sRGB) until the pair reaches --target.

Exit codes: 0 = pair meets --target (default 4.5), 1 = below target, 2 = usage error.
Standard library only; requires Python 3.12+.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys

if sys.version_info < (3, 12):
    sys.exit("contrast.py needs Python 3.12+; install it (for example `uv python install 3.12`).")

HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
LEVELS = {"AA normal": 4.5, "AA large": 3.0, "AAA normal": 7.0, "AAA large": 4.5, "UI component": 3.0}


def parse_hex(value: str) -> tuple[float, float, float, float]:
    match = HEX.match(value.strip())
    if not match:
        raise ValueError(f"not a hex color: {value!r}")
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    channels = [int(digits[i : i + 2], 16) / 255 for i in range(0, len(digits), 2)]
    alpha = channels[3] if len(channels) == 4 else 1.0
    return channels[0], channels[1], channels[2], alpha


def to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(min(1.0, max(0.0, c)) * 255):02X}" for c in rgb)


def composite(fg: tuple[float, float, float, float], bg: tuple[float, float, float]) -> tuple[float, float, float]:
    alpha = fg[3]
    return tuple(fg[i] * alpha + bg[i] * (1 - alpha) for i in range(3))  # type: ignore[return-value]


def linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def gamma(channel: float) -> float:
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def to_oklch(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (linear(c) for c in rgb)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness, math.hypot(a, bb), math.atan2(bb, a)


def from_oklch(lightness: float, chroma: float, hue: float) -> tuple[float, float, float] | None:
    a, b = chroma * math.cos(hue), chroma * math.sin(hue)
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    if any(c < -1e-6 or c > 1 + 1e-6 for c in rgb):
        return None
    return tuple(gamma(min(1.0, max(0.0, c))) for c in rgb)  # type: ignore[return-value]


def in_gamut(lightness: float, chroma: float, hue: float) -> tuple[float, float, float]:
    """Return the sRGB color at this lightness, lowering chroma until it fits."""
    low, high = 0.0, chroma
    best = from_oklch(lightness, 0.0, hue)
    if (exact := from_oklch(lightness, chroma, hue)) is not None:
        return exact
    for _ in range(30):
        mid = (low + high) / 2
        candidate = from_oklch(lightness, mid, hue)
        if candidate is None:
            high = mid
        else:
            low, best = mid, candidate
    assert best is not None
    return best


def repair(moving: tuple[float, float, float], fixed: tuple[float, float, float], target: float):
    """Find the smallest OKLCH lightness shift of the moving color that meets the target."""
    lightness, chroma, hue = to_oklch(moving)
    if chroma < 1e-4:  # achromatic: keep it neutral instead of inheriting hue noise
        chroma = 0.0

    def passes(level: float) -> bool:
        return ratio(parse_hex(to_hex(in_gamut(level, chroma, hue)))[:3], fixed) >= target

    away = -1.0 if luminance(moving) <= luminance(fixed) else 1.0
    step = 0.005
    for index in range(1, int(1 / step) + 2):
        for direction in (away, -away):
            level = lightness + direction * index * step
            if not 0.0 <= level <= 1.0 or not passes(level):
                continue
            near = lightness + direction * (index - 1) * step
            far = level
            for _ in range(20):
                mid = (near + far) / 2
                if passes(mid):
                    far = mid
                else:
                    near = mid
            return to_hex(in_gamut(far, chroma, hue))
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WCAG 2.x contrast ratio for one color pair.")
    parser.add_argument("fg")
    parser.add_argument("bg")
    parser.add_argument("--target", type=float, default=4.5)
    parser.add_argument("--fix", choices=("fg", "bg"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        fg_raw, bg_raw = parse_hex(args.fg), parse_hex(args.bg)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if bg_raw[3] < 1.0:
        print("error: background must be opaque", file=sys.stderr)
        return 2
    bg = bg_raw[:3]
    fg = composite(fg_raw, bg)
    value = ratio(fg, bg)
    result: dict[str, object] = {
        "fg": to_hex(fg),
        "bg": to_hex(bg),
        "ratio": round(value, 2),
        "target": args.target,
        "meets_target": value >= args.target,
        "levels": {name: value >= need for name, need in LEVELS.items()},
    }
    if args.fix and value < args.target:
        moving, fixed = (fg, bg) if args.fix == "fg" else (bg, fg)
        fixed_hex = repair(moving, fixed, args.target)
        result["fix"] = (
            {"role": args.fix, "value": fixed_hex,
             "ratio": round(ratio(parse_hex(fixed_hex)[:3], fixed), 2)}
            if fixed_hex else {"role": args.fix, "value": None, "reason": "target unreachable by lightness alone"}
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        verdicts = ", ".join(f"{name} {'pass' if ok else 'fail'}" for name, ok in result["levels"].items())
        print(f"{result['fg']} on {result['bg']}: {result['ratio']}:1 ({verdicts})")
        if fix := result.get("fix"):
            if fix["value"]:
                print(f"fix {fix['role']}: {fix['value']} -> {fix['ratio']}:1")
            else:
                print(f"fix {fix['role']}: {fix['reason']}")
    return 0 if value >= args.target else 1


if __name__ == "__main__":
    sys.exit(main())
