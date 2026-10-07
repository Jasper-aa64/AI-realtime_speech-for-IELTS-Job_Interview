#!/usr/bin/env python3
"""Export all raster brand icons from studio-brain.svg using librsvg.

Requires rsvg-convert (librsvg) and, for the macOS ICNS bundle, iconutil.
Only Python's standard library is used; ICO entries contain the rendered PNGs.
"""

import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "web/static/assets/brand"
DESKTOP = ROOT / "desktop/assets"
SOURCE = BRAND / "studio-brain.svg"
NS = "{http://www.w3.org/2000/svg}"


def render(renderer: str, source: Path, destination: Path, size: int) -> None:
    subprocess.run([renderer, "--width", str(size), "--height", str(size),
                    "--output", str(destination), str(source)], check=True)
    data = destination.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", data[16:24]) != (size, size):
        raise RuntimeError(f"Incorrect PNG dimensions: {destination}")


def write_ico(destination: Path, images: list[tuple[int, bytes]]) -> None:
    offset = 6 + 16 * len(images)
    entries = []
    for size, data in images:
        entries.append(struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    destination.write_bytes(struct.pack("<HHH", 0, 1, len(images))
                            + b"".join(entries) + b"".join(data for _, data in images))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-icns", action="store_true", help="Export web/Qt PNG icons on non-macOS systems")
    args = parser.parse_args()
    renderer = shutil.which("rsvg-convert")
    iconutil = shutil.which("iconutil")
    if not renderer:
        parser.error("rsvg-convert is required (macOS: brew install librsvg)")
    if not args.skip_icns and not iconutil:
        parser.error("iconutil is required for ICNS (use --skip-icns on non-macOS systems)")

    DESKTOP.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="studio-brand-") as temporary:
        scratch = Path(temporary)
        # SVG styling is for the live UI. Strip animation for deterministic, open-eye rasters.
        tree = ET.parse(SOURCE)
        for style in tree.getroot().findall(f"{NS}style"):
            tree.getroot().remove(style)
        static_source = scratch / "studio-brain.svg"
        tree.write(static_source, encoding="utf-8", xml_declaration=True)

        sizes = {16, 32, 48, 64, 128, 180, 256, 512, 1024}
        pngs = {}
        for size in sorted(sizes):
            pngs[size] = scratch / f"brain-{size}.png"
            render(renderer, static_source, pngs[size], size)
        write_ico(BRAND / "studio-brain.ico", [(size, pngs[size].read_bytes()) for size in (16, 32, 48)])
        shutil.copyfile(pngs[180], BRAND / "studio-brain-180.png")
        for size in (512, 1024):
            shutil.copyfile(pngs[size], DESKTOP / f"studio-brain-{size}.png")

        if not args.skip_icns:
            iconset = scratch / "studio-brain.iconset"
            iconset.mkdir()
            for logical_size in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    suffix = "@2x" if scale == 2 else ""
                    shutil.copyfile(pngs[logical_size * scale],
                                    iconset / f"icon_{logical_size}x{logical_size}{suffix}.png")
            subprocess.run([iconutil, "--convert", "icns", "--output",
                            str(DESKTOP / "studio-brain.icns"), str(iconset)], check=True)
    print("Exported studio-brain favicon, touch icon, and desktop icons from the canonical SVG.")


if __name__ == "__main__":
    main()
