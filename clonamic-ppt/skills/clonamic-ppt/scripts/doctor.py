#!/usr/bin/env python3
"""Report presentation runtime readiness without installing dependencies."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def check_runtime(package_root: Path) -> dict[str, object]:
    package_root = package_root.resolve()
    vendor = package_root / "vendor/image-size/index.js"
    installed_image = package_root / "node_modules/image-size/index.js"
    checks = {
        "node": shutil.which("node") is not None,
        "package_lock": (package_root / "package-lock.json").is_file(),
        "pptxgenjs": (package_root / "node_modules/pptxgenjs/package.json").is_file(),
        "image_size_guard": installed_image.exists()
        and installed_image.resolve() == vendor.resolve(),
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "recovery": f"npm ci --ignore-scripts --prefix {package_root}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    args = parser.parse_args(argv)
    result = check_runtime(args.package_root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
