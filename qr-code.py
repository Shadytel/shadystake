#!/usr/bin/env python3
"""Generate an SVG QR code for a URI."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlparse


PX_TO_MM = 25.4 / 96  # 1 px = 1/96 inch; 1 inch = 25.4 mm

MODULE_PX = 3
BORDER_MODULES = 3

MODULE_MM = MODULE_PX * PX_TO_MM
BORDER_MM = BORDER_MODULES * MODULE_MM
FILENAME_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def parse_uri(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme:
        raise argparse.ArgumentTypeError("URI must include a scheme, such as https:, mailto:, tel:, or ftp:")
    if not any((parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)):
        raise argparse.ArgumentTypeError("URI must include content after the scheme")
    return value


def safe_filename_stem(value: str) -> str:
    return FILENAME_SAFE_CHARS.sub("_", value).strip("._-")


def default_output_path(uri: str) -> Path:
    parsed = urlparse(uri)
    stem_source = parsed.hostname

    if stem_source is not None:
        try:
            stem_source = stem_source.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"Invalid hostname {stem_source!r}") from exc
    else:
        stem_source = f"{parsed.scheme}_{parsed.netloc or parsed.path or uri}"

    safe_stem = safe_filename_stem(stem_source)
    if not safe_stem:
        raise ValueError("URI cannot be converted to a safe filename")
    return Path(f"{safe_stem}.svg")


def build_svg(
    data: str,
    module_mm: float = MODULE_MM,
    border_mm: float = BORDER_MM,
    pixels: str = "both",
) -> tuple[str, int, float]:
    if pixels not in ("both", "black", "white"):
        raise ValueError("pixels must be one of: both, black, white")

    try:
        import qrcode
    except ModuleNotFoundError as exc:
        raise RuntimeError("Missing dependency: install with `python -m pip install qrcode`") from exc

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=0,
    )
    qr.add_data(data)
    qr.make(fit=True)

    matrix = qr.get_matrix()
    module_count = len(matrix)
    qr_size_mm = module_count * module_mm
    size_mm = qr_size_mm + (border_mm * 2)

    # viewBox uses unitless user coordinates where 1 user unit = 1 mm.
    # Only the SVG width/height carry the "mm" suffix; internal rect
    # coordinates are plain numbers so the viewBox transform applies correctly.
    def fmt(v: float) -> str:
        return f"{v:.6f}".rstrip("0").rstrip(".")

    border_modules = round(border_mm / module_mm)
    if abs(border_modules * module_mm - border_mm) > 1e-9:
        raise ValueError("border_mm must be an exact multiple of module_mm")

    rects = []
    total_module_count = module_count + (border_modules * 2)
    for y in range(total_module_count):
        matrix_y = y - border_modules
        if 0 <= matrix_y < module_count:
            row = [False] * border_modules + matrix[matrix_y] + [False] * border_modules
        else:
            row = [False] * total_module_count

        x = 0
        while x < total_module_count:
            run_start = x
            fill = "black" if row[x] else "white"
            while x < total_module_count and row[x] == row[run_start]:
                x += 1

            if pixels in ("both", fill):
                rects.append(
                    f'<rect x="{fmt(run_start * module_mm)}" y="{fmt(y * module_mm)}" '
                    f'width="{fmt((x - run_start) * module_mm)}" height="{fmt(module_mm)}" fill="{fill}"/>'
                )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
     width="{fmt(size_mm)}mm" height="{fmt(size_mm)}mm"
     viewBox="0 0 {fmt(size_mm)} {fmt(size_mm)}">
{chr(10).join(rects)}
</svg>
'''
    return svg, module_count, size_mm


def write_svg(output_path: Path, svg: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an SVG QR code for a URI.")
    parser.add_argument("uri", type=parse_uri, help="URI to encode, such as https:, mailto:, tel:, or ftp:")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="SVG output path; defaults to the URI hostname plus .svg when available",
    )
    parser.add_argument(
        "--pixels",
        choices=("both", "black", "white"),
        default="both",
        help="which QR pixels to emit; defaults to both",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        output_path = args.output or default_output_path(args.uri)
        svg, module_count, size_mm = build_svg(args.uri, pixels=args.pixels)
        write_svg(output_path, svg)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"error: {exc}\n")

    print(f"Wrote {output_path}: {module_count}x{module_count} modules, {size_mm}mm square")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
