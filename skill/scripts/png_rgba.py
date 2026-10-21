"""Minimal lossless reader/writer for 8-bit, non-interlaced RGBA PNG templates."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def read_rgba(path: Path) -> tuple[int, int, bytearray]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"不是 PNG 文件：{path}")
    cursor = len(PNG_SIGNATURE)
    width = height = 0
    compressed = bytearray()
    while cursor < len(data):
        length = struct.unpack(">I", data[cursor:cursor + 4])[0]
        kind = data[cursor + 4:cursor + 8]
        payload = data[cursor + 8:cursor + 8 + length]
        cursor += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if bit_depth != 8 or color_type not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError("PNG 必须是 8-bit、RGB/RGBA、非交错格式。")
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(compressed))
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError("PNG 像素数据长度异常。")

    pixels = bytearray(width * height * 4)
    previous = bytearray(stride)
    source = 0
    for y in range(height):
        filter_type = raw[source]
        source += 1
        encoded = raw[source:source + stride]
        source += stride
        row = bytearray(stride)
        for x, value in enumerate(encoded):
            left = row[x - channels] if x >= channels else 0
            above = previous[x]
            upper_left = previous[x - channels] if x >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise ValueError(f"不支持的 PNG 滤镜：{filter_type}")
            row[x] = (value + predictor) & 0xFF
        if channels == 4:
            start = y * width * 4
            pixels[start:start + stride] = row
        else:
            target = y * width * 4
            for channel_offset in range(0, stride, 3):
                pixels[target:target + 4] = row[channel_offset:channel_offset + 3] + b"\xff"
                target += 4
        previous = row
    return width, height, pixels


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def write_rgba(path: Path, width: int, height: int, pixels: bytes) -> None:
    stride = width * 4
    if len(pixels) != stride * height:
        raise ValueError("RGBA 像素长度与尺寸不匹配。")
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)
        start = y * stride
        scanlines.extend(pixels[start:start + stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(scanlines, 9)) + _chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def fill_box(
    pixels: bytearray,
    width: int,
    box: tuple[int, int, int, int],
    rgba: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    row = bytes(rgba) * (right - left)
    for y in range(top, bottom):
        start = (y * width + left) * 4
        pixels[start:start + len(row)] = row


def crop_rgba(
    pixels: bytes,
    width: int,
    box: tuple[int, int, int, int],
) -> tuple[int, int, bytearray]:
    left, top, right, bottom = box
    out_width, out_height = right - left, bottom - top
    result = bytearray(out_width * out_height * 4)
    for out_y, source_y in enumerate(range(top, bottom)):
        source_start = (source_y * width + left) * 4
        target_start = out_y * out_width * 4
        result[target_start:target_start + out_width * 4] = pixels[
            source_start:source_start + out_width * 4
        ]
    return out_width, out_height, result
