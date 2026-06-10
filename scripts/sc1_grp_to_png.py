#!/usr/bin/env python3
"""Convert a StarCraft GRP file to PNG without launching PyMS UI.

This script expects the PyMS source tree to exist under tools/mpq/PyMS. It does
not contain or download any StarCraft assets; it only converts local GRP files.
"""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
PYMS_ROOT = REPO_ROOT / "tools" / "mpq" / "PyMS"
DEFAULT_PALETTE = PYMS_ROOT / "Palettes" / "Units.pal"


def _load_palette(path: Path) -> list[list[int]]:
    data = path.read_bytes()
    if len(data) != 256 * 3:
        raise ValueError(f"Unsupported palette size for {path}: {len(data)} bytes")
    return [list(data[i : i + 3]) for i in range(0, len(data), 3)]


class GrpInfo:
    def __init__(self, frames: int, width: int, height: int):
        self.frames = frames
        self.width = width
        self.height = height


def _decode_grp(grp_path: Path) -> tuple[GrpInfo, list[list[list[int]]]]:
    data = grp_path.read_bytes()
    if len(data) < 6:
        raise ValueError(f"{grp_path} is too small to be a GRP")

    frame_count, width, height = struct.unpack_from("<3H", data, 0)
    if not (1 <= frame_count <= 2400 and 1 <= width <= 256 and 1 <= height <= 256):
        raise ValueError(f"Unsupported GRP header in {grp_path}")

    decoded_frames: list[list[list[int]]] = []
    for frame_idx in range(frame_count):
        entry_offset = 6 + 8 * frame_idx
        xoff, yoff, line_width, line_count, frame_data = struct.unpack_from(
            "<4BL", data, entry_offset
        )
        if xoff + line_width > width:
            line_width = width - xoff
        if yoff + line_count > height:
            line_count = height - yoff

        image = [[0 for _ in range(width)] for _ in range(height)]
        for line_idx in range(line_count):
            line_table_offset = frame_data + 2 * line_idx
            rel_offset = struct.unpack_from("<H", data, line_table_offset)[0]
            cursor = frame_data + rel_offset
            row: list[int] = []

            while len(row) < line_width:
                opcode = data[cursor]
                cursor += 1
                if opcode & 0x80:
                    row.extend([0] * (opcode - 0x80))
                elif opcode & 0x40:
                    count = opcode - 0x40
                    value = data[cursor]
                    cursor += 1
                    row.extend([value] * count)
                else:
                    count = opcode
                    row.extend(data[cursor : cursor + count])
                    cursor += count

            y = yoff + line_idx
            x_start = xoff
            for x_delta, value in enumerate(row[:line_width]):
                image[y][x_start + x_delta] = value

        decoded_frames.append(image)

    return GrpInfo(frame_count, width, height), decoded_frames


def _indexed_to_rgba(image: list[list[int]], palette: list[list[int]]) -> Image.Image:
    height = len(image)
    width = len(image[0]) if height else 0
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = []
    for row in image:
        for index in row:
            if index == 0:
                pixels.append((0, 0, 0, 0))
            else:
                r, g, b = palette[index]
                pixels.append((r, g, b, 255))
    out.putdata(pixels)
    return out


def _make_sheet(frames: list[Image.Image], columns: int) -> Image.Image:
    if not frames:
        raise ValueError("GRP produced no frames")
    frame_w = max(frame.width for frame in frames)
    frame_h = max(frame.height for frame in frames)
    cols = max(1, columns)
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGBA", (frame_w * cols, frame_h * rows), (0, 0, 0, 0))
    for idx, frame in enumerate(frames):
        x = (idx % cols) * frame_w
        y = (idx // cols) * frame_h
        sheet.alpha_composite(frame, (x, y))
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("grp", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--palette", type=Path, default=DEFAULT_PALETTE)
    parser.add_argument("--columns", type=int, default=17)
    parser.add_argument(
        "--first-frame",
        action="store_true",
        help="Write only frame 0 instead of a contact sheet.",
    )
    args = parser.parse_args()

    palette = _load_palette(args.palette)
    grp, decoded_frames = _decode_grp(args.grp)
    frames = [_indexed_to_rgba(frame, palette) for frame in decoded_frames]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image = frames[0] if args.first_frame else _make_sheet(frames, args.columns)
    image.save(args.output)
    print(
        f"wrote {args.output} from {args.grp} "
        f"frames={grp.frames} frame_size={grp.width}x{grp.height}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
