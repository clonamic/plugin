#!/usr/bin/env python3
"""Render PPTX to PNG and flag empty / near-empty slides."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from engine_lib import SLIDE_H, SLIDE_W


def issue(sev: str, code: str, msg: str, slide: str | None = None) -> dict:
    return {"severity": sev, "code": code, "message": msg, "slide_id": slide, "element_id": None}


def _soffice() -> str | None:
    if platform.system() == "Darwin" and os.environ.get("CLONAMIC_ALLOW_MACOS_SOFFICE") != "1":
        return None
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    mac = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    return str(mac) if mac.exists() else None


def render_pngs(pptx: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    soffice = _soffice()
    if not soffice:
        return []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        profile = td_path / "profile"
        profile.mkdir()
        common = [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile.as_uri()}",
        ]
        try:
            proc = subprocess.run(
                [*common, "--convert-to", "pdf", "--outdir", str(td_path), str(pptx)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        pdfs = list(td_path.glob("*.pdf"))
        if proc.returncode != 0 or not pdfs:
            return []
        pdf = pdfs[0]
        if shutil.which("pdftoppm"):
            try:
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "110", str(pdf), str(out_dir / "slide")],
                    check=False,
                    capture_output=True,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                return []
        else:
            try:
                subprocess.run(
                    [*common, "--convert-to", "png", "--outdir", str(out_dir), str(pdf)],
                    capture_output=True,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                return []
    pngs = sorted(out_dir.glob("slide*.png")) + sorted(out_dir.glob("*.png"))
    # unique preserve order
    seen = set()
    out = []
    for p in pngs:
        if p.name not in seen:
            seen.add(p.name)
            out.append(p)
    return out


def ink_ratio(png: Path) -> float | None:
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return None
    img = Image.open(png).convert("RGB")
    arr = __import__("numpy").array(img)
    # Count only near-paper white as empty. Card fill #F7F8FA must count as ink.
    white = (arr[:, :, 0] > 252) & (arr[:, :, 1] > 252) & (arr[:, :, 2] > 252)
    return float(1.0 - white.mean())


def ir_coverage(slide: dict) -> float:
    area = 0.0
    for el in slide.get("elements") or []:
        bb = el.get("bbox") or {}
        try:
            area += float(bb["w"]) * float(bb["h"])
        except Exception:
            continue
    return area / (SLIDE_W * SLIDE_H)


def qa_visual_report(pptx: Path, deck: dict, png_dir: Path) -> dict:
    issues: list[dict] = []
    slides = deck.get("slides") or []
    for s in slides:
        cov = ir_coverage(s)
        if cov < 0.22:
            issues.append(issue("major", "VIS001", f"IR coverage {cov:.2f} < 0.22 (sparse)", s.get("slide_id")))
    pngs = render_pngs(pptx, png_dir)
    if not pngs:
        issues.append(issue("info", "VIS000", "visual render unavailable or disabled"))
        return {"visual_status": "unavailable", "issues": issues}
    for i, png in enumerate(pngs):
        sid = slides[i]["slide_id"] if i < len(slides) else f"png{i+1}"
        ratio = ink_ratio(png)
        if ratio is None:
            continue
        if ratio < 0.04:
            issues.append(issue("blocker", "VIS002", f"near-empty render ink={ratio:.3f}", sid))
        elif ratio < 0.09:
            issues.append(issue("major", "VIS003", f"sparse render ink={ratio:.3f}", sid))
    return {"visual_status": "rendered", "issues": issues}


def qa_visual(pptx: Path, deck: dict, png_dir: Path) -> list[dict]:
    return qa_visual_report(pptx, deck, png_dir)["issues"]
